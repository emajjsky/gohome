import SwiftUI

struct ProfileView: View {
    @ObservedObject private var model: ProfileViewModel
    let onSignOut: () -> Void

    init(model: ProfileViewModel, onSignOut: @escaping () -> Void) {
        self.model = model
        self.onSignOut = onSignOut
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                GoHomePageHeader(eyebrow: "我的", title: "账户与家庭")
                identity

                ProfileSection(title: "家庭") {
                    NavigationLink {
                        FamilyMembersView(model: model)
                    } label: {
                        ProfileNavigationRow(
                            symbol: "person.2",
                            title: model.family.name,
                            value: familySummary
                        )
                    }

                    NavigationLink {
                        if let elder = model.state.value?.elder {
                            CaredForProfileView(profile: elder)
                        } else {
                            ProfileUnavailableView(title: "尚未配置照护资料")
                        }
                    } label: {
                        ProfileNavigationRow(
                            symbol: "person.text.rectangle",
                            title: "照护资料",
                            value: model.state.value?.elder?.displayName ?? "未填写"
                        )
                    }
                }

                ProfileSection(title: "设备与守护") {
                    NavigationLink {
                        DeviceSettingsView(model: model)
                    } label: {
                        ProfileNavigationRow(
                            symbol: "shippingbox",
                            title: "家庭盒子与摄像头",
                            value: deviceSummary
                        )
                    }

                    NavigationLink {
                        RuleSettingsView(model: model)
                    } label: {
                        ProfileNavigationRow(
                            symbol: "viewfinder",
                            title: "守护规则",
                            value: model.canEditRules ? "可配置" : "仅查看"
                        )
                    }
                }

                ProfileSection(title: "消息与内容") {
                    NavigationLink {
                        ContentPreferencesView(model: model)
                    } label: {
                        ProfileNavigationRow(
                            symbol: "slider.horizontal.3",
                            title: "提醒与内容偏好",
                            value: preferenceSummary
                        )
                    }
                }

                ProfileSection(title: "账户") {
                    NavigationLink {
                        PrivacyDataView()
                    } label: {
                        ProfileNavigationRow(
                            symbol: "hand.raised",
                            title: "隐私与数据",
                            value: "已保护"
                        )
                    }

                    Button(role: .destructive, action: onSignOut) {
                        HStack(spacing: 12) {
                            Image(systemName: "rectangle.portrait.and.arrow.right")
                                .frame(width: 24)
                            Text("退出登录")
                                .font(.system(size: 15, weight: .semibold))
                            Spacer()
                        }
                        .foregroundStyle(Color.red)
                        .padding(.vertical, 15)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("profile-sign-out")
                }

                if let error = model.inlineError ?? model.state.staleReason {
                    Label(error, systemImage: "exclamationmark.circle")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                        .padding(.bottom, 8)
                }
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 18)
            .padding(.bottom, 28)
        }
        .background(GoHomeTheme.paper)
        .task { model.start() }
    }

    private var identity: some View {
        HStack(spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous)
                    .fill(GoHomeTheme.ink)
                    .frame(width: 52, height: 52)
                Text(identityInitial)
                    .font(.system(size: 20, weight: .bold, design: .rounded))
                    .foregroundStyle(GoHomeTheme.ginger)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(model.user.displayName?.nonEmpty ?? "回家用户")
                    .font(.system(size: 18, weight: .bold, design: .rounded))
                    .foregroundStyle(GoHomeTheme.ink)
                Text(maskedPhone)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
            Spacer()
        }
        .padding(.vertical, 5)
    }

    private var identityInitial: String {
        String((model.user.displayName?.nonEmpty ?? model.user.phone?.nonEmpty ?? "回").prefix(1))
    }

    private var maskedPhone: String {
        guard let phone = model.user.phone?.nonEmpty else { return "手机号未设置" }
        guard phone.count >= 7 else { return phone }
        let start = phone.prefix(3)
        let end = phone.suffix(4)
        return "\(start) **** \(end)"
    }

    private var deviceSummary: String {
        guard let value = model.state.value else { return "待同步" }
        if value.bindings.isEmpty { return "未绑定" }
        return "\(value.cameras.count) 路画面"
    }

    private var preferenceSummary: String {
        guard let value = model.state.value else { return "待同步" }
        return value.carePreferences.contentRecommendationsEnabled ? "已开启" : "已关闭"
    }

    private var familySummary: String {
        model.family.memberCount.map { "\($0) 人" } ?? "家庭管理"
    }
}

