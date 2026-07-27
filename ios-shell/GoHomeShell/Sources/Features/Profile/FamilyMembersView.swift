import SwiftUI

struct FamilyMembersView: View {
    @ObservedObject var model: ProfileViewModel
    @State private var pendingAction: PendingFamilyAction?

    private enum PendingFamilyAction: Identifiable {
        case transfer(FamilyMember)
        case remove(FamilyMember)
        case leave

        var id: String {
            switch self {
            case let .transfer(member): "transfer-\(member.id)"
            case let .remove(member): "remove-\(member.id)"
            case .leave: "leave"
            }
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                familySummary

                VStack(alignment: .leading, spacing: 12) {
                    GoHomeSectionHeader(
                        title: "家庭成员",
                        detail: model.family.memberCount.map { "\($0) 人" }
                    )
                    ForEach(model.familyMembers) { member in
                        memberRow(member)
                    }
                }

                if let error = model.inlineError {
                    HStack(spacing: 10) {
                        Label(error, systemImage: "exclamationmark.circle")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(GoHomeTheme.mutedInk)
                        Spacer()
                        Button { model.refreshFamilyMembers() } label: {
                            Image(systemName: "arrow.clockwise")
                                .frame(width: 34, height: 34)
                        }
                        .buttonStyle(ProfileIconButtonStyle())
                        .disabled(model.familyActionID != nil)
                        .accessibilityLabel("重新载入家庭成员")
                    }
                }

                if let code = model.family.joinCode, !code.isEmpty, model.canEditRules {
                    VStack(alignment: .leading, spacing: 10) {
                        GoHomeSectionHeader(title: "家庭邀请码", detail: "创建者可见")
                        HStack {
                            Text(code)
                                .font(.system(size: 18, weight: .bold, design: .monospaced))
                                .foregroundStyle(GoHomeTheme.ink)
                            Spacer()
                            ShareLink(item: "加入 \(model.family.name)：\(code)") {
                                Image(systemName: "square.and.arrow.up")
                                    .frame(width: 38, height: 38)
                            }
                            .buttonStyle(ProfileIconButtonStyle())
                            .accessibilityLabel("分享家庭邀请码")
                        }
                        .padding(.vertical, 12)
                        .overlay(alignment: .top) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
                        .overlay(alignment: .bottom) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
                    }
                }

                if model.role == .member {
                    Button(role: .destructive) { pendingAction = .leave } label: {
                        Label("退出这个家庭", systemImage: "rectangle.portrait.and.arrow.right")
                            .font(.system(size: 15, weight: .semibold))
                            .frame(maxWidth: .infinity, minHeight: 48)
                    }
                    .buttonStyle(.plain)
                    .disabled(model.familyActionID != nil)
                }
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 18)
            .padding(.bottom, 28)
        }
        .background(GoHomeTheme.paper)
        .profileNavigationTitle("家庭")
        .task { model.refreshFamilyMembers() }
        .confirmationDialog(
            confirmationTitle,
            isPresented: Binding(
                get: { pendingAction != nil },
                set: { if !$0 { pendingAction = nil } }
            ),
            titleVisibility: .visible
        ) {
            if let action = pendingAction {
                Button(confirmationButtonTitle(action), role: .destructive) {
                    pendingAction = nil
                    Task { await perform(action) }
                }
                Button("取消", role: .cancel) { pendingAction = nil }
            }
        } message: {
            Text(confirmationMessage)
        }
    }

    private var familySummary: some View {
        HStack(alignment: .center, spacing: 14) {
            Image(systemName: "house.fill")
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(GoHomeTheme.ink)
                .frame(width: 46, height: 46)
                .background(GoHomeTheme.paleGinger, in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
            VStack(alignment: .leading, spacing: 4) {
                Text(model.family.name)
                    .font(.system(size: 21, weight: .bold, design: .rounded))
                    .foregroundStyle(GoHomeTheme.ink)
                Text(model.role.rawValue)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
        }
    }

    private func memberRow(_ member: FamilyMember) -> some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .fill(GoHomeTheme.ink)
                    .frame(width: 42, height: 42)
                Image(systemName: "person.fill")
                    .foregroundStyle(GoHomeTheme.ginger)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(member.displayName)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.ink)
                Text(member.isCurrentUser ? "当前账号" : member.accountHint)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
            Spacer()
            Text(member.isCreator ? "创建者" : "成员")
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(GoHomeTheme.ink)
            if model.canEditRules, !member.isCurrentUser {
                Menu {
                    Button { pendingAction = .transfer(member) } label: {
                        Label("设为创建者", systemImage: "person.badge.key")
                    }
                    Button(role: .destructive) { pendingAction = .remove(member) } label: {
                        Label("移出家庭", systemImage: "person.crop.circle.badge.minus")
                    }
                } label: {
                    Image(systemName: "ellipsis")
                        .frame(width: 38, height: 38)
                        .contentShape(Rectangle())
                }
                .buttonStyle(ProfileIconButtonStyle())
                .disabled(model.familyActionID != nil)
                .accessibilityLabel("管理 \(member.displayName)")
            }
        }
        .padding(.vertical, 12)
        .overlay(alignment: .top) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
        .overlay(alignment: .bottom) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
    }

    private var confirmationTitle: String {
        guard let pendingAction else { return "确认操作" }
        switch pendingAction {
        case .transfer: return "转让创建者身份？"
        case .remove: return "移出家庭？"
        case .leave: return "退出这个家庭？"
        }
    }

    private var confirmationMessage: String {
        guard let pendingAction else { return "" }
        switch pendingAction {
        case let .transfer(member): return "转让后，\(member.displayName) 将管理盒子、摄像头和守护规则，你将变为普通成员。"
        case let .remove(member): return "\(member.displayName) 将无法再查看这个家庭的数据，账号本身不会被删除。"
        case .leave: return "退出后将无法再查看这个家庭的画面、事件和记忆。"
        }
    }

    private func confirmationButtonTitle(_ action: PendingFamilyAction) -> String {
        switch action {
        case .transfer: "确认转让"
        case .remove: "确认移出"
        case .leave: "确认退出"
        }
    }

    private func perform(_ action: PendingFamilyAction) async {
        switch action {
        case let .transfer(member): _ = await model.transferOwnership(to: member)
        case let .remove(member): _ = await model.removeFamilyMember(member)
        case .leave: _ = await model.leaveFamily()
        }
    }
}

