import SwiftUI

struct MainTabView: View {
    let repository: AppRepository?
    let scope: CacheScope?
    let apiClient: APIClient?
    let user: AppUser
    let family: AppFamily
    @ObservedObject var pushNotifications: PushNotificationCoordinator
    let onSignOut: () -> Void
    let onAccountDeleted: () -> Void
    let onFamilyChanged: () -> Void
    let onAccountProfileChanged: (AccountProfile) -> Void
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
    @State private var showsHomeLocationSetup = false

    static var preview: MainTabView {
        let isMember = ProcessInfo.processInfo.arguments.contains("-uiTestMember")
        let client = APIClient(baseURL: URL(string: "https://example.invalid")!)
        return MainTabView(
            repository: nil,
            scope: nil,
            apiClient: ProcessInfo.processInfo.arguments.contains("-uiTestProfile") ? client : nil,
            user: AppUser(id: "preview", phone: "13800138000", displayName: "回家用户"),
            family: AppFamily(id: "preview", name: "我的家庭", role: isMember ? "member" : "owner"),
            pushNotifications: PushNotificationCoordinator(
                client: client,
                enabled: false,
                environment: "sandbox"
            ),
            onSignOut: {},
            onAccountDeleted: {},
            onFamilyChanged: {},
            onAccountProfileChanged: { _ in }
        )
    }

    init(
        repository: AppRepository?,
        scope: CacheScope?,
        apiClient: APIClient?,
        user: AppUser,
        family: AppFamily,
        pushNotifications: PushNotificationCoordinator,
        onSignOut: @escaping () -> Void,
        onAccountDeleted: @escaping () -> Void,
        onFamilyChanged: @escaping () -> Void,
        onAccountProfileChanged: @escaping (AccountProfile) -> Void
    ) {
        self.repository = repository
        self.scope = scope
        self.apiClient = apiClient
        self.user = user
        self.family = family
        self.pushNotifications = pushNotifications
        self.onSignOut = onSignOut
        self.onAccountDeleted = onAccountDeleted
        self.onFamilyChanged = onFamilyChanged
        self.onAccountProfileChanged = onAccountProfileChanged
        let hasHomeFixture = ProcessInfo.processInfo.arguments.contains("-uiTestHome")
        let hasFixedHomeLocation = ProcessInfo.processInfo.arguments.contains("-uiTestFixedHomeLocation")
        let hasSurfaceFixture = ProcessInfo.processInfo.arguments.contains("-uiTestSurface")
        _homeModel = StateObject(wrappedValue: HomeViewModel(
            repository: repository,
            scope: scope,
            seed: hasHomeFixture ? Self.uiTestHome(
                homeLocation: hasFixedHomeLocation
                    ? HomeLocation(
                        latitude: 30.2146,
                        longitude: 120.1573,
                        label: "西湖区 · 杭州市",
                        city: "杭州市",
                        district: "西湖区",
                        source: "profile",
                        updatedAt: "2026-07-31T10:00:00+08:00"
                    )
                    : nil
            ) : nil
        ))
        let seedEvents = ProcessInfo.processInfo.arguments.contains("-uiTestEvent") || hasHomeFixture
            ? Self.uiTestEvents
            : []
        _eventsModel = StateObject(wrappedValue: EventsViewModel(repository: repository, scope: scope, seedEvents: seedEvents))
        _timelineModel = StateObject(wrappedValue: ActivityTimelineViewModel(
            repository: repository,
            scope: scope,
            canManageHistory: FamilyRole.resolve(familyRole: family.role, canEdit: false) == .creator,
            seed: hasSurfaceFixture ? Self.uiTestTimeline : nil,
            overviewSeed: hasSurfaceFixture ? Self.uiTestActivityOverview : nil
        ))
        _memoryModel = StateObject(wrappedValue: MemoryViewModel(
            repository: repository,
            scope: scope,
            seed: hasSurfaceFixture ? Self.uiTestMemories : nil
        ))
        _recommendationsModel = StateObject(wrappedValue: ProductRecommendationsViewModel(
            repository: repository,
            scope: scope,
            seed: hasSurfaceFixture ? Self.uiTestProducts : nil
        ))
        let seedProfile = ProcessInfo.processInfo.arguments.contains("-uiTestProfile")
            ? Self.uiTestProfile(familyID: family.id, canEdit: family.role != "member")
            : nil
        _profileModel = StateObject(wrappedValue: ProfileViewModel(
            user: user,
            family: family,
            repository: repository,
            scope: scope,
            seed: seedProfile,
            onFamilyChanged: onFamilyChanged,
            onAccountProfileChanged: onAccountProfileChanged
        ))
    }

