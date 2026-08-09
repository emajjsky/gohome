import SwiftUI
import UIKit

struct ContentPreferencesView: View {
    @Environment(\.scenePhase) private var scenePhase
    @ObservedObject var model: ProfileViewModel
    @ObservedObject var pushNotifications: PushNotificationCoordinator
    @State private var editor: PreferencesEditor?
    private let availableInterests = ["天气", "本地资讯", "健康生活", "防诈骗", "戏曲", "家常", "节日"]

    private enum PreferencesEditor: String, Identifiable {
        case quietHours
        case products

        var id: String { rawValue }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                if let preferences = model.state.value?.carePreferences {
                    ProfileSection(title: "消息") {
                        preferenceToggle("安全事件推送", symbol: "bell", value: model.state.value?.rules.notificationEnabled ?? true) { enabled in
                            guard var rules = model.state.value?.rules else { return }
                            rules.notificationEnabled = enabled
                            model.saveRules(rules)
                        }
                        Button(action: openSystemNotificationSettings) {
                            ProfileNavigationRow(
                                symbol: "gearshape",
                                title: "系统通知权限",
                                value: pushNotifications.status.permissionSummary
                            )
                        }
                        .buttonStyle(.plain)
                        HStack(spacing: 12) {
                            Image(systemName: "bell.badge")
                                .font(.system(size: 15, weight: .semibold))
                                .frame(width: 24)
                            VStack(alignment: .leading, spacing: 3) {
                                Text("推送通道")
                                    .font(.system(size: 15, weight: .semibold))
                                Text(pushNotifications.status.channelSummary)
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundStyle(GoHomeTheme.mutedInk)
                            }
                            Spacer()
                            Text(pushNotifications.registrationActive ? "已连接" : "待连接")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundStyle(GoHomeTheme.mutedInk)
                        }
                        .foregroundStyle(GoHomeTheme.ink)
                        .frame(minHeight: 52)
                        Button {
                            Task { await pushNotifications.sendTest(familyID: model.family.id) }
                        } label: {
                            HStack(spacing: 12) {
                                Image(systemName: "paperplane")
                                    .font(.system(size: 15, weight: .semibold))
                                    .frame(width: 24)
                                Text("发送测试通知")
                                    .font(.system(size: 15, weight: .semibold))
                                Spacer()
                                if pushNotifications.testState.isSending {
                                    ProgressView().controlSize(.small)
                                } else {
                                    Image(systemName: "chevron.right")
                                        .font(.system(size: 11, weight: .bold))
                                        .foregroundStyle(GoHomeTheme.mutedInk)
                                }
                            }
                            .foregroundStyle(GoHomeTheme.ink)
                            .frame(minHeight: 52)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .disabled(pushNotifications.testState.isSending || pushNotifications.status.authorization != .allowed)
                        Button { editor = .quietHours } label: {
                            ProfileNavigationRow(
                                symbol: "moon",
                                title: "免打扰",
                                value: "\(preferences.quietHours.start) - \(preferences.quietHours.end)"
                            )
                        }
                        .buttonStyle(.plain)
                    }

                    ProfileSection(title: "首页内容") {
                        preferenceToggle("图文资讯", symbol: "newspaper", value: preferences.contentRecommendationsEnabled) {
                            var next = preferences; next.contentRecommendationsEnabled = $0; model.savePreferences(next)
                        }
                        preferenceToggle("可信来源", symbol: "checkmark.seal", value: preferences.contentSourcesEnabled) {
                            var next = preferences; next.contentSourcesEnabled = $0; model.savePreferences(next)
                        }
                    }

                    VStack(alignment: .leading, spacing: 12) {
                        GoHomeSectionHeader(title: "关注内容", detail: "按需推荐")
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 92), spacing: 8)], alignment: .leading, spacing: 8) {
                            ForEach(availableInterests, id: \.self) { interest in
                                let selected = preferences.interests.contains(interest)
                                Button {
                                    var next = preferences
                                    if selected {
                                        next.interests.removeAll { $0 == interest }
                                    } else {
                                        next.interests.append(interest)
                                    }
                                    model.savePreferences(next)
                                } label: {
                                    HStack(spacing: 6) {
                                        Image(systemName: selected ? "checkmark" : "plus")
                                        Text(interest)
                                    }
                                    .font(.system(size: 12, weight: .semibold))
                                    .foregroundStyle(selected ? GoHomeTheme.ink : GoHomeTheme.mutedInk)
                                    .frame(maxWidth: .infinity, minHeight: 36)
                                    .background(
                                        selected ? GoHomeTheme.paleGinger : GoHomeTheme.paper,
                                        in: RoundedRectangle(cornerRadius: GoHomeTheme.controlRadius, style: .continuous)
                                    )
                                    .overlay {
                                        RoundedRectangle(cornerRadius: GoHomeTheme.controlRadius, style: .continuous)
                                            .stroke(selected ? Color.clear : GoHomeTheme.line, lineWidth: 1)
                                    }
                                }
                                .buttonStyle(.plain)
                                .disabled(model.savingPreferences)
                            }
                        }
                    }

                    ProfileSection(title: "精选推荐") {
                        Button { editor = .products } label: {
                            ProfileNavigationRow(
                                symbol: "sparkles",
                                title: "推荐方向",
                                value: productPreferenceText
                            )
                        }
                        .buttonStyle(.plain)
                    }
                } else {
                    ProfileEmptyRow(symbol: "slider.horizontal.3", title: "偏好设置暂不可用")
                }

                if let error = model.inlineError {
                    Label(error, systemImage: "exclamationmark.circle")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
                if let message = pushNotifications.testState.message {
                    Label(message, systemImage: pushNotifications.testState == .queued ? "checkmark.circle" : "bell")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 18)
            .padding(.bottom, 28)
        }
        .background(GoHomeTheme.paper)
        .profileNavigationTitle("提醒与内容")
        .task { await pushNotifications.refreshStatus() }
        .onChange(of: scenePhase) { phase in
            if phase == .active {
                Task { await pushNotifications.refreshStatus() }
            }
        }
        .onDisappear { model.cancelInFlightPreferenceSaves() }
        .sheet(item: $editor) { destination in
            switch destination {
            case .quietHours:
                if let preferences = model.state.value?.carePreferences {
                    QuietHoursEditor(initial: preferences.quietHours) { quietHours in
                        var next = preferences
                        next.quietHours = quietHours
                        model.savePreferences(next)
                    }
                }
            case .products:
                ProductPreferencesEditor(
                    initial: model.state.value?.productPreferences ?? ProductPreferences(categories: [], needs: [])
                ) { model.saveProductPreferences($0) }
            }
        }
    }

    private func preferenceToggle(
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
        .disabled(model.savingPreferences || model.savingRules)
    }

    private var productPreferenceText: String {
        guard let preferences = model.state.value?.productPreferences else { return "尚未选择推荐方向" }
        let values = preferences.categories + preferences.needs
        return values.isEmpty ? "尚未选择推荐方向" : values.joined(separator: " · ")
    }

    private func openSystemNotificationSettings() {
        guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
        UIApplication.shared.open(url)
    }
}

