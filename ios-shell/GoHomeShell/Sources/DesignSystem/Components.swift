import SwiftUI

struct GoHomePageHeader: View {
    let eyebrow: String
    let title: String
    var trailing: AnyView?

    init(eyebrow: String, title: String, trailing: AnyView? = nil) {
        self.eyebrow = eyebrow
        self.title = title
        self.trailing = trailing
    }

    var body: some View {
        HStack(alignment: .bottom, spacing: 12) {
            VStack(alignment: .leading, spacing: 5) {
                Text(eyebrow.uppercased())
                    .font(.system(size: 11, weight: .bold, design: .rounded))
                    .foregroundStyle(GoHomeTheme.ginger)
                Text(title)
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                    .foregroundStyle(GoHomeTheme.ink)
            }
            Spacer(minLength: 12)
            trailing
        }
    }
}

struct GoHomeSectionHeader: View {
    let title: String
    var detail: String?

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title)
                .font(.system(size: 18, weight: .bold, design: .rounded))
                .foregroundStyle(GoHomeTheme.ink)
            Spacer()
            if let detail {
                Text(detail)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
        }
    }
}

struct GoHomeStatusDot: View {
    let color: Color
    var body: some View {
        Circle()
            .fill(color)
            .frame(width: 7, height: 7)
            .accessibilityHidden(true)
    }
}

struct GoHomeTabRoot<Content: View>: View {
    let tab: GoHomeTab
    @Binding var path: NavigationPath
    @ViewBuilder let content: () -> Content

    var body: some View {
        NavigationStack(path: $path) {
            content()
                .navigationBarTitleDisplayMode(.inline)
        }
        .tag(tab)
        .tabItem {
            Label(tab.title, systemImage: tab.icon)
        }
        .tint(GoHomeTheme.ink)
    }
}

struct MainTabEmptyState: View {
    let tab: GoHomeTab
    let title: String
    let detail: String

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            GoHomePageHeader(eyebrow: tab.title, title: title)
            Text(detail)
                .font(.system(size: 15, weight: .regular))
                .foregroundStyle(GoHomeTheme.mutedInk)
                .padding(.top, 14)
            Spacer()
        }
        .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
        .padding(.top, 18)
        .background(GoHomeTheme.paper.ignoresSafeArea())
    }
}
