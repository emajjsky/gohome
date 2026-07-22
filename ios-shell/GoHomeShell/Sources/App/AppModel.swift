import Foundation

@MainActor
final class AppModel: ObservableObject {
    @Published private(set) var route: AppRoute = .launching
    @Published private(set) var bootstrap = Loadable<BootstrapResponse>()

    private let repository: AppRepository
    private let sessionContextStore: SessionContextStore
    private var bootstrapTask: Task<Void, Never>?

    init(repository: AppRepository, sessionContextStore: SessionContextStore) {
        self.repository = repository
        self.sessionContextStore = sessionContextStore
    }

    func start(authStore: KeychainAuthStore) {
        let arguments = ProcessInfo.processInfo.arguments
        if arguments.contains("-uiTestState") {
            if let rawStep = arguments.first(where: { $0.hasPrefix("-uiTestOnboardingStep=") })?
                .split(separator: "=", maxSplits: 1).last,
               let step = OnboardingStep(rawValue: String(rawStep)) {
                route = .onboarding(step)
            } else {
                route = .signedOut
            }
            return
        }
        Task { [weak self] in
            do {
                guard let token = try await authStore.token(), !token.isEmpty else {
                    self?.route = .signedOut
                    return
                }
                if let scope = await self?.sessionContextStore.scope() {
                    await self?.restore(scope: scope)
                } else {
                    await self?.loadAuthenticatedState()
                }
            } catch {
                self?.route = .signedOut
            }
        }
    }

    func authenticated() {
        Task { [weak self] in await self?.loadAuthenticatedState() }
    }

    func reloadAfterOnboardingStep() {
        Task { [weak self] in await self?.loadAuthenticatedState() }
    }

    func restore(scope: CacheScope) {
        bootstrapTask?.cancel()
        bootstrapTask = Task { [repository] in
            await repository.bootstrap(scope: scope) { state in
                await self.applyBootstrap(state)
            }
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
            if !state.isRefreshing { route = .signedOut }
            return
        }
        persistContext(for: value)
        route = value.onboarding.complete ? .main : .onboarding(value.onboarding.nextStep)
    }

    private func loadAuthenticatedState() async {
        do {
            let value = try await repository.fetchBootstrap()
            bootstrap = Loadable(value: value, isRefreshing: false, staleReason: nil)
            persistContext(for: value)
            if value.onboarding.complete {
                route = .main
            } else {
                route = .onboarding(value.onboarding.nextStep)
            }
        } catch {
            route = .signedOut
        }
    }

    private func persistContext(for value: BootstrapResponse) {
        let scope = CacheScope(userID: value.user.id, familyID: value.activeFamilyID ?? "onboarding")
        Task { [repository, sessionContextStore] in
            await sessionContextStore.save(scope: scope)
            await repository.cacheBootstrap(value, scope: scope)
        }
    }
}
