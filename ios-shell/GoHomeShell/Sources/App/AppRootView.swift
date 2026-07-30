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
            case .launching:
                AppLaunchView()
            case .signedOut:
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
                        apiClient: environment.apiClient,
                        user: bootstrap.user,
                        family: bootstrap.families.first(where: { $0.id == familyID })
                            ?? AppFamily(id: familyID, name: "我的家庭", role: nil),
                        pushNotifications: environment.pushNotifications,
                        onSignOut: {
                            model.signOut()
                            Task {
                                await environment.pushNotifications.deactivate()
                                await environment.clearAuthenticatedSession(scope: scope)
                            }
                        },
                        onAccountDeleted: {
                            model.signOut()
                            Task {
                                await environment.pushNotifications.deactivate()
                                await environment.clearDeletedAccountSession()
                            }
                        },
                        onFamilyChanged: {
                            model.reloadAfterFamilyChange()
                        },
                        onAccountProfileChanged: { profile in
                            model.accountProfileChanged(profile)
                        }
                    )
                } else {
                    MainTabView.preview
                }
            }
        }
        .animation(.easeOut(duration: 0.18), value: model.route)
        .task {
            model.start(authStore: environment.authStore)
        }
        .task(id: model.pushFamilyID) {
            guard let familyID = model.pushFamilyID else { return }
            await environment.pushNotifications.activate(familyID: familyID)
        }
    }
}

private struct AppLaunchView: View {
    var body: some View {
        ZStack {
            Color.white.ignoresSafeArea()
            ProgressView()
                .tint(.black)
                .controlSize(.regular)
        }
        .accessibilityLabel("正在进入回家")
    }
}
