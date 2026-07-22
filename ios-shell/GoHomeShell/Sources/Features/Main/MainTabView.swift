import SwiftUI

struct MainTabView: View {
    let repository: AppRepository?
    let scope: CacheScope?
    let unreadCount: Int
    let apiClient: APIClient?
    @StateObject private var homeModel: HomeViewModel
    @State private var selection: GoHomeTab = .home
    @State private var homePath = NavigationPath()
    @State private var guardPath = NavigationPath()
    @State private var eventsPath = NavigationPath()
    @State private var discoverPath = NavigationPath()
    @State private var profilePath = NavigationPath()

    static var preview: MainTabView {
        MainTabView(repository: nil, scope: nil, unreadCount: 0, apiClient: nil)
    }

    init(repository: AppRepository?, scope: CacheScope?, unreadCount: Int, apiClient: APIClient?) {
        self.repository = repository
        self.scope = scope
        self.unreadCount = unreadCount
        self.apiClient = apiClient
        _homeModel = StateObject(wrappedValue: HomeViewModel(repository: repository, scope: scope))
    }

    var body: some View {
        TabView(selection: $selection) {
            GoHomeTabRoot(tab: .home, path: $homePath) {
                HomeView(model: homeModel, unreadCount: unreadCount)
            }
            GoHomeTabRoot(tab: .guardView, path: $guardPath) {
                GuardView(cameras: homeModel.state.value?.cameras ?? [], apiClient: apiClient)
            }
            GoHomeTabRoot(tab: .events, path: $eventsPath) {
                MainTabEmptyState(
                    tab: .events,
                    title: "事件记录",
                    detail: "当前没有待处理事件"
                )
            }
            GoHomeTabRoot(tab: .discover, path: $discoverPath) {
                MainTabEmptyState(
                    tab: .discover,
                    title: "今日精选",
                    detail: "今天还没有新的推荐"
                )
            }
            GoHomeTabRoot(tab: .profile, path: $profilePath) {
                MainTabEmptyState(
                    tab: .profile,
                    title: "我的设置",
                    detail: "账号与家庭设置"
                )
            }
        }
        .tint(GoHomeTheme.ink)
        .background(GoHomeTheme.paper)
        .accessibilityIdentifier("main-tab-shell")
        .task { homeModel.start() }
    }
}
