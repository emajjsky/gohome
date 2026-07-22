import SwiftUI

struct ContentPreferencesView: View {
    @ObservedObject var model: ProfileViewModel
    private let availableInterests = ["天气", "本地资讯", "健康生活", "防诈骗", "戏曲", "家常", "节日"]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                if let preferences = model.state.value?.carePreferences {
                    ProfileSection(title: "消息") {
                        preferenceToggle("应用内提醒", symbol: "bell", value: model.state.value?.rules.notificationEnabled ?? true) { enabled in
                            guard var rules = model.state.value?.rules else { return }
                            rules.notificationEnabled = enabled
                            model.saveRules(rules)
                        }
                        ProfileValueRow(title: "免打扰", value: "\(preferences.quietHours.start) - \(preferences.quietHours.end)")
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

                    VStack(alignment: .leading, spacing: 10) {
                        GoHomeSectionHeader(title: "精选推荐", detail: "只做推荐")
                        Text(productPreferenceText)
                            .font(.system(size: 14, weight: .medium))
                            .foregroundStyle(GoHomeTheme.ink)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, minHeight: 52, alignment: .leading)
                            .overlay(alignment: .top) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
                            .overlay(alignment: .bottom) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
                    }
                } else {
                    ProfileEmptyRow(symbol: "slider.horizontal.3", title: "偏好设置暂不可用")
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
        .profileNavigationTitle("提醒与内容")
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
}
