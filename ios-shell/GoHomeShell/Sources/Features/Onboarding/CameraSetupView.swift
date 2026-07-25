import SwiftUI

struct CameraSetupView: View {
    let familyID: String?
    let service: OnboardingService
    let onComplete: @MainActor () -> Void
    @State private var binding: DeviceBinding?
    @State private var errorMessage: String?

    var body: some View {
        OnboardingPage(index: 4, title: "添加第一路画面", subtitle: "App 保存配置，盒子负责在家中接入摄像头。") {
            Group {
                if let binding {
                    CameraConfigurationForm(binding: binding, onSave: save)
                } else {
                    ProfileEmptyRow(symbol: "shippingbox", title: errorMessage ?? "正在确认家庭盒子")
                }
                OnboardingError(message: errorMessage)
            }
        }
        .accessibilityIdentifier("onboarding-camera")
        .task { await loadDevice() }
    }

    private func loadDevice() async {
        if ProcessInfo.processInfo.arguments.contains("-uiTestState") {
            binding = DeviceBinding(
                id: "ui-test-binding",
                familyID: familyID ?? "ui-test-family",
                deviceID: "ui-test-box",
                deviceName: "演示守护盒子",
                status: "online"
            )
            return
        }
        guard let familyID else { return }
        do {
            binding = try await service.bindings(familyID: familyID).first
            if binding == nil { errorMessage = "请先完成盒子绑定。" }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func save(_ values: CameraConnectionValues) async -> Bool {
        guard let familyID, let binding else { return false }
        do {
            _ = try await service.saveCamera(
                familyID: familyID,
                deviceID: binding.deviceID,
                name: values.name,
                room: values.room,
                streamURL: values.streamURL,
                username: values.username,
                password: values.password
            )
            onComplete()
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }
}
