import Foundation

@MainActor
final class AppModel: ObservableObject {
    @Published private(set) var route: AppRoute = .launching
    @Published private(set) var bootstrap = Loadable<BootstrapResponse>()

    private let repository: AppRepository
    private var bootstrapTask: Task<Void, Never>?

    init(repository: AppRepository) {
        self.repository = repository
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
    }

    private func applyBootstrap(_ state: Loadable<BootstrapResponse>) {
        bootstrap = state
        guard let value = state.value else {
            if !state.isRefreshing { route = .signedOut }
            return
        }
        route = value.onboarding.complete ? .main : .onboarding(value.onboarding.nextStep)
    }
}
