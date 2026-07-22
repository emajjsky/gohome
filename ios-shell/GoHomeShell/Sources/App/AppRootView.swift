import SwiftUI

struct AppRootView: View {
    @StateObject private var model: AppModel
    private let environment: AppEnvironment

    init(environment: AppEnvironment) {
        self.environment = environment
        _model = StateObject(wrappedValue: AppModel(
            repository: environment.repository,
            sessionContextStore: environment.sessionContextStore
        ))
    }

    var body: some View {
        Group {
            switch model.route {
            case .launching, .signedOut:
                AuthView(viewModel: AuthViewModel(
                    client: environment.apiClient,
                    authStore: environment.authStore,
                    onAuthenticated: { model.authenticated() }
                ))
            case let .onboarding(step):
                OnboardingCoordinatorView(
                    step: step,
                    familyID: model.bootstrap.value?.activeFamilyID,
                    service: OnboardingService(client: environment.apiClient),
                    onComplete: { model.reloadAfterOnboardingStep() }
                )
            case .main:
                if let bootstrap = model.bootstrap.value, let familyID = bootstrap.activeFamilyID {
                    MainTabView(
                        repository: environment.repository,
                        scope: CacheScope(userID: bootstrap.user.id, familyID: familyID),
                        unreadCount: bootstrap.unreadCount,
                        apiClient: environment.apiClient
                    )
                } else {
                    MainTabView.preview
                }
            }
        }
        .task {
            model.start(authStore: environment.authStore)
        }
    }
}
