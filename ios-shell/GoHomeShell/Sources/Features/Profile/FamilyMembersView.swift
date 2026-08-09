import SwiftUI
import UIKit

struct FamilyMembersView: View {
    @ObservedObject var model: ProfileViewModel
    @State private var pendingAction: PendingFamilyAction?
    @State private var familyActionTask: Task<Void, Never>?
    @State private var invitationActionTask: Task<Void, Never>?

    private enum PendingFamilyAction: Identifiable {
        case transfer(FamilyMember)
        case remove(FamilyMember)
        case leave
        case revokeInvitation(FamilyInvitation)

        var id: String {
            switch self {
            case let .transfer(member): "transfer-\(member.id)"
            case let .remove(member): "remove-\(member.id)"
            case .leave: "leave"
            case let .revokeInvitation(invitation): "revoke-\(invitation.id)"
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

                if model.canEditRules { invitationSection }

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
        .onDisappear {
            familyActionTask?.cancel()
            invitationActionTask?.cancel()
            model.cancelInFlightFamilyRefresh()
        }
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
                    familyActionTask = Task { await perform(action) }
                }
                Button("取消", role: .cancel) { pendingAction = nil }
            }
        } message: {
            Text(confirmationMessage)
        }
    }

    private var invitationSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            GoHomeSectionHeader(title: "邀请家人", detail: "一次有效")
            if let invitation = model.activeFamilyInvitation {
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        if let code = invitation.code, !code.isEmpty {
                            Text(code)
                                .font(.system(size: 17, weight: .bold, design: .monospaced))
                                .foregroundStyle(GoHomeTheme.ink)
                        } else {
                            Text("邀请码尾号 \(invitation.codeHint)")
                                .font(.system(size: 15, weight: .semibold))
                                .foregroundStyle(GoHomeTheme.ink)
                        }
                        Text(invitationExpiryText(invitation))
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(GoHomeTheme.mutedInk)
                    }
                    Spacer(minLength: 8)
                    if let code = invitation.code, !code.isEmpty {
                        ShareLink(item: invitationShareText(code)) {
                            Image(systemName: "square.and.arrow.up")
                                .frame(width: 38, height: 38)
                        }
                        .buttonStyle(ProfileIconButtonStyle())
                        .accessibilityLabel("分享家庭邀请码")
                    } else {
                        Button {
                            invitationActionTask = Task { _ = await model.createFamilyInvitation() }
                        } label: {
                            Image(systemName: "arrow.triangle.2.circlepath")
                                .frame(width: 38, height: 38)
                        }
                        .buttonStyle(ProfileIconButtonStyle())
                        .disabled(model.invitationActionID != nil)
                        .accessibilityLabel("重新生成家庭邀请码")
                    }
                    Button(role: .destructive) { pendingAction = .revokeInvitation(invitation) } label: {
                        Image(systemName: "xmark.circle")
                            .frame(width: 38, height: 38)
                    }
                    .buttonStyle(ProfileIconButtonStyle())
                    .disabled(model.invitationActionID != nil)
                    .accessibilityLabel("撤销家庭邀请码")
                }
            } else {
                Button {
                    invitationActionTask = Task { _ = await model.createFamilyInvitation() }
                } label: {
                    HStack(spacing: 9) {
                        if model.invitationActionID == "create-invitation" {
                            ProgressView().controlSize(.small)
                        } else {
                            Image(systemName: "person.badge.plus")
                        }
                        Text("生成邀请码")
                            .font(.system(size: 15, weight: .semibold))
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.system(size: 12, weight: .bold))
                    }
                    .foregroundStyle(GoHomeTheme.ink)
                    .frame(minHeight: 46)
                }
                .buttonStyle(.plain)
                .disabled(model.invitationActionID != nil)
            }
        }
        .padding(.vertical, 12)
        .overlay(alignment: .top) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
        .overlay(alignment: .bottom) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
    }

    private func invitationShareText(_ code: String) -> String {
        "邀请你加入“\(model.family.name)”\n邀请码：\(code)\n10 分钟内有效，仅可使用一次。"
    }

    private func invitationExpiryText(_ invitation: FamilyInvitation) -> String {
        guard let raw = invitation.expiresAt else { return "10 分钟内有效" }
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = fractional.date(from: raw) ?? ISO8601DateFormatter().date(from: raw) else {
            return "10 分钟内有效"
        }
        return "\(date.formatted(date: .omitted, time: .shortened)) 前有效"
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
        case .revokeInvitation: return "撤销这个邀请码？"
        }
    }

    private var confirmationMessage: String {
        guard let pendingAction else { return "" }
        switch pendingAction {
        case let .transfer(member): return "转让后，\(member.displayName) 将管理盒子、摄像头和守护规则，你将变为普通成员。"
        case let .remove(member): return "\(member.displayName) 将无法再查看这个家庭的数据，账号本身不会被删除。"
        case .leave: return "退出后将无法再查看这个家庭的画面、事件和记忆。"
        case .revokeInvitation: return "撤销后，这个邀请码将立即失效。"
        }
    }

    private func confirmationButtonTitle(_ action: PendingFamilyAction) -> String {
        switch action {
        case .transfer: "确认转让"
        case .remove: "确认移出"
        case .leave: "确认退出"
        case .revokeInvitation: "确认撤销"
        }
    }

    private func perform(_ action: PendingFamilyAction) async {
        switch action {
        case let .transfer(member): _ = await model.transferOwnership(to: member)
        case let .remove(member): _ = await model.removeFamilyMember(member)
        case .leave: _ = await model.leaveFamily()
        case let .revokeInvitation(invitation): _ = await model.revokeFamilyInvitation(invitation)
        }
    }
}

