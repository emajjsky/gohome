import SwiftUI

struct DeviceSettingsView: View {
    @ObservedObject var model: ProfileViewModel
    let onboardingService: OnboardingService?

    @State private var showingBoxBinding = false
    @State private var bindingToRemove: DeviceBinding?
    @State private var cameraBindingToAdd: DeviceBinding?
    @State private var choosingCameraBox = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                boxSection
                cameraSection
                NavigationLink {
                    RuleSettingsView(model: model)
                } label: {
                    ProfileNavigationRow(
                        symbol: "viewfinder",
                        title: "守护规则",
                        value: model.canEditRules ? "可配置" : "仅查看"
                    )
                }
                .overlay(alignment: .top) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
                .overlay(alignment: .bottom) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 18)
            .padding(.bottom, 28)
        }
        .background(GoHomeTheme.paper)
        .profileNavigationTitle("设备与守护")
        .sheet(isPresented: $showingBoxBinding) {
            if let onboardingService {
                NavigationStack {
                    DeviceBindingView(
                        familyID: model.family.id,
                        service: onboardingService,
                        onComplete: {
                            showingBoxBinding = false
                            model.refresh()
                        },
                        presentation: .management
                    )
                }
            }
        }
        .sheet(item: $cameraBindingToAdd) { binding in
            NavigationStack {
                CameraManagementView(model: model, binding: binding, camera: nil)
            }
        }
        .confirmationDialog(
            "选择摄像头连接的盒子",
            isPresented: $choosingCameraBox,
            titleVisibility: .visible
        ) {
            ForEach(model.state.value?.bindings ?? []) { binding in
                Button(binding.deviceName) { cameraBindingToAdd = binding }
            }
            Button("取消", role: .cancel) {}
        }
        .confirmationDialog(
            "解除这台盒子的家庭绑定？",
            isPresented: Binding(
                get: { bindingToRemove != nil },
                set: { if !$0 { bindingToRemove = nil } }
            ),
            titleVisibility: .visible,
            presenting: bindingToRemove
        ) { binding in
            Button("解除绑定", role: .destructive) { unbind(binding) }
            Button("取消", role: .cancel) {}
        } message: { binding in
            Text("“\(binding.deviceName)”下的摄像头配置会同时移除，历史安全事件仍保留。")
        }
    }

    private var boxSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                GoHomeSectionHeader(title: "家庭盒子")
                Spacer()
                if model.canManageDevices, onboardingService != nil {
                    Button { showingBoxBinding = true } label: {
                        Image(systemName: "plus")
                            .font(.system(size: 14, weight: .bold))
                            .frame(width: 34, height: 34)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(GoHomeTheme.ink)
                    .accessibilityLabel("添加家庭盒子")
                }
            }
            if let bindings = model.state.value?.bindings, !bindings.isEmpty {
                VStack(spacing: 0) {
                    ForEach(bindings) { binding in
                        HStack(spacing: 13) {
                            Image(systemName: "shippingbox.fill")
                                .font(.system(size: 18, weight: .semibold))
                                .foregroundStyle(GoHomeTheme.ink)
                                .frame(width: 42, height: 42)
                                .background(GoHomeTheme.paleGinger, in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
                            VStack(alignment: .leading, spacing: 4) {
                                Text(binding.deviceName)
                                    .font(.system(size: 15, weight: .bold))
                                    .foregroundStyle(GoHomeTheme.ink)
                                Label(deviceStatus(binding), systemImage: "circle.fill")
                                    .font(.system(size: 11, weight: .medium))
                                    .foregroundStyle(deviceOnline(binding) ? Color.green : GoHomeTheme.mutedInk)
                            }
                            Spacer()
                            if model.canManageDevices {
                                Button(role: .destructive) { bindingToRemove = binding } label: {
                                    Label("解除绑定", systemImage: "shippingbox.and.arrow.backward")
                                        .font(.system(size: 12, weight: .semibold))
                                        .padding(.vertical, 10)
                                }
                                .buttonStyle(.plain)
                                .foregroundStyle(.red)
                                .disabled(model.deviceActionID != nil)
                                .accessibilityLabel("解除绑定：\(binding.deviceName)")
                            }
                        }
                        .frame(minHeight: 64)
                        Divider().overlay(GoHomeTheme.softLine)
                    }
                }
                .overlay(alignment: .top) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
            } else {
                ProfileEmptyRow(symbol: "shippingbox", title: "尚未绑定家庭盒子")
            }
        }
    }

    private var cameraSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                GoHomeSectionHeader(
                    title: "摄像头",
                    detail: model.state.value.map { "\($0.cameras.count) 路" }
                )
                Spacer()
                if model.canManageDevices, !(model.state.value?.bindings.isEmpty ?? true) {
                    Button(action: addCamera) {
                        Image(systemName: "plus")
                            .font(.system(size: 14, weight: .bold))
                            .frame(width: 34, height: 34)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(GoHomeTheme.ink)
                    .accessibilityLabel("添加摄像头")
                }
            }
            if let cameras = model.state.value?.cameras, !cameras.isEmpty {
                VStack(spacing: 0) {
                    ForEach(Array(cameras.enumerated()), id: \.element.id) { index, camera in
                        if model.canManageDevices, let binding = binding(for: camera) {
                            NavigationLink {
                                CameraManagementView(model: model, binding: binding, camera: camera)
                            } label: {
                                cameraRow(camera, showsDisclosure: true)
                            }
                            .buttonStyle(.plain)
                        } else {
                            cameraRow(camera, showsDisclosure: false)
                        }
                        if index < cameras.count - 1 {
                            Rectangle().fill(GoHomeTheme.softLine).frame(height: 1)
                                .padding(.leading, 44)
                        }
                    }
                }
                .overlay(alignment: .top) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
                .overlay(alignment: .bottom) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
            } else {
                ProfileEmptyRow(symbol: "video", title: "尚未配置摄像头")
            }
        }
    }

    private func cameraRow(_ camera: CameraConfig, showsDisclosure: Bool) -> some View {
        HStack(spacing: 12) {
            Image(systemName: "video.fill")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(GoHomeTheme.ink)
                .frame(width: 32, height: 32)
                .background(GoHomeTheme.paleGinger, in: RoundedRectangle(cornerRadius: 6, style: .continuous))
            VStack(alignment: .leading, spacing: 3) {
                Text(camera.name)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.ink)
                Text(camera.room.isEmpty ? "未设置位置" : camera.room)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
            Spacer()
            Text(cameraStatus(camera))
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(camera.status.lowercased() == "online" ? Color.green : GoHomeTheme.mutedInk)
            if showsDisclosure {
                Image(systemName: "chevron.right")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
        }
        .frame(minHeight: 58)
    }

    private func deviceOnline(_ binding: DeviceBinding) -> Bool {
        ["online", "active", "connected"].contains(binding.status.lowercased())
    }

    private func deviceStatus(_ binding: DeviceBinding) -> String {
        deviceOnline(binding) ? "在线" : "离线"
    }

    private func cameraStatus(_ camera: CameraConfig) -> String {
        if !camera.enabled { return "已暂停" }
        switch camera.status.lowercased() {
        case "online", "active", "connected": return "在线"
        case "pending", "syncing", "pending_edge_sync", "pending_edge_verify", "pending_edge_setup": return "配置中"
        default: return "离线"
        }
    }

    private func binding(for camera: CameraConfig) -> DeviceBinding? {
        let bindings = model.state.value?.bindings ?? []
        return bindings.first(where: { $0.deviceID == camera.deviceID }) ?? bindings.first
    }

    private func unbind(_ binding: DeviceBinding) {
        Task { _ = await model.unbindDevice(binding) }
    }

    private func addCamera() {
        let bindings = model.state.value?.bindings ?? []
        guard !bindings.isEmpty else { return }
        if bindings.count == 1 {
            cameraBindingToAdd = bindings[0]
        } else {
            choosingCameraBox = true
        }
    }
}