struct PrivacyDataView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                ProfileSection(title: "数据保护") {
                    PrivacyStatusRow(symbol: "key", title: "登录凭证", value: "钥匙串")
                    PrivacyStatusRow(symbol: "iphone", title: "本机缓存", value: "账户隔离")
                    PrivacyStatusRow(symbol: "house", title: "家庭数据", value: "云端同步")
                }
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 18)
            .padding(.bottom, 28)
        }
        .background(GoHomeTheme.paper)
        .profileNavigationTitle("隐私与数据")
    }
}

private struct ProfileNavigationTitleModifier: ViewModifier {
    @Environment(\.dismiss) private var dismiss
    let title: String

    func body(content: Content) -> some View {
        content
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .navigationBarBackButtonHidden(true)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button { dismiss() } label: {
                        Image(systemName: "chevron.left")
                            .font(.system(size: 16, weight: .semibold))
                    }
                    .foregroundStyle(GoHomeTheme.ink)
                    .accessibilityLabel("返回")
                }
            }
    }
}

extension View {
    func profileNavigationTitle(_ title: String) -> some View {
        modifier(ProfileNavigationTitleModifier(title: title))
    }
}

private struct PrivacyStatusRow: View {
    let symbol: String
    let title: String
    let value: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: symbol)
                .font(.system(size: 15, weight: .semibold))
                .frame(width: 24)
            Text(title)
                .font(.system(size: 15, weight: .semibold))
            Spacer()
            Text(value)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(GoHomeTheme.mutedInk)
        }
        .foregroundStyle(GoHomeTheme.ink)
        .frame(minHeight: 50)
    }
}

struct ProfileSection<Content: View>: View {
    let title: String
    @ViewBuilder let content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title)
                .font(.system(size: 12, weight: .bold))
                .foregroundStyle(GoHomeTheme.mutedInk)
                .padding(.bottom, 7)
            VStack(spacing: 0) {
                content()
            }
            .overlay(alignment: .top) {
                Rectangle().fill(GoHomeTheme.line).frame(height: 1)
            }
            .overlay(alignment: .bottom) {
                Rectangle().fill(GoHomeTheme.line).frame(height: 1)
            }
        }
    }
}

struct ProfileNavigationRow: View {
    let symbol: String
    let title: String
    var value: String?

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: symbol)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(GoHomeTheme.ink)
                .frame(width: 24)
            Text(title)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(GoHomeTheme.ink)
            Spacer(minLength: 12)
            if let value {
                Text(value)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(GoHomeTheme.mutedInk)
                    .lineLimit(1)
            }
            Image(systemName: "chevron.right")
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(GoHomeTheme.mutedInk)
        }
        .frame(minHeight: 52)
        .contentShape(Rectangle())
    }
}

struct ProfileUnavailableView: View {
    let title: String

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "minus.circle")
                .font(.system(size: 28, weight: .light))
            Text(title)
                .font(.system(size: 15, weight: .semibold))
        }
        .foregroundStyle(GoHomeTheme.mutedInk)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(GoHomeTheme.paper)
        .profileNavigationTitle("资料")
    }
}

private extension String {
    var nonEmpty: String? {
        let value = trimmingCharacters(in: .whitespacesAndNewlines)
        return value.isEmpty ? nil : value
    }
}
