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
                    let scope = CacheScope(userID: bootstrap.user.id, familyID: familyID)
                    MainTabView(
                        repository: environment.repository,
                        scope: scope,
                        unreadCount: bootstrap.unreadCount,
                        apiClient: environment.apiClient,
                        user: bootstrap.user,
                        family: bootstrap.families.first(where: { $0.id == familyID })
                            ?? AppFamily(id: familyID, name: "我的家庭", role: nil),
                        onSignOut: {
                            model.signOut()
                            Task { await environment.clearAuthenticatedSession(scope: scope) }
                        }
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