private struct QuietHoursEditor: View {
    @Environment(\.dismiss) private var dismiss
    @State private var start: Date
    @State private var end: Date
    let onSave: (QuietHours) -> Void

    init(initial: QuietHours, onSave: @escaping (QuietHours) -> Void) {
        _start = State(initialValue: Self.date(from: initial.start))
        _end = State(initialValue: Self.date(from: initial.end))
        self.onSave = onSave
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                DatePicker("开始", selection: $start, displayedComponents: .hourAndMinute)
                    .frame(minHeight: 54)
                    .accessibilityIdentifier("quiet-hours-start")
                Divider().overlay(GoHomeTheme.softLine)
                DatePicker("结束", selection: $end, displayedComponents: .hourAndMinute)
                    .frame(minHeight: 54)
                    .accessibilityIdentifier("quiet-hours-end")
                Spacer()
            }
            .font(.system(size: 15, weight: .semibold))
            .foregroundStyle(GoHomeTheme.ink)
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 18)
            .background(GoHomeTheme.paper)
            .navigationTitle("免打扰")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("保存") {
                        onSave(QuietHours(start: Self.text(from: start), end: Self.text(from: end)))
                        dismiss()
                    }
                    .fontWeight(.semibold)
                }
            }
        }
        .presentationDetents([.medium])
    }

    private static func date(from value: String) -> Date {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "HH:mm"
        return formatter.date(from: value) ?? Date()
    }

    private static func text(from value: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "HH:mm"
        return formatter.string(from: value)
    }
}

private struct ProductPreferencesEditor: View {
    @Environment(\.dismiss) private var dismiss
    @State private var preferences: ProductPreferences
    let onSave: (ProductPreferences) -> Void

    private let categories = ["居家防滑与安全", "照明与视野", "日常生活与收纳", "沟通与简易电子", "非医疗出行配件"]
    private let needs = ["夜间照明", "居家防滑", "物品收纳", "简单操作", "出行便利"]

    init(initial: ProductPreferences, onSave: @escaping (ProductPreferences) -> Void) {
        _preferences = State(initialValue: initial)
        self.onSave = onSave
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    choiceSection(title: "关注类别", values: categories, selection: $preferences.categories)
                    choiceSection(title: "实际需求", values: needs, selection: $preferences.needs)
                }
                .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
                .padding(.top, 18)
                .padding(.bottom, 28)
            }
            .background(GoHomeTheme.paper)
            .navigationTitle("推荐方向")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("保存") {
                        onSave(preferences)
                        dismiss()
                    }
                    .fontWeight(.semibold)
                }
            }
        }
    }

    private func choiceSection(title: String, values: [String], selection: Binding<[String]>) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            GoHomeSectionHeader(title: title)
            ForEach(values, id: \.self) { value in
                Button {
                    var next = selection.wrappedValue
                    if let index = next.firstIndex(of: value) {
                        next.remove(at: index)
                    } else {
                        next.append(value)
                    }
                    selection.wrappedValue = next
                } label: {
                    HStack(spacing: 12) {
                        Text(value)
                            .font(.system(size: 15, weight: .semibold))
                        Spacer()
                        Image(systemName: selection.wrappedValue.contains(value) ? "checkmark.circle.fill" : "circle")
                            .foregroundStyle(selection.wrappedValue.contains(value) ? GoHomeTheme.ginger : GoHomeTheme.mutedInk)
                    }
                    .foregroundStyle(GoHomeTheme.ink)
                    .frame(minHeight: 48)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
        .overlay(alignment: .top) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
        .overlay(alignment: .bottom) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
    }
}
