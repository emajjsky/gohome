import SwiftUI

struct FamilySetupView: View {
    enum Mode: String, CaseIterable, Identifiable {
        case create, join
        var id: String { rawValue }
        var title: String { self == .create ? "创建家庭" : "加入家庭" }
    }

    let service: OnboardingService
    let onComplete: @MainActor () -> Void
    @State private var mode: Mode = .create
    @State private var familyName = ""
    @State private var joinCode = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    var body: some View {
        OnboardingPage(index: 1, title: "先建立一个家庭", subtitle: "家庭资料、设备和提醒都会在这里归属。") {
            VStack(alignment: .leading, spacing: 18) {
                Picker("家庭操作", selection: $mode) {
                    ForEach(Mode.allCases) { Text($0.title).tag($0) }
                }
                .pickerStyle(.segmented)

                if mode == .create {
                    OnboardingField(title: "家庭名称", placeholder: "例如：杭州的家", text: $familyName)
                } else {
                    OnboardingField(title: "家庭邀请码", placeholder: "输入 GH- 开头的邀请码", text: $joinCode)
                        .textInputAutocapitalization(.characters)
                }

                OnboardingError(message: errorMessage)
                OnboardingPrimaryButton(
                    title: mode == .create ? "创建并继续" : "加入并继续",
                    isLoading: isSubmitting,
                    isDisabled: isSubmitting || !canSubmit,
                    action: submit
                )
                .padding(.top, 10)
            }
        }
        .accessibilityIdentifier("onboarding-family")
    }

    private var canSubmit: Bool {
        mode == .create ? !familyName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty : joinCode.count >= 6
    }

    private func submit() {
        guard canSubmit, !isSubmitting else { return }
        isSubmitting = true
        errorMessage = nil
        Task {
            do {
                if mode == .create {
                    _ = try await service.createFamily(name: familyName.trimmingCharacters(in: .whitespacesAndNewlines))
                } else {
                    _ = try await service.joinFamily(code: joinCode.trimmingCharacters(in: .whitespacesAndNewlines))
                }
                onComplete()
            } catch {
                errorMessage = error.localizedDescription
            }
            isSubmitting = false
        }
    }
}
