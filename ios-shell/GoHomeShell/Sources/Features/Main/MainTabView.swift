import SwiftUI

struct MainTabView: View {
    let repository: AppRepository?
    let scope: CacheScope?
    let unreadCount: Int
    let apiClient: APIClient?
    let user: AppUser
    let family: AppFamily
    let onSignOut: () -> Void
    @StateObject private var homeModel: HomeViewModel
    @StateObject private var eventsModel: EventsViewModel
    @StateObject private var memoryModel: MemoryViewModel
    @StateObject private var recommendationsModel: ProductRecommendationsViewModel
    @StateObject private var profileModel: ProfileViewModel
    @State private var selection: GoHomeTab = .home
    @State private var homePath = NavigationPath()
    @State private var guardPath = NavigationPath()
    @State private var memoryPath = NavigationPath()
    @State private var communityPath = NavigationPath()
    @State private var profilePath = NavigationPath()

    static var preview: MainTabView {
        MainTabView(
            repository: nil,
            scope: nil,
            unreadCount: 0,
            apiClient: nil,
            user: AppUser(id: "preview", phone: "13800138000", displayName: "回家用户"),
            family: AppFamily(id: "preview", name: "我的家庭", role: "owner"),
            onSignOut: {}
        )
    }

    init(
        repository: AppRepository?,
        scope: CacheScope?,
        unreadCount: Int,
        apiClient: APIClient?,
        user: AppUser,
        family: AppFamily,
        onSignOut: @escaping () -> Void
    ) {
        self.repository = repository
        self.scope = scope
        self.unreadCount = unreadCount
        self.apiClient = apiClient
        self.user = user
        self.family = family
        self.onSignOut = onSignOut
        _homeModel = StateObject(wrappedValue: HomeViewModel(repository: repository, scope: scope))
        let seedEvents = ProcessInfo.processInfo.arguments.contains("-uiTestEvent") ? Self.uiTestEvents : []
        _eventsModel = StateObject(wrappedValue: EventsViewModel(repository: repository, scope: scope, seedEvents: seedEvents))
        _memoryModel = StateObject(wrappedValue: MemoryViewModel(repository: repository, scope: scope))
        _recommendationsModel = StateObject(wrappedValue: ProductRecommendationsViewModel(repository: repository, scope: scope))
        let seedProfile = ProcessInfo.processInfo.arguments.contains("-uiTestProfile")
            ? Self.uiTestProfile(familyID: family.id)
            : nil
        _profileModel = StateObject(wrappedValue: ProfileViewModel(
            user: user,
            family: family,
            repository: repository,
            scope: scope,
            seed: seedProfile
        ))
    }

    var body: some View {
        TabView(selection: $selection) {
            GoHomeTabRoot(tab: .home, path: $homePath) {
                HomeView(model: homeModel, unreadCount: unreadCount)
            }
            GoHomeTabRoot(tab: .guardView, path: $guardPath) {
                if ProcessInfo.processInfo.arguments.contains("-uiTestEvent") {
                    EventsView(model: eventsModel, apiClient: apiClient)
                } else {
                    GuardView(
                        cameras: homeModel.state.value?.cameras ?? [],
                        apiClient: apiClient,
                        eventsModel: eventsModel
                    )
                }
            }
            GoHomeTabRoot(tab: .memory, path: $memoryPath) {
                MemoryView(model: memoryModel, apiClient: apiClient, user: user, family: family)
            }
            GoHomeTabRoot(tab: .community, path: $communityPath) {
                ProductRecommendationsView(model: recommendationsModel)
            }
            GoHomeTabRoot(tab: .profile, path: $profilePath) {
                ProfileView(model: profileModel, onSignOut: onSignOut)
            }
        }
        .tint(GoHomeTheme.ink)
        .background(GoHomeTheme.paper)
        .accessibilityIdentifier("main-tab-shell")
        .task {
            homeModel.start()
            memoryModel.start()
            recommendationsModel.start()
        }
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

    private static func uiTestProfile(familyID: String) -> ProfileData {
        ProfileData(
            elder: nil,
            bindings: [],
            cameras: [],
            rules: FamilyRules(
                canEdit: true,
                offlineEnabled: true,
                blackScreenEnabled: true,
                noMotionEnabled: true,
                personDetectionEnabled: true,
                fallDetectionEnabled: true,
                activityDetectionEnabled: true,
                fireDetectionEnabled: true,
                notificationEnabled: true
            ),
            carePreferences: CarePreferences(familyID: familyID, interests: ["天气", "防诈骗"]),
            productPreferences: ProductPreferences(categories: ["照明与视野"], needs: ["夜间照明"])
        )
    }
}
