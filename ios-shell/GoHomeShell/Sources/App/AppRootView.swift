import SwiftUI

struct AppRootView: View {
    @StateObject private var model: AppModel
    private let environment: AppEnvironment

    init(environment: AppEnvironment) {
        self.environment = environment
        _model = StateObject(wrappedValue: AppModel(repository: environment.repository))
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
                OnboardingPlaceholder(step: step)
            case .main:
                MainPlaceholder()
            }
        }
        .task {
            model.start()
        }
    }
}

private struct OnboardingPlaceholder: View {
    let step: OnboardingStep

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("开始配置")
                .font(.largeTitle.bold())
            Text(step.title)
                .font(.title3)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .padding(24)
    }
}

private struct MainPlaceholder: View {
    var body: some View {
        Text("回家")
            .font(.largeTitle.bold())
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private extension OnboardingStep {
    var title: String {
        switch self {
        case .family: return "创建家庭"
        case .profile: return "添加家庭成员"
        case .device: return "绑定守护盒子"
        case .camera: return "配置摄像头"
        case .complete: return "即将完成"
        }
    }
}
