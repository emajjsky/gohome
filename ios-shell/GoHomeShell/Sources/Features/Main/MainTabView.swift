import SwiftUI

struct MainTabView: View {
    let repository: AppRepository?
    let scope: CacheScope?
    let unreadCount: Int
    let apiClient: APIClient?
    let user: AppUser
    let family: AppFamily
    @ObservedObject var pushNotifications: PushNotificationCoordinator
    let onSignOut: () -> Void
    let onAccountDeleted: () -> Void
    @StateObject private var homeModel: HomeViewModel
    @StateObject private var eventsModel: EventsViewModel
    @StateObject private var timelineModel: ActivityTimelineViewModel
    @StateObject private var memoryModel: MemoryViewModel
    @StateObject private var recommendationsModel: ProductRecommendationsViewModel
    @StateObject private var profileModel: ProfileViewModel
    @State private var selection: GoHomeTab = .home
    @State private var homePath = NavigationPath()
    @State private var guardPath = NavigationPath()
    @State private var memoryPath = NavigationPath()
    @State private var communityPath = NavigationPath()
    @State private var profilePath = NavigationPath()
    @State private var guardSection: GuardSection = .live
    @State private var notificationRouteTask: Task<Void, Never>?

    static var preview: MainTabView {
        let isMember = ProcessInfo.processInfo.arguments.contains("-uiTestMember")
        let client = APIClient(baseURL: URL(string: "https://example.invalid")!)
        return MainTabView(
            repository: nil,
            scope: nil,
            unreadCount: 0,
            apiClient: ProcessInfo.processInfo.arguments.contains("-uiTestProfile") ? client : nil,
            user: AppUser(id: "preview", phone: "13800138000", displayName: "回家用户"),
            family: AppFamily(id: "preview", name: "我的家庭", role: isMember ? "member" : "owner"),
            pushNotifications: PushNotificationCoordinator(
                client: client,
                enabled: false,
                environment: "sandbox"
            ),
            onSignOut: {},
            onAccountDeleted: {}
        )
    }

    init(
        repository: AppRepository?,
        scope: CacheScope?,
        unreadCount: Int,
        apiClient: APIClient?,
        user: AppUser,
        family: AppFamily,
        pushNotifications: PushNotificationCoordinator,
        onSignOut: @escaping () -> Void,
        onAccountDeleted: @escaping () -> Void
    ) {
        self.repository = repository
        self.scope = scope
        self.unreadCount = unreadCount
        self.apiClient = apiClient
        self.user = user
        self.family = family
        self.pushNotifications = pushNotifications
        self.onSignOut = onSignOut
        self.onAccountDeleted = onAccountDeleted
        _homeModel = StateObject(wrappedValue: HomeViewModel(repository: repository, scope: scope))
        let seedEvents = ProcessInfo.processInfo.arguments.contains("-uiTestEvent") ? Self.uiTestEvents : []
        _eventsModel = StateObject(wrappedValue: EventsViewModel(repository: repository, scope: scope, seedEvents: seedEvents))
        _timelineModel = StateObject(wrappedValue: ActivityTimelineViewModel(
            repository: repository,
            scope: scope,
            canManageHistory: FamilyRole.resolve(familyRole: family.role, canEdit: false) == .creator
        ))
        _memoryModel = StateObject(wrappedValue: MemoryViewModel(repository: repository, scope: scope))
        _recommendationsModel = StateObject(wrappedValue: ProductRecommendationsViewModel(repository: repository, scope: scope))
        let seedProfile = ProcessInfo.processInfo.arguments.contains("-uiTestProfile")
            ? Self.uiTestProfile(familyID: family.id, canEdit: family.role != "member")
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
                        familyID: family.id,
                        eventsModel: eventsModel,
                        timelineModel: timelineModel,
                        section: $guardSection
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
                ProfileView(
                    model: profileModel,
                    onboardingService: apiClient.map(OnboardingService.init(client:)),
                    repository: repository,
                    onSignOut: onSignOut,
                    onAccountDeleted: onAccountDeleted
                )
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
        .onChange(of: selection) { next in
            if next == .guardView { homeModel.refresh() }
        }
        .onChange(of: profileModel.deviceConfigurationRevision) { _ in
            homeModel.reconcileDeviceConfiguration()
        }
        .onReceive(pushNotifications.$pendingRoute.compactMap { $0 }) { route in
            open(route)
        }
    }

    private func open(_ route: PushNotificationRoute) {
        switch route {
        case .home:
            notificationRouteTask?.cancel()
            selection = .home
            homePath = NavigationPath()
            pushNotifications.consume(route)
        case let .event(eventID, _):
            notificationRouteTask?.cancel()
            selection = .guardView
            guardSection = .events
            notificationRouteTask = Task {
                let ready = await eventsModel.prepareEvent(id: eventID)
                guard !Task.isCancelled else { return }
                if ready {
                    guardPath = NavigationPath()
                    guardPath.append(eventID)
                }
                pushNotifications.consume(route)
            }
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

    private static func uiTestProfile(familyID: String, canEdit: Bool) -> ProfileData {
        ProfileData(
            elder: nil,
            bindings: [DeviceBinding(
                id: "ui-test-binding",
                familyID: familyID,
                deviceID: "ui-test-box",
                deviceName: "演示守护盒子",
                status: "online",
                lastSeenAt: "2026-07-25T12:00:00+08:00"
            )],
            cameras: [CameraConfig(
                id: "ui-test-camera",
                familyID: familyID,
                deviceID: "ui-test-box",
                name: "客厅主视",
                room: "客厅",
                status: "online",
                syncStatus: "synced",
                connectionOwner: "edge_agent",
                hasStreamConfig: true,
                passwordSet: true,
                enabled: true
            )],
            rules: FamilyRules(
                canEdit: canEdit,
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