struct CaredForProfileView: View {
    let profile: ElderProfile

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                HStack(spacing: 14) {
                    Image(systemName: "person.crop.square")
                        .font(.system(size: 22, weight: .semibold))
                        .foregroundStyle(GoHomeTheme.ink)
                        .frame(width: 50, height: 50)
                        .background(GoHomeTheme.paleGinger, in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
                    VStack(alignment: .leading, spacing: 3) {
                        Text(profile.displayName)
                            .font(.system(size: 22, weight: .bold, design: .rounded))
                        Text([profile.relationship, ageText].filter { !$0.isEmpty }.joined(separator: " · "))
                            .font(.system(size: 13, weight: .medium))
                            .foregroundStyle(GoHomeTheme.mutedInk)
                    }
                }

                ProfileSection(title: "联系方式") {
                    ProfileValueRow(title: "手机", value: profile.mobilePhone.isEmpty ? profile.phone : profile.mobilePhone)
                    ProfileValueRow(title: "家庭电话", value: profile.homePhone)
                }

                ProfileSection(title: "所在地区") {
                    ProfileValueRow(title: "城市", value: profile.city)
                    ProfileValueRow(title: "区域", value: profile.district)
                }
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 18)
            .padding(.bottom, 28)
        }
        .background(GoHomeTheme.paper)
        .profileNavigationTitle("照护资料")
    }

    private var ageText: String { profile.age.map { "\($0) 岁" } ?? "" }
}

struct ProfileValueRow: View {
    let title: String
    let value: String

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 16) {
            Text(title)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(GoHomeTheme.mutedInk)
                .frame(width: 72, alignment: .leading)
            Text(value.isEmpty ? "未填写" : value)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(GoHomeTheme.ink)
            Spacer()
        }
        .frame(minHeight: 48)
    }
}

struct ProfileIconButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(GoHomeTheme.ink)
            .background(GoHomeTheme.paper, in: RoundedRectangle(cornerRadius: GoHomeTheme.controlRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: GoHomeTheme.controlRadius, style: .continuous)
                    .stroke(GoHomeTheme.line, lineWidth: 1)
            }
            .opacity(configuration.isPressed ? 0.65 : 1)
    }
}
