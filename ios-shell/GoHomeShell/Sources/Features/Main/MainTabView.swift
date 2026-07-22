import SwiftUI

struct MainTabView: View {
    let repository: AppRepository?
    let scope: CacheScope?
    let unreadCount: Int
    let apiClient: APIClient?
    @StateObject private var homeModel: HomeViewModel
    @StateObject private var eventsModel: EventsViewModel
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
        let seedEvents = ProcessInfo.processInfo.arguments.contains("-uiTestEvent") ? Self.uiTestEvents : []
        _eventsModel = StateObject(wrappedValue: EventsViewModel(repository: repository, scope: scope, seedEvents: seedEvents))
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
                EventsView(model: eventsModel, apiClient: apiClient)
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

    private static var uiTestEvents: [AppEvent] {
        [AppEvent(
            id: "ui-test-event-1",
            type: "fall_candidate",
            level: "critical",
            room: "客厅",
            cameraID: "2",
            cameraName: "客厅摄像头",
            occurredAt: "2026-07-22T09:30:00+08:00",
            createdAt: "2026-07-22T09:30:00+08:00",
            updatedAt: "2026-07-22T09:30:00+08:00",
            evidenceMedia: [EventEvidence(assetID: "missing-asset", role: "current", capturedAt: "2026-07-22T09:30:00+08:00")],
            payload: EventPayload(verification: EventVerification(status: "confirmed", result: EventVerificationResult(reason: "云端复核支持这条提醒，请结合实时画面确认。")))
        )]
    }
}
