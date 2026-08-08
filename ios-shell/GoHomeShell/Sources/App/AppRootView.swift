import SwiftUI

enum MainShellResolution: Equatable {
    case live(bootstrap: BootstrapResponse, family: AppFamily)
    case uiTestPreview
    case unavailable

    static func resolve(bootstrap: BootstrapResponse?, allowsUITestPreview: Bool) -> Self {
        if let bootstrap,
           let familyID = bootstrap.activeFamilyID,
           let family = bootstrap.families.first(where: { $0.id == familyID }) {
            return .live(bootstrap: bootstrap, family: family)
        }
        return allowsUITestPreview ? .uiTestPreview : .unavailable
    }
}

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
            case .sessionUnavailable:
                AppRecoveryView(
                    title: "暂时无法连接服务",
                    message: model.bootstrap.staleReason ?? "请检查网络后重新加载。",
                    accessibilityIdentifier: "session-unavailable",
                    retry: { model.retryAuthenticatedState() }
                )
            case let .onboarding(step):
                OnboardingCoordinatorView(
                    step: step,
                    familyID: model.bootstrap.value?.activeFamilyID,
                    service: OnboardingService(client: environment.apiClient),
                    onComplete: { model.reloadAfterOnboardingStep() }
                )
            case .main:
                switch MainShellResolution.resolve(
                    bootstrap: model.bootstrap.value,
                    allowsUITestPreview: ProcessInfo.processInfo.arguments.contains("-uiTestState")
                ) {
                case let .live(bootstrap, family):
                    let familyID = family.id
                    let scope = CacheScope(userID: bootstrap.user.id, familyID: familyID)
                    MainTabView(
                        repository: environment.repository,
                        scope: scope,
                        apiClient: environment.apiClient,
                        user: bootstrap.user,
                        family: family,
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
                case .uiTestPreview:
                    MainTabView.preview
                case .unavailable:
                    MainDataUnavailableView {
                        model.reloadAfterFamilyChange()
                    }
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

private struct MainDataUnavailableView: View {
    let retry: () -> Void

    var body: some View {
        AppRecoveryView(
            title: "家庭数据暂时无法读取",
            message: "请重新加载家庭数据。",
            accessibilityIdentifier: "main-data-unavailable",
            retry: retry
        )
    }
}

private struct AppRecoveryView: View {
    let title: String
    let message: String
    let accessibilityIdentifier: String
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.icloud")
                .font(.system(size: 30, weight: .medium))
                .foregroundStyle(GoHomeTheme.mutedInk)
            Text(title)
                .font(.system(size: 17, weight: .bold))
                .foregroundStyle(GoHomeTheme.ink)
            Text(message)
                .font(.system(size: 14))
                .foregroundStyle(GoHomeTheme.mutedInk)
                .multilineTextAlignment(.center)
            Button("重新加载", action: retry)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(.white)
                .frame(minWidth: 120, minHeight: 46)
                .background(GoHomeTheme.ink, in: RoundedRectangle(cornerRadius: GoHomeTheme.controlRadius, style: .continuous))
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(GoHomeTheme.paper.ignoresSafeArea())
        .accessibilityIdentifier(accessibilityIdentifier)
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
