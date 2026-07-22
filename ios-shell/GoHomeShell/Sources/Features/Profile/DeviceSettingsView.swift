import SwiftUI

struct DeviceSettingsView: View {
    @ObservedObject var model: ProfileViewModel

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
    }

    private var boxSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            GoHomeSectionHeader(title: "家庭盒子")
            if let binding = model.state.value?.bindings.first {
                HStack(spacing: 13) {
                    Image(systemName: "shippingbox.fill")
                        .font(.system(size: 19, weight: .semibold))
                        .foregroundStyle(GoHomeTheme.ink)
                        .frame(width: 44, height: 44)
                        .background(GoHomeTheme.paleGinger, in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
                    VStack(alignment: .leading, spacing: 4) {
                        Text(binding.deviceName)
                            .font(.system(size: 16, weight: .bold))
                            .foregroundStyle(GoHomeTheme.ink)
                        Label(deviceStatus(binding), systemImage: "circle.fill")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(deviceOnline(binding) ? Color.green : GoHomeTheme.mutedInk)
                    }
                    Spacer()
                }
                .padding(.vertical, 12)
                .overlay(alignment: .top) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
                .overlay(alignment: .bottom) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
            } else {
                ProfileEmptyRow(symbol: "shippingbox", title: "尚未绑定家庭盒子")
            }
        }
    }

    private var cameraSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            GoHomeSectionHeader(
                title: "摄像头",
                detail: model.state.value.map { "\($0.cameras.count) 路" }
            )
            if let cameras = model.state.value?.cameras, !cameras.isEmpty {
                VStack(spacing: 0) {
                    ForEach(Array(cameras.enumerated()), id: \.element.id) { index, camera in
                        cameraRow(camera)
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

    private func cameraRow(_ camera: CameraConfig) -> some View {
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
        switch camera.status.lowercased() {
        case "online", "active", "connected": return "在线"
        case "pending", "syncing": return "配置中"
        default: return "离线"
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
