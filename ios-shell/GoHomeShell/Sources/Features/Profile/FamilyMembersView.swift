import SwiftUI

struct FamilyMembersView: View {
    @ObservedObject var model: ProfileViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                familySummary

                VStack(alignment: .leading, spacing: 12) {
                    GoHomeSectionHeader(
                        title: "家庭成员",
                        detail: model.family.memberCount.map { "\($0) 人" }
                    )
                    memberRow
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
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 18)
            .padding(.bottom, 28)
        }
        .background(GoHomeTheme.paper)
        .profileNavigationTitle("家庭")
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

    private var memberRow: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .fill(GoHomeTheme.ink)
                    .frame(width: 42, height: 42)
                Image(systemName: "person.fill")
                    .foregroundStyle(GoHomeTheme.ginger)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(model.user.displayName ?? model.user.phone ?? "回家用户")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.ink)
                Text("当前账号")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
            Spacer()
            Text(model.role.rawValue)
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(GoHomeTheme.ink)
        }
        .padding(.vertical, 12)
        .overlay(alignment: .top) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
        .overlay(alignment: .bottom) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
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
