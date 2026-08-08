import Foundation

@MainActor
final class AppModel: ObservableObject {
    @Published private(set) var route: AppRoute = .launching
    @Published private(set) var bootstrap = Loadable<BootstrapResponse>()

    private let repository: AppRepository
    private let sessionContextStore: SessionContextStore
    private var bootstrapTask: Task<Void, Never>?
    private var hasStarted = false

    var pushFamilyID: String? {
        guard route == .main else { return nil }
        return bootstrap.value?.activeFamilyID
    }

    init(repository: AppRepository, sessionContextStore: SessionContextStore) {
        self.repository = repository
        self.sessionContextStore = sessionContextStore
    }

    func start(authStore: KeychainAuthStore) {
        guard !hasStarted else { return }
        hasStarted = true
        let arguments = ProcessInfo.processInfo.arguments
        if arguments.contains("-uiTestState") {
            if arguments.contains("-uiTestSessionUnavailable") {
                bootstrap.staleReason = "连接服务器超时，请重新加载。"
                route = .sessionUnavailable
            } else if let rawStep = arguments.first(where: { $0.hasPrefix("-uiTestOnboardingStep=") })?
                .split(separator: "=", maxSplits: 1).last,
               let step = OnboardingStep(rawValue: String(rawStep)) {
                route = .onboarding(step)
            } else if arguments.contains("-uiTestMain") {
                route = .main
            } else {
                route = .signedOut
            }
            return
        }
        beginSessionResolution(authStore: authStore)
    }

    func retryAuthenticatedState() {
        route = .launching
        bootstrapTask?.cancel()
        bootstrapTask = Task { [weak self] in
            guard let self else { return }
            if let scope = await sessionContextStore.scope() {
                await loadRestoredState(scope: scope)
            } else {
                await loadAuthenticatedState()
            }
        }
    }

    private func beginSessionResolution(authStore: KeychainAuthStore) {
        route = .launching
        bootstrapTask?.cancel()
        bootstrapTask = Task { [weak self] in
            guard let self else { return }
            do {
                guard let token = try await authStore.token(), !token.isEmpty else {
                    route = .signedOut
                    return
                }
                try Task.checkCancellation()
                if let scope = await sessionContextStore.scope() {
                    await loadRestoredState(scope: scope)
                } else {
                    await loadAuthenticatedState()
                }
            } catch is CancellationError {
                return
            } catch {
                showSessionUnavailable(error)
            }
        }
    }

    func authenticated() {
        beginFreshBootstrap()
    }

    func reloadAfterOnboardingStep() {
        beginFreshBootstrap()
    }

    func reloadAfterFamilyChange() {
        beginFreshBootstrap()
    }

    private func beginFreshBootstrap() {
        route = .launching
        bootstrapTask?.cancel()
        bootstrapTask = Task { [weak self] in await self?.loadAuthenticatedState() }
    }

    func accountProfileChanged(_ profile: AccountProfile) {
        guard let value = bootstrap.value else { return }
        let updated = BootstrapResponse(
            user: AppUser(id: profile.id, phone: profile.phone, displayName: profile.displayName),
            families: value.families,
            activeFamilyID: value.activeFamilyID,
            onboarding: value.onboarding,
            unreadCount: value.unreadCount,
            revision: value.revision
        )
        bootstrap.value = updated
        persistContext(for: updated)
    }

    func restore(scope: CacheScope) {
        route = .launching
        bootstrapTask?.cancel()
        bootstrapTask = Task { [weak self] in
            await self?.loadRestoredState(scope: scope)
        }
    }

    func signOut() {
        bootstrapTask?.cancel()
        bootstrap = Loadable()
        route = .signedOut
        Task { await sessionContextStore.clear() }
    }

    private func applyBootstrap(_ state: Loadable<BootstrapResponse>) {
        bootstrap = state
        guard let value = state.value else {
            if !state.isRefreshing { route = .sessionUnavailable }
            return
        }
        persistContext(for: value)
        route = value.onboarding.complete ? .main : .onboarding(value.onboarding.nextStep)
    }

    private func loadAuthenticatedState() async {
        do {
            let value = try await repository.fetchBootstrap()
            try Task.checkCancellation()
            bootstrap = Loadable(value: value, isRefreshing: false, staleReason: nil)
            persistContext(for: value)
            if value.onboarding.complete {
                route = .main
            } else {
                route = .onboarding(value.onboarding.nextStep)
            }
        } catch is CancellationError {
            return
        } catch APIError.unauthorized {
            await invalidateSession()
        } catch {
            showSessionUnavailable(error)
        }
    }

    private func loadRestoredState(scope: CacheScope) async {
        do {
            try await repository.bootstrap(scope: scope) { state in
                await self.applyBootstrap(state)
            }
        } catch is CancellationError {
            return
        } catch APIError.unauthorized {
            await invalidateSession()
        } catch {
            showSessionUnavailable(error)
        }
    }

    private func showSessionUnavailable(_ error: Error) {
        bootstrap = Loadable(value: nil, isRefreshing: false, staleReason: sessionUnavailableMessage(for: error))
        route = .sessionUnavailable
    }

    private func invalidateSession() async {
        route = .launching
        bootstrap = Loadable()
        await sessionContextStore.clear()
        route = .signedOut
    }

    private func sessionUnavailableMessage(for error: Error) -> String {
        if let apiError = error as? APIError {
            return apiError.errorDescription ?? "暂时无法连接服务，请重新加载。"
        }
        if let urlError = error as? URLError {
            switch urlError.code {
            case .timedOut:
                return "连接服务器超时，请重新加载。"
            case .notConnectedToInternet, .networkConnectionLost:
                return "当前网络不可用，请检查网络后重新加载。"
            default:
                return "暂时无法连接服务，请重新加载。"
            }
        }
        return "暂时无法连接服务，请重新加载。"
    }

    private func persistContext(for value: BootstrapResponse) {
        let scope = CacheScope(userID: value.user.id, familyID: value.activeFamilyID ?? "onboarding")
        Task { [repository, sessionContextStore] in
            await sessionContextStore.save(scope: scope)
            await repository.cacheBootstrap(value, scope: scope)
        }
    }
}
