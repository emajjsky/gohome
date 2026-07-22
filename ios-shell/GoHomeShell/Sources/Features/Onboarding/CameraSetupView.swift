import SwiftUI

struct CameraSetupView: View {
    let familyID: String?
    let service: OnboardingService
    let onComplete: @MainActor () -> Void
    @State private var name = "客厅主视"
    @State private var room = "客厅"
    @State private var streamURL = ""
    @State private var deviceID: String?
    @State private var isSaving = false
    @State private var errorMessage: String?

    var body: some View {
        OnboardingPage(index: 4, title: "添加第一路画面", subtitle: "App 保存配置，盒子负责在家中接入摄像头。") {
            VStack(alignment: .leading, spacing: 18) {
                OnboardingField(title: "画面名称", placeholder: "客厅主视", text: $name)
                OnboardingField(title: "安装位置", placeholder: "客厅", text: $room)
                OnboardingField(title: "视频地址", placeholder: "可选，留空由盒子接入", text: $streamURL)
                    .textInputAutocapitalization(.never)
                Text("不要求手机直接连接摄像头。保存后，盒子会同步配置并完成实际抓帧验证。")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                OnboardingError(message: errorMessage)
                OnboardingPrimaryButton(title: "测试并保存", isLoading: isSaving, isDisabled: isSaving || !canSubmit, action: save)
                    .padding(.top, 8)
            }
        }
        .accessibilityIdentifier("onboarding-camera")
        .task { await loadDevice() }
    }

    private var canSubmit: Bool {
        familyID != nil && !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !room.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func loadDevice() async {
        guard let familyID else { return }
        if let binding = try? await service.bindings(familyID: familyID) {
            deviceID = binding.first?.deviceID
        }
    }

    private func save() {
        guard let familyID, canSubmit else { return }
        isSaving = true
        errorMessage = nil
        let normalizedURL = streamURL.trimmingCharacters(in: .whitespacesAndNewlines)
        Task {
            do {
                let result = try await service.testCamera(familyID: familyID, streamURL: normalizedURL)
                guard result.ok else { throw CameraSetupError.connectionFailed }
                _ = try await service.saveCamera(
                    familyID: familyID,
                    deviceID: deviceID,
                    name: name.trimmingCharacters(in: .whitespacesAndNewlines),
                    room: room.trimmingCharacters(in: .whitespacesAndNewlines),
                    streamURL: normalizedURL
                )
                onComplete()
            } catch {
                errorMessage = error.localizedDescription
            }
            isSaving = false
        }
    }
}

private enum CameraSetupError: LocalizedError {
    case connectionFailed
    var errorDescription: String? { "摄像头连接测试未通过，请检查配置后重试。" }
}
