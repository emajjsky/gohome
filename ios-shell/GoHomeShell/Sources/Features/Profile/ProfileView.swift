import SwiftUI
import UIKit

struct ProfileView: View {
    @ObservedObject private var model: ProfileViewModel
    let onboardingService: OnboardingService?
    let repository: AppRepository?
    let apiClient: APIClient?
    @ObservedObject var pushNotifications: PushNotificationCoordinator
    let onSignOut: () -> Void
    let onAccountDeleted: () -> Void

    init(
        model: ProfileViewModel,
        onboardingService: OnboardingService?,
        repository: AppRepository? = nil,
        apiClient: APIClient? = nil,
        pushNotifications: PushNotificationCoordinator,
        onSignOut: @escaping () -> Void,
        onAccountDeleted: @escaping () -> Void = {}
    ) {
        self.model = model
        self.onboardingService = onboardingService
        self.repository = repository
        self.apiClient = apiClient
        self.pushNotifications = pushNotifications
        self.onSignOut = onSignOut
        self.onAccountDeleted = onAccountDeleted
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                GoHomePageHeader(eyebrow: "我的", title: "账户与家庭")
                NavigationLink {
                    AccountProfileEditor(model: model, apiClient: apiClient)
                } label: {
                    profileHero
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("profile-account-entry")

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
                        CaredForProfileView(model: model)
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
                        DeviceSettingsView(model: model, onboardingService: onboardingService)
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

                    NavigationLink {
                        ActivityDataSettingsView(model: model)
                    } label: {
                        ProfileNavigationRow(
                            symbol: "chart.xyaxis.line",
                            title: "活动数据与报告",
                            value: activityDataSummary
                        )
                    }
                }

                ProfileSection(title: "消息与内容") {
                    NavigationLink {
                        ContentPreferencesView(model: model, pushNotifications: pushNotifications)
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
                        PrivacyDataView(
                            model: PrivacyDataViewModel(
                                repository: repository,
                                seedPlan: ProcessInfo.processInfo.arguments.contains("-uiTestProfile") ? .uiTestAllowed : nil
                            ),
                            onAccountDeleted: onAccountDeleted
                        )
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
                        .foregroundStyle(GoHomeTheme.danger)
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

    private var profileHero: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .center, spacing: 14) {
                AccountAvatar(
                    profile: model.accountProfile,
                    apiClient: apiClient,
                    size: 66
                )
                VStack(alignment: .leading, spacing: 4) {
                    Text("我的家庭")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(GoHomeTheme.leaf)
                    Text(model.accountProfile.displayName.nonEmpty ?? "回家用户")
                        .font(.system(size: 24, weight: .bold, design: .rounded))
                        .foregroundStyle(GoHomeTheme.ink)
                    Text(accountSubtitle)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
            .contentShape(Rectangle())
        }
        .padding(16)
        .background(GoHomeTheme.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(GoHomeTheme.line, lineWidth: 0.7)
        }
    }

    private var maskedPhone: String {
        guard let phone = model.accountProfile.phone.nonEmpty else { return "手机号未设置" }
        guard phone.count >= 7 else { return phone }
        let start = phone.prefix(3)
        let end = phone.suffix(4)
        return "\(start) **** \(end)"
    }

    private var accountSubtitle: String {
        let place = [model.accountProfile.city, model.accountProfile.district].filter { !$0.isEmpty }.joined(separator: " · ")
        return place.isEmpty ? maskedPhone : place
    }

    private var deviceSummary: String {
        guard let value = model.state.value else { return "—" }
        if value.bindings.isEmpty { return "未绑定" }
        return "\(value.cameras.count) 路画面"
    }

    private var preferenceSummary: String {
        guard let value = model.state.value else { return "—" }
        return value.carePreferences.contentRecommendationsEnabled ? "已开启" : "已关闭"
    }

    private var activityDataSummary: String {
        guard let settings = model.state.value?.carePreferences.metadata.activityHistory else { return "—" }
        return settings.trackingEnabled ? "已开启" : "已关闭"
    }

    private var familySummary: String {
        model.family.memberCount.map { "\($0) 人" } ?? "家庭管理"
    }
}

struct PrivacyDataView: View {
    @StateObject private var model: PrivacyDataViewModel
    let onAccountDeleted: () -> Void
    @State private var shareItem: ExportShareItem?
    @State private var confirmsDeletion = false

    init(model: PrivacyDataViewModel, onAccountDeleted: @escaping () -> Void) {
        _model = StateObject(wrappedValue: model)
        self.onAccountDeleted = onAccountDeleted
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                ProfileSection(title: "数据保护") {
                    PrivacyStatusRow(symbol: "key", title: "登录凭证", value: "钥匙串")
                    PrivacyStatusRow(symbol: "iphone", title: "本机缓存", value: "账户隔离")
                    PrivacyStatusRow(symbol: "house", title: "家庭数据", value: "云端同步")
                }

                ProfileSection(title: "我的数据") {
                    Button(action: model.exportData) {
                        PrivacyActionRow(
                            symbol: "square.and.arrow.up",
                            title: "导出我的数据",
                            value: model.isExporting ? "正在生成" : "JSON 文件",
                            showsProgress: model.isExporting
                        )
                    }
                    .buttonStyle(.plain)
                    .disabled(model.isExporting || model.isDeleting)
                    .accessibilityIdentifier("privacy-export-data")
                }

                ProfileSection(title: "账号") {
                    if model.isLoading && model.plan == nil {
                        PrivacyActionRow(symbol: "person.crop.circle.badge.questionmark", title: "注销账号", value: "正在确认", showsProgress: true)
                    } else if let blocker = model.plan?.blockers.first {
                        VStack(alignment: .leading, spacing: 6) {
                            Label("暂时无法注销", systemImage: "person.2.badge.gearshape")
                                .font(.system(size: 15, weight: .semibold))
                                .foregroundStyle(GoHomeTheme.ink)
                            Text(blocker.message)
                                .font(.system(size: 13, weight: .medium))
                                .foregroundStyle(GoHomeTheme.mutedInk)
                        }
                        .frame(maxWidth: .infinity, minHeight: 62, alignment: .leading)
                        .accessibilityIdentifier("privacy-delete-blocked")
                    } else {
                        Button(role: .destructive) { confirmsDeletion = true } label: {
                            PrivacyActionRow(
                                symbol: "trash",
                                title: "永久删除账号",
                                value: deletionSummary,
                                showsProgress: model.isDeleting,
                                destructive: true
                            )
                        }
                        .buttonStyle(.plain)
                        .disabled(model.plan?.canDelete != true || model.isDeleting || model.isExporting)
                        .accessibilityIdentifier("privacy-delete-account")
                    }
                }

                if let note = model.plan?.retentionNote, !note.isEmpty {
                    Text(note)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }

                if let error = model.errorMessage {
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
        .profileNavigationTitle("隐私与数据")
        .task { model.start() }
        .onChange(of: model.exportURL) { url in
            if let url { shareItem = ExportShareItem(url: url) }
        }
        .sheet(item: $shareItem, onDismiss: model.clearExport) { item in
            SystemShareSheet(items: [item.url])
        }
        .alert("永久删除账号？", isPresented: $confirmsDeletion) {
            Button("取消", role: .cancel) {}
            Button("永久删除", role: .destructive) {
                Task {
                    if await model.deleteAccount() { onAccountDeleted() }
                }
            }
        } message: {
            Text(deletionConfirmationMessage)
        }
    }

    private var deletionSummary: String {
        guard let scope = model.plan?.deletionScope else { return "不可恢复" }
        if !scope.familiesToDelete.isEmpty { return "含家庭数据" }
        return "不可恢复"
    }

    private var deletionConfirmationMessage: String {
        guard let scope = model.plan?.deletionScope else { return "账号与登录数据将被删除，且无法恢复。" }
        var parts = ["账号、登录凭证和推送标识将被删除"]
        if !scope.familiesToDelete.isEmpty { parts.append("你独自创建的家庭及其数据也会删除") }
        if scope.authoredMemories > 0 { parts.append("你发布的 \(scope.authoredMemories) 条记忆会删除") }
        return parts.joined(separator: "；") + "。此操作无法恢复。"
    }
}

private struct PrivacyActionRow: View {
    let symbol: String
    let title: String
    let value: String
    let showsProgress: Bool
    var destructive = false

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: symbol)
                .font(.system(size: 15, weight: .semibold))
                .frame(width: 24)
            Text(title)
                .font(.system(size: 15, weight: .semibold))
            Spacer()
            if showsProgress {
                ProgressView().controlSize(.small)
            } else {
                Text(value)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(destructive ? Color.red.opacity(0.75) : GoHomeTheme.mutedInk)
            }
        }
        .foregroundStyle(destructive ? Color.red : GoHomeTheme.ink)
        .frame(minHeight: 52)
        .contentShape(Rectangle())
    }
}

private struct ExportShareItem: Identifiable {
    let id = UUID()
    let url: URL
}

private struct SystemShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

private extension AccountDeletionPlan {
    static let uiTestAllowed = AccountDeletionPlan(
        canDelete: true,
        requiresOwnershipTransfer: false,
        families: [],
        blockers: [],
        deletionScope: AccountDeletionScope(familiesToDelete: ["ui-test-family"], membershipsToLeave: [], authoredMemories: 1),
        retentionNote: "账号与可删除内容将按规则清理。"
    )
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
            .padding(.horizontal, 14)
            .background(GoHomeTheme.surface, in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous)
                    .stroke(GoHomeTheme.line, lineWidth: 0.7)
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
                .foregroundStyle(GoHomeTheme.leaf)
                .frame(width: 30, height: 30)
                .background(GoHomeTheme.paleLeaf, in: Circle())
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