struct CaredForProfileView: View {
    @ObservedObject var model: ProfileViewModel
    @State private var isEditing = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                if let profile = model.state.value?.elder {
                    HStack(spacing: 14) {
                        Image(systemName: "person.crop.square")
                            .font(.system(size: 22, weight: .semibold))
                            .foregroundStyle(GoHomeTheme.ink)
                            .frame(width: 50, height: 50)
                            .background(GoHomeTheme.paleGinger, in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
                        VStack(alignment: .leading, spacing: 3) {
                            Text(profile.displayName)
                                .font(.system(size: 22, weight: .bold, design: .rounded))
                            Text([profile.relationship, ageText(profile)].filter { !$0.isEmpty }.joined(separator: " · "))
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
                } else {
                    VStack(alignment: .leading, spacing: 12) {
                        Image(systemName: "person.crop.circle.badge.plus")
                            .font(.system(size: 28, weight: .medium))
                            .foregroundStyle(GoHomeTheme.ginger)
                        Text("尚未填写照护资料")
                            .font(.system(size: 18, weight: .bold))
                            .foregroundStyle(GoHomeTheme.ink)
                        if model.canEditRules {
                            Button("添加资料") { isEditing = true }
                                .font(.system(size: 14, weight: .bold))
                                .foregroundStyle(GoHomeTheme.ink)
                                .padding(.horizontal, 15)
                                .frame(height: 40)
                                .background(GoHomeTheme.ginger, in: RoundedRectangle(cornerRadius: GoHomeTheme.controlRadius, style: .continuous))
                        }
                    }
                    .padding(.vertical, 28)
                }
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 18)
            .padding(.bottom, 28)
        }
        .background(GoHomeTheme.paper)
        .profileNavigationTitle("照护资料")
        .toolbar {
            if model.canEditRules, model.state.value?.elder != nil {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("编辑") { isEditing = true }
                        .fontWeight(.semibold)
                        .foregroundStyle(GoHomeTheme.ink)
                }
            }
        }
        .sheet(isPresented: $isEditing) {
            CaredForProfileEditor(model: model, profile: model.state.value?.elder)
        }
    }

    private func ageText(_ profile: ElderProfile) -> String { profile.age.map { "\($0) 岁" } ?? "" }
}