    var body: some View {
        TabView(selection: $selection) {
            GoHomeTabRoot(tab: .home, path: $homePath) {
                HomeView(
                    model: homeModel,
                    apiClient: apiClient,
                    onSetHomeLocation: homeLocationSetupAction
                ) { eventID in
                    openEvent(eventID)
                }
            }
            GoHomeTabRoot(tab: .guardView, path: $guardPath) {
                if ProcessInfo.processInfo.arguments.contains("-uiTestEvent") {
                    EventsView(model: eventsModel, apiClient: apiClient)
                } else {
                    GuardView(
                        cameras: guardCameras,
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
                CommunityView(
                    model: recommendationsModel,
                    apiBaseURL: apiClient?.baseURL,
                    homeLocation: homeModel.state.value?.homeLocation,
                    onSetHomeLocation: homeLocationSetupAction
                )
            }
            GoHomeTabRoot(tab: .profile, path: $profilePath) {
                ProfileView(
                    model: profileModel,
                    onboardingService: apiClient.map(OnboardingService.init(client:)),
                    repository: repository,
                    apiClient: apiClient,
                    pushNotifications: pushNotifications,
                    onSignOut: onSignOut,
                    onAccountDeleted: onAccountDeleted
                )
            }
        }
        .tint(GoHomeTheme.ink)
        .background(GoHomeTheme.paper)
        .accessibilityIdentifier("main-tab-shell")
        .task {
            profileModel.start()
            recommendationsModel.start()
        }
        .onChange(of: profileModel.deviceConfigurationRevision) { _ in
            homeModel.reconcileDeviceConfiguration()
        }
        .onReceive(pushNotifications.$pendingRoute.compactMap { $0 }) { route in
            open(route)
        }
        .sheet(isPresented: $showsHomeLocationSetup) {
            if let apiClient {
                HomeLocationSetupView(
                    service: OnboardingService(client: apiClient),
                    familyID: family.id,
                    profile: profileModel.state.value?.elder
                ) {
                    profileModel.refresh()
                    homeModel.refresh()
                }
            }
        }
    }

    private var homeLocationSetupAction: (() -> Void)? {
        guard
            apiClient != nil,
            FamilyRole.resolve(familyRole: family.role, canEdit: false) == .creator
        else { return nil }
        return { showsHomeLocationSetup = true }
    }

    private var guardCameras: [HomeCamera] {
        GuardCameraCatalog.resolve(
            profile: profileModel.state.value,
            fallback: homeModel.state.value?.cameras ?? []
        )
    }

    private func open(_ route: PushNotificationRoute) {
        switch route {
        case .home:
            notificationRouteTask?.cancel()
            selection = .home
            homePath = NavigationPath()
            pushNotifications.consume(route)
        case let .event(eventID, _):
            openEvent(eventID) { pushNotifications.consume(route) }
        }
    }

    private func openEvent(_ eventID: String, completion: @escaping () -> Void = {}) {
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
            completion()
        }
    }

    private static func uiTestHome(homeLocation: HomeLocation?) -> HomeResponse {
        HomeResponse(
            family: nil,
            weather: HomeWeather(city: "杭州", temperature: 29, condition: "晴"),
            calendar: [HomeCalendarEvent(id: "calendar-1", title: "周末回家", startsAt: "2026-07-31T10:00:00+08:00")],
            distance: HomeDistance(
                meters: 8_600,
                travelMinutes: 24,
                userLatitude: 30.2741,
                userLongitude: 120.1551,
                homeLatitude: 30.2146,
                homeLongitude: 120.1573
            ),
            homeLocation: homeLocation,
            criticalAlert: HomeCriticalAlert(
                id: "ui-test-event-1",
                title: "客厅有一条安全事件待确认",
                level: "critical",
                acknowledged: false
            ),
            careMessage: nil,
            articles: [
                HomeArticle(
                    id: "article-1",
                    category: "本地",
                    title: "周末城市公园开放夜游时段",
                    summary: "傍晚路线与公共交通信息已更新。",
                    imageURL: "",
                    sourceName: "城市服务",
                    sourceURL: "https://example.com/local",
                    publishedAt: "2026-07-28T09:00:00+08:00"
                ),
                HomeArticle(
                    id: "article-2",
                    category: "生活健康",
                    title: "高温天气的居家通风时段",
                    summary: "避开正午高温，保持室内空气流通。",
                    imageURL: "",
                    sourceName: "健康杭州",
                    sourceURL: "https://example.com/wellness",
                    publishedAt: "2026-07-28T08:00:00+08:00"
                ),
                HomeArticle(
                    id: "article-3",
                    category: "文娱",
                    title: "本周公共文化活动清单",
                    summary: "戏曲、展览与社区放映可提前预约。",
                    imageURL: "",
                    sourceName: "公共文化云",
                    sourceURL: "https://example.com/culture",
                    publishedAt: "2026-07-27T18:00:00+08:00"
                ),
                HomeArticle(
                    id: "article-4",
                    category: "兴趣",
                    title: "夏季阳台植物的浇水节奏",
                    summary: "观察土壤状态，比固定时间浇水更可靠。",
                    imageURL: "",
                    sourceName: "生活指南",
                    sourceURL: "https://example.com/interests",
                    publishedAt: "2026-07-27T12:00:00+08:00"
                ),
            ],
            cameras: [],
            revision: "ui-test-home-r1"
        )
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

    private static var uiTestMemories: FamilyMemoriesResponse {
        FamilyMemoriesResponse(
            memories: [
                FamilyMemory(
                    id: "memory-1",
                    familyID: "preview",
                    author: MemoryAuthor(id: "preview", displayName: "我"),
                    body: "周末一起整理了阳台，傍晚的风很舒服。",
                    happenedAt: "2026-07-27T18:30:00+08:00",
                    locationName: "家",
                    people: [],
                    media: [],
                    comments: [MemoryComment(id: "comment-1", authorUserID: "family-2", body: "下次一起种点薄荷。", createdAt: "2026-07-27T19:00:00+08:00")],
                    favoriteCount: 2,
                    isFavorite: true,
                    createdAt: "2026-07-27T18:35:00+08:00",
                    updatedAt: "2026-07-27T19:00:00+08:00"
                ),
                FamilyMemory(
                    id: "memory-2",
                    familyID: "preview",
                    author: MemoryAuthor(id: "family-2", displayName: "家人"),
                    body: "把旧相册重新按年份排好了。",
                    happenedAt: "2026-07-20T10:00:00+08:00",
                    locationName: "客厅",
                    people: [],
                    media: [],
                    comments: [],
                    favoriteCount: 0,
                    isFavorite: false,
                    createdAt: "2026-07-20T10:05:00+08:00",
                    updatedAt: "2026-07-20T10:05:00+08:00"
                ),
            ],
            revision: "ui-test-memory-r1"
        )
    }

    private static var uiTestTimeline: ActivityTimelineResponse {
        ActivityTimelineResponse(
            date: "2026-07-28",
            intervals: [
                ActivityInterval(
                    id: "activity-1",
                    cameraID: "camera-1",
                    room: "客厅",
                    startedAt: "2026-07-28T08:12:00+08:00",
                    endedAt: "2026-07-28T08:28:00+08:00",
                    personCountMax: 1,
                    postures: ["standing", "sitting"],
                    confidence: 0.91
                ),
                ActivityInterval(
                    id: "activity-2",
                    cameraID: "camera-2",
                    room: "厨房",
                    startedAt: "2026-07-28T12:03:00+08:00",
                    endedAt: "2026-07-28T12:17:00+08:00",
                    personCountMax: 1,
                    postures: ["standing"],
                    confidence: 0.94
                ),
            ],
            revision: "ui-test-activity-r1"
        )
    }

    private static var uiTestActivityOverview: ActivityOverviewResponse {
        let room = ActivityRoomSummary(room: "客厅", activeMinutes: 28, intervalCount: 2)
        let previousDays = [18, 24, 21, 32, 27, 35].enumerated().map { index, minutes in
            ActivityDaySummary(
                date: "2026-07-\(22 + index)",
                hasData: true,
                activeMinutes: minutes,
                intervalCount: 2,
                personCountMax: 1,
                firstActivityAt: nil,
                lastActivityAt: nil,
                observedPostures: ["standing", "sitting"],
                rooms: [room]
            )
        }
        let today = ActivityDaySummary(
            date: "2026-07-28",
            hasData: true,
            activeMinutes: 30,
            intervalCount: 2,
            personCountMax: 1,
            firstActivityAt: nil,
            lastActivityAt: nil,
            observedPostures: ["standing", "sitting"],
            rooms: [room]
        )
        return ActivityOverviewResponse(
            date: "2026-07-28",
            today: today,
            sevenDayTrend: previousDays + [today],
            baseline: ActivityBaseline(comparableDays: 6, averageActiveMinutes: 26),
            dataQuality: ActivityDataQuality(
                status: "ready",
                hasTodayActivity: true,
                comparableDays: 6,
                minimumComparableDays: 3,
                canCompareRoutine: true,
                activityDurationComparisonReady: true
            ),
            facts: ["08:12 首次记录到活动", "客厅活动时间较集中"],
            attentionItems: nil,
            revision: "ui-test-overview-r1"
        )
    }

    private static var uiTestProducts: ProductRecommendationsResponse {
        ProductRecommendationsResponse(products: [
            ProductRecommendation(
                id: "product-1",
                category: "照明与视野",
                brand: "品牌 A",
                name: "感应小夜灯",
                summary: "夜间起身时自动提供柔和照明。",
                imageURL: "https://example.com/night-light.jpg",
                sourceName: "品牌官方页面",
                sourceURL: "https://example.com/night-light",
                suitability: ["夜间照明"],
                recommendationReason: "适合夜间照明需求",
                disclosure: "无赞助或返佣关系",
                verifiedAt: "2026-07-01T00:00:00+08:00"
            ),
            ProductRecommendation(
                id: "product-2",
                category: "日常生活与收纳",
                brand: "品牌 B",
                name: "抽屉分隔收纳盒",
                summary: "常用物品更容易分类和取放。",
                imageURL: "https://example.com/storage.jpg",
                sourceName: "品牌官方页面",
                sourceURL: "https://example.com/storage",
                suitability: ["物品收纳"],
                recommendationReason: "适合物品收纳需求",
                disclosure: "无赞助或返佣关系",
                verifiedAt: "2026-07-01T00:00:00+08:00"
            ),
            ProductRecommendation(
                id: "product-3",
                category: "居家防滑与安全",
                brand: "品牌 C",
                name: "浴室防滑垫",
                summary: "保持排水并增加湿区脚下摩擦。",
                imageURL: "https://example.com/mat.jpg",
                sourceName: "品牌官方页面",
                sourceURL: "https://example.com/mat",
                suitability: ["居家防滑"],
                recommendationReason: "适合居家防滑需求",
                disclosure: "无赞助或返佣关系",
                verifiedAt: "2026-07-01T00:00:00+08:00"
            ),
        ], revision: "ui-test-product-r1")
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