struct RuleSettingsView: View {
    @ObservedObject var model: ProfileViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                HStack(spacing: 10) {
                    Image(systemName: model.canEditRules ? "checkmark.shield.fill" : "lock.fill")
                        .foregroundStyle(GoHomeTheme.ink)
                    Text(model.canEditRules ? "家庭创建者可调整" : "当前账号仅可查看")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }

                if let rules = model.state.value?.rules {
                    ProfileSection(title: "检测频率") {
                        ruleNumber(
                            "抽帧间隔",
                            value: rules.captureIntervalSeconds,
                            range: 1...60,
                            step: 1,
                            formatted: "\(rules.captureIntervalSeconds) 秒"
                        ) {
                            var next = rules; next.captureIntervalSeconds = $0; model.saveRules(next)
                        }
                        ruleNumber(
                            "静止阈值",
                            value: rules.noMotionSeconds,
                            range: 10...86_400,
                            step: 30,
                            formatted: durationText(rules.noMotionSeconds)
                        ) {
                            var next = rules; next.noMotionSeconds = $0; model.saveRules(next)
                        }
                        ruleNumber(
                            "无人阈值",
                            value: rules.noPersonSeconds,
                            range: 10...86_400,
                            step: 30,
                            formatted: durationText(rules.noPersonSeconds)
                        ) {
                            var next = rules; next.noPersonSeconds = $0; model.saveRules(next)
                        }
                    }

                    ProfileSection(title: "视觉守护") {
                        ruleToggle("人物出现", symbol: "person.fill", value: rules.personDetectionEnabled) {
                            var next = rules; next.personDetectionEnabled = $0; model.saveRules(next)
                        }
                        ruleToggle("姿态与跌倒", symbol: "figure.fall", value: rules.fallDetectionEnabled) {
                            var next = rules; next.fallDetectionEnabled = $0; model.saveRules(next)
                        }
                        ruleToggle("活动变化", symbol: "figure.walk.motion", value: rules.activityDetectionEnabled) {
                            var next = rules; next.activityDetectionEnabled = $0; model.saveRules(next)
                        }
                        ruleToggle("烟火风险", symbol: "flame.fill", value: rules.fireDetectionEnabled) {
                            var next = rules; next.fireDetectionEnabled = $0; model.saveRules(next)
                        }
                    }

                    ProfileSection(title: "设备状态") {
                        ruleToggle("画面异常", symbol: "rectangle.slash", value: rules.blackScreenEnabled) {
                            var next = rules; next.blackScreenEnabled = $0; model.saveRules(next)
                        }
                        ruleToggle("长时间静止", symbol: "pause.rectangle", value: rules.noMotionEnabled) {
                            var next = rules; next.noMotionEnabled = $0; model.saveRules(next)
                        }
                        ruleToggle("设备离线", symbol: "wifi.slash", value: rules.offlineEnabled) {
                            var next = rules; next.offlineEnabled = $0; model.saveRules(next)
                        }
                    }

                    ProfileSection(title: "提醒") {
                        ruleToggle("安全事件提醒", symbol: "bell.fill", value: rules.notificationEnabled) {
                            var next = rules; next.notificationEnabled = $0; model.saveRules(next)
                        }
                    }
                } else {
                    ProfileEmptyRow(symbol: "viewfinder", title: "守护规则暂不可用")
                }

