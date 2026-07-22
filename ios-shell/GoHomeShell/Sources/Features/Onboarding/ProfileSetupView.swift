import SwiftUI

struct ProfileSetupView: View {
    let familyID: String?
    let service: OnboardingService
    let onComplete: @MainActor () -> Void
    @State private var displayName = ""
    @State private var relationship = "母亲"
    @State private var city = ""
    @State private var district = ""
    @State private var phone = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    private let relationships = ["母亲", "父亲", "祖父", "祖母", "亲属", "其他"]

    var body: some View {
        OnboardingPage(index: 2, title: "添加家庭成员", subtitle: "只填写必要信息，用于提醒和内容推荐。") {
            VStack(alignment: .leading, spacing: 18) {
                OnboardingField(title: "称呼", placeholder: "例如：李阿姨", text: $displayName)
                VStack(alignment: .leading, spacing: 8) {
                    Text("身份关系")
                        .font(.system(size: 13, weight: .semibold))
                    Menu {
                        ForEach(relationships, id: \.self) { item in
                            Button(item) { relationship = item }
                        }
                    } label: {
                        HStack {
                            Text(relationship)
                                .foregroundStyle(.black)
                            Spacer()
                            Image(systemName: "chevron.up.chevron.down")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(.secondary)
                        }
                        .padding(.horizontal, 15)
                        .frame(height: 52)
                        .background(Color.black.opacity(0.045), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    }
                }
                HStack(spacing: 12) {
                    OnboardingField(title: "城市", placeholder: "杭州", text: $city)
                    OnboardingField(title: "区域", placeholder: "可选", text: $district)
                }
                OnboardingField(title: "联系号码", placeholder: "用于重要提醒", text: $phone, keyboard: .phonePad)
                Text("号码仅用于家庭提醒，不会展示给其他家庭成员。")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)

                OnboardingError(message: errorMessage)
                OnboardingPrimaryButton(title: "保存并继续", isLoading: isSubmitting, isDisabled: isSubmitting || !canSubmit, action: submit)
                    .padding(.top, 8)
            }
        }
        .accessibilityIdentifier("onboarding-profile")
    }

    private var normalizedPhone: String { phone.filter(\.isNumber) }
    private var canSubmit: Bool {
        familyID != nil && !displayName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && normalizedPhone.count >= 7
    }

    private func submit() {
        guard let familyID, canSubmit else { return }
        isSubmitting = true
        errorMessage = nil
        let payload = ProfilePayload(
            displayName: displayName.trimmingCharacters(in: .whitespacesAndNewlines),
            relationship: relationship,
            city: city.trimmingCharacters(in: .whitespacesAndNewlines),
            district: district.trimmingCharacters(in: .whitespacesAndNewlines),
            phone: normalizedPhone,
            mobilePhone: normalizedPhone,
            homePhone: ""
        )
        Task {
            do {
                _ = try await service.saveProfile(familyID: familyID, profile: payload)
                onComplete()
            } catch {
                errorMessage = error.localizedDescription
            }
            isSubmitting = false
        }
    }
}
