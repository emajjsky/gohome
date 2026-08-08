import SwiftUI

struct CameraManagementView: View {
    @ObservedObject var model: ProfileViewModel
    let binding: DeviceBinding
    let camera: CameraConfig?

    @Environment(\.dismiss) private var dismiss
    @State private var confirmingDelete = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                CameraConfigurationForm(
                    binding: binding,
                    existing: camera,
                    onSave: save,
                    onComplete: { dismiss() }
                )
                if camera != nil {
                    Button(role: .destructive) { confirmingDelete = true } label: {
                        HStack(spacing: 8) {
                            if let camera, model.deviceActionID == "camera-\(camera.id)" { ProgressView().controlSize(.small) }
                            Label(
                                camera.map { model.deviceActionID == "camera-\($0.id)" } == true ? "正在删除" : "删除摄像头",
                                systemImage: "trash"
                            )
                        }
                            .font(.system(size: 14, weight: .semibold))
                            .frame(maxWidth: .infinity, minHeight: 48)
                    }
                    .disabled(model.deviceActionID != nil)
                }
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 18)
            .padding(.bottom, 28)
        }
        .background(GoHomeTheme.paper)
        .profileNavigationTitle(camera == nil ? "添加摄像头" : "编辑摄像头")
        .confirmationDialog("删除这路摄像头？", isPresented: $confirmingDelete, titleVisibility: .visible) {
            Button("删除摄像头", role: .destructive) { deleteCamera() }
            Button("取消", role: .cancel) {}
        } message: {
            Text("历史安全事件仍会保留，但不再关联这路实时画面。")
        }
    }

    private func save(_ values: CameraConnectionValues) async -> Bool {
        let success: Bool
        if let camera {
            success = await model.updateCamera(
                camera,
                name: values.name,
                room: values.room,
                streamURL: values.streamURL,
                username: values.username,
                password: values.password,
                enabled: values.enabled
            )
        } else {
            success = await model.createCamera(
                binding: binding,
                name: values.name,
                room: values.room,
                streamURL: values.streamURL,
                username: values.username,
                password: values.password
            )
        }
        return success
    }

    private func deleteCamera() {
        guard let camera else { return }
        Task {
            if await model.deleteCamera(camera) { dismiss() }
        }
    }
}