                if let error = model.inlineError {
                    Label(error, systemImage: "exclamationmark.circle")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 18)
            .padding(.bottom, 28)
        }
        .background(GoHomeTheme.paper)
        .profileNavigationTitle("守护规则")
    }

    private func ruleToggle(
        _ title: String,
        symbol: String,
        value: Bool,
        update: @escaping (Bool) -> Void
    ) -> some View {
        Toggle(isOn: Binding(get: { value }, set: update)) {
            Label(title, systemImage: symbol)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(GoHomeTheme.ink)
        }
        .tint(GoHomeTheme.ginger)
        .frame(minHeight: 50)
        .disabled(!model.canEditRules || model.savingRules)
    }

    private func ruleNumber(
        _ title: String,
        value: Int,
        range: ClosedRange<Int>,
        step: Int,
        formatted: String,
        update: @escaping (Int) -> Void
    ) -> some View {
        Stepper(value: Binding(get: { value }, set: update), in: range, step: step) {
            HStack {
                Text(title)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.ink)
                Spacer()
                Text(formatted)
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
        }
        .frame(minHeight: 50)
        .disabled(!model.canEditRules || model.savingRules)
    }

    private func durationText(_ seconds: Int) -> String {
        if seconds >= 3_600, seconds.isMultiple(of: 3_600) { return "\(seconds / 3_600) 小时" }
        if seconds >= 60, seconds.isMultiple(of: 60) { return "\(seconds / 60) 分钟" }
        return "\(seconds) 秒"
    }
}

struct ProfileEmptyRow: View {
    let symbol: String
    let title: String

    var body: some View {
        Label(title, systemImage: symbol)
            .font(.system(size: 14, weight: .medium))
            .foregroundStyle(GoHomeTheme.mutedInk)
            .frame(maxWidth: .infinity, minHeight: 54, alignment: .leading)
            .overlay(alignment: .top) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
            .overlay(alignment: .bottom) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
    }
}