private struct CaredForProfileEditor: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var model: ProfileViewModel
    @StateObject private var locationProvider = MemoryLocationProvider()
    @State private var displayName: String
    @State private var relationship: String
    @State private var city: String
    @State private var district: String
    @State private var mobilePhone: String
    @State private var homePhone: String
    @State private var homeLatitude: Double?
    @State private var homeLongitude: Double?
    @State private var homeLocationLabel: String
    @State private var showsCityPicker = false

    private let relationships = ["母亲", "父亲", "祖父", "祖母", "亲属", "其他"]

    init(model: ProfileViewModel, profile: ElderProfile?) {
        let mobilePhone = profile?.mobilePhone.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        self.model = model
        _displayName = State(initialValue: profile?.displayName ?? "")
        _relationship = State(initialValue: profile?.relationship ?? "亲属")
        _city = State(initialValue: profile?.city ?? "")
        _district = State(initialValue: profile?.district ?? "")
        _mobilePhone = State(initialValue: mobilePhone.isEmpty ? profile?.phone ?? "" : mobilePhone)
        _homePhone = State(initialValue: profile?.homePhone ?? "")
        _homeLatitude = State(initialValue: profile?.homeLatitude)
        _homeLongitude = State(initialValue: profile?.homeLongitude)
        _homeLocationLabel = State(initialValue: profile?.homeLocationLabel ?? "")
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    ProfileSection(title: "基本资料") {
                        editField("称呼", text: $displayName, contentType: .name)
                        HStack(spacing: 16) {
                            Text("关系")
                                .font(.system(size: 14, weight: .medium))
                                .foregroundStyle(GoHomeTheme.mutedInk)
                                .frame(width: 72, alignment: .leading)
                            Menu {
                                ForEach(relationships, id: \.self) { value in
                                    Button(value) { relationship = value }
                                }
                            } label: {
                                HStack {
                                    Text(relationship)
                                    Spacer()
                                    Image(systemName: "chevron.up.chevron.down")
                                        .font(.caption.weight(.bold))
                                }
                                .foregroundStyle(GoHomeTheme.ink)
                            }
                        }
                        .frame(minHeight: 50)
                    }

                    ProfileSection(title: "联系方式") {
                        editField("手机", text: $mobilePhone, contentType: .telephoneNumber, keyboard: .phonePad)
                        editField("家庭电话", text: $homePhone, contentType: .telephoneNumber, keyboard: .phonePad)
                    }

                    ProfileSection(title: "所在地区") {
                        Button { showsCityPicker = true } label: {
                            HStack(spacing: 16) {
                                Text("城市")
                                    .font(.system(size: 14, weight: .medium))
                                    .foregroundStyle(GoHomeTheme.mutedInk)
                                    .frame(width: 72, alignment: .leading)
                                Text(city.isEmpty ? "选择城市" : city)
                                    .font(.system(size: 15, weight: .semibold))
                                    .foregroundStyle(city.isEmpty ? GoHomeTheme.mutedInk : GoHomeTheme.ink)
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.caption.weight(.bold))
                                    .foregroundStyle(GoHomeTheme.mutedInk)
                            }
                            .frame(minHeight: 50)
                        }
                        .buttonStyle(.plain)
                        editField("区域", text: $district, contentType: .sublocality)
                        Button { locationProvider.requestLocation() } label: {
                            HStack(spacing: 16) {
                                Text("家庭位置")
                                    .font(.system(size: 14, weight: .medium))
                                    .foregroundStyle(GoHomeTheme.mutedInk)
                                    .frame(width: 72, alignment: .leading)
                                Text(homeLocationLabel.isEmpty ? "设为当前位置" : homeLocationLabel)
                                    .font(.system(size: 15, weight: .semibold))
                                    .foregroundStyle(homeLocationLabel.isEmpty ? GoHomeTheme.mutedInk : GoHomeTheme.ink)
                                    .lineLimit(1)
                                Spacer()
                                if locationProvider.isLocating {
                                    ProgressView().controlSize(.small)
                                } else {
                                    Image(systemName: "location.fill")
                                        .font(.system(size: 13, weight: .semibold))
                                        .foregroundStyle(GoHomeTheme.ginger)
                                }
                            }
                            .frame(minHeight: 50)
                        }
                        .buttonStyle(.plain)
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
            .navigationTitle("编辑照护资料")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(model.savingElderProfile ? "保存中" : "保存") { save() }
                        .fontWeight(.semibold)
                        .disabled(!canSave || model.savingElderProfile)
                }
            }
        }
        .sheet(isPresented: $showsCityPicker) {
            CitySelectionView(selection: $city)
        }
        .onReceive(locationProvider.$coordinate.compactMap { $0 }) { coordinate in
            homeLatitude = coordinate.latitude
            homeLongitude = coordinate.longitude
        }
        .onReceive(locationProvider.$resolvedLocation.compactMap { $0 }) { location in
            city = location.city
            district = location.district
            homeLocationLabel = location.displayName
        }
    }

    private var normalizedMobilePhone: String { mobilePhone.filter(\.isNumber) }
    private var normalizedHomePhone: String { homePhone.filter { $0.isNumber || $0 == "-" } }
    private var canSave: Bool {
        !displayName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && normalizedMobilePhone.count >= 7
    }

    private func editField(
        _ title: String,
        text: Binding<String>,
        contentType: UITextContentType?,
        keyboard: UIKeyboardType = .default
    ) -> some View {
        HStack(spacing: 16) {
            Text(title)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(GoHomeTheme.mutedInk)
                .frame(width: 72, alignment: .leading)
            TextField("未填写", text: text)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(GoHomeTheme.ink)
                .textContentType(contentType)
                .keyboardType(keyboard)
        }
        .frame(minHeight: 50)
    }

    private func save() {
        let payload = ProfilePayload(
            displayName: displayName.trimmingCharacters(in: .whitespacesAndNewlines),
            relationship: relationship,
            city: city.trimmingCharacters(in: .whitespacesAndNewlines),
            district: district.trimmingCharacters(in: .whitespacesAndNewlines),
            phone: normalizedMobilePhone,
            mobilePhone: normalizedMobilePhone,
            homePhone: normalizedHomePhone,
            homeLatitude: homeLatitude,
            homeLongitude: homeLongitude,
            homeLocationLabel: homeLocationLabel.isEmpty ? nil : homeLocationLabel
        )
        Task {
            if await model.saveElderProfile(payload) { dismiss() }
        }
    }
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
