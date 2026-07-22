import SwiftUI

struct OnboardingCoordinatorView: View {
    let step: OnboardingStep
    let familyID: String?
    let service: OnboardingService
    let onComplete: @MainActor () -> Void

    var body: some View {
        switch step {
        case .family:
            FamilySetupView(service: service, onComplete: onComplete)
        case .profile:
            ProfileSetupView(familyID: familyID, service: service, onComplete: onComplete)
        case .device:
            DeviceBindingView(familyID: familyID, service: service, onComplete: onComplete)
        case .camera:
            CameraSetupView(familyID: familyID, service: service, onComplete: onComplete)
        case .complete:
            ProgressView("正在进入")
                .task { onComplete() }
        }
    }
}

struct OnboardingPage<Content: View>: View {
    let index: Int
    let title: String
    let subtitle: String
    @ViewBuilder let content: () -> Content

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    Text("回家")
                        .font(.system(size: 17, weight: .bold, design: .rounded))
                    Spacer()
                    Text("\(index) / 4")
                        .font(.system(size: 13, weight: .semibold, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
                .padding(.bottom, 38)

                HStack(spacing: 6) {
                    ForEach(1...4, id: \.self) { step in
                        Capsule()
                            .fill(step <= index ? Color.yellow.opacity(0.9) : Color.black.opacity(0.08))
                            .frame(height: 4)
                    }
                }
                .padding(.bottom, 34)

                Text(title)
                    .font(.system(size: 32, weight: .bold, design: .rounded))
                    .foregroundStyle(.black)
                Text(subtitle)
                    .font(.system(size: 15))
                    .foregroundStyle(.black.opacity(0.5))
                    .padding(.top, 10)

                content()
                    .padding(.top, 32)
            }
            .padding(.horizontal, 24)
            .padding(.top, 22)
            .padding(.bottom, 36)
        }
        .scrollDismissesKeyboard(.interactively)
        .background(Color.white.ignoresSafeArea())
    }
}

struct OnboardingField: View {
    let title: String
    let placeholder: String
    @Binding var text: String
    var keyboard: UIKeyboardType = .default

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 13, weight: .semibold))
            TextField(placeholder, text: $text)
                .keyboardType(keyboard)
                .padding(.horizontal, 15)
                .frame(height: 52)
                .background(Color.black.opacity(0.045), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        }
    }
}

struct OnboardingPrimaryButton: View {
    let title: String
    let isLoading: Bool
    let isDisabled: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if isLoading { ProgressView().tint(.white) }
                Text(isLoading ? "处理中" : title)
            }
            .font(.system(size: 16, weight: .bold))
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity)
            .frame(height: 54)
            .background(Color.black, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        }
        .disabled(isDisabled)
        .opacity(isDisabled ? 0.35 : 1)
    }
}

struct OnboardingError: View {
    let message: String?

    var body: some View {
        if let message {
            Text(message)
                .font(.system(size: 13))
                .foregroundStyle(Color.red.opacity(0.85))
                .padding(.top, 14)
        }
    }
}
