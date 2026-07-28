import Foundation

actor AppRepository {
    typealias BootstrapLoader = @Sendable () async throws -> BootstrapResponse
    typealias BootstrapUpdate = @Sendable (Loadable<BootstrapResponse>) async -> Void
    typealias HomeLoader = @Sendable (String) async throws -> HomeResponse
    typealias HomeUpdate = @Sendable (Loadable<HomeResponse>) async -> Void
    typealias EventsLoader = @Sendable (String) async throws -> [AppEvent]
    typealias ProductsLoader = @Sendable (String) async throws -> ProductRecommendationsResponse
    typealias EventLoader = @Sendable (String) async throws -> AppEvent
    typealias EventActionLoader = @Sendable (String, String) async throws -> AppEvent
    typealias ProfileLoader = @Sendable (String) async throws -> ProfileData
    typealias RulesUpdater = @Sendable (String, RulePatch) async throws -> FamilyRules
    typealias CarePreferencesUpdater = @Sendable (String, CarePreferencesPatch) async throws -> CarePreferences
    typealias ProductPreferencesUpdater = @Sendable (String, ProductPreferences) async throws -> ProductPreferencesEnvelope
    typealias ElderProfileUpdater = @Sendable (String, String, ProfilePayload) async throws -> ElderProfile
    typealias MessageActionLoader = @Sendable (String, String, CareMessageActionRequest) async throws -> CareMessageActionResponse
    typealias MemoriesLoader = @Sendable (String) async throws -> FamilyMemoriesResponse
    typealias MemoryCreator = @Sendable (String, MemoryDraftRequest) async throws -> FamilyMemoryEnvelope
    typealias MemoryUpdater = @Sendable (String, String, MemoryDraftRequest) async throws -> FamilyMemoryEnvelope
    typealias MemoryCommentCreator = @Sendable (String, String, MemoryCommentRequest) async throws -> FamilyMemoryEnvelope
    typealias MemoryFavoriteUpdater = @Sendable (String, String, Bool) async throws -> FamilyMemoryEnvelope
    typealias MemoryDeleter = @Sendable (String, String) async throws -> MemoryDeleteResponse
    typealias MemoryMediaUploader = @Sendable (String, Data, String) async throws -> MemoryMediaUploadResponse
    typealias MemoryMediaBatchUploader = @Sendable (String, [MemoryUploadAsset]) async throws -> MemoryMediaBatchUploadResponse
    typealias ActivityTimelineLoader = @Sendable (String, String) async throws -> ActivityTimelineResponse
    typealias ActivityOverviewLoader = @Sendable (String, String) async throws -> ActivityOverviewResponse
    typealias ActivityHistoryDeleter = @Sendable (String) async throws -> ActivityHistoryDeleteResponse
    typealias CameraCreator = @Sendable (CameraCreateRequest) async throws -> CameraConfig
    typealias CameraUpdater = @Sendable (String, CameraUpdateRequest) async throws -> CameraConfig
    typealias CameraDeleter = @Sendable (String) async throws -> CameraDeleteResponse
    typealias DeviceUnbinder = @Sendable (String) async throws -> DeviceUnbindResponse
    typealias AccountExporter = @Sendable () async throws -> Data
    typealias AccountDeletionPlanLoader = @Sendable () async throws -> AccountDeletionPlan
    typealias AccountDeleter = @Sendable () async throws -> AccountDeleteResponse
    typealias FamilyMembersLoader = @Sendable (String) async throws -> FamilyMembersResponse
    typealias FamilyMemberRemover = @Sendable (String, String) async throws -> FamilyMemberRemovalResponse
    typealias FamilyLeaver = @Sendable (String) async throws -> FamilyLeaveResponse
    typealias FamilyOwnershipTransferer = @Sendable (String, String) async throws -> FamilyOwnershipTransferResponse
    typealias FamilyInvitationsLoader = @Sendable (String) async throws -> FamilyInvitationsResponse
    typealias FamilyInvitationCreator = @Sendable (String) async throws -> FamilyInvitation
    typealias FamilyInvitationRevoker = @Sendable (String, String) async throws -> FamilyInvitation

    private let cache: DiskCache
    private let bootstrapLoader: BootstrapLoader
    private let homeLoader: HomeLoader
    private let eventsLoader: EventsLoader
    private let productsLoader: ProductsLoader
    private let eventLoader: EventLoader
    private let eventActionLoader: EventActionLoader
    private let profileLoader: ProfileLoader
    private let rulesUpdater: RulesUpdater
    private let carePreferencesUpdater: CarePreferencesUpdater
    private let productPreferencesUpdater: ProductPreferencesUpdater
    private let elderProfileUpdater: ElderProfileUpdater
    private let messageActionLoader: MessageActionLoader
    private let memoriesLoader: MemoriesLoader
    private let memoryCreator: MemoryCreator
    private let memoryUpdater: MemoryUpdater
    private let memoryCommentCreator: MemoryCommentCreator
    private let memoryFavoriteUpdater: MemoryFavoriteUpdater
    private let memoryDeleter: MemoryDeleter
    private let memoryMediaUploader: MemoryMediaUploader
    private let memoryMediaBatchUploader: MemoryMediaBatchUploader
    private let activityTimelineLoader: ActivityTimelineLoader
    private let activityOverviewLoader: ActivityOverviewLoader
    private let activityHistoryDeleter: ActivityHistoryDeleter
    private let cameraCreator: CameraCreator
    private let cameraUpdater: CameraUpdater
    private let cameraDeleter: CameraDeleter
    private let deviceUnbinder: DeviceUnbinder
    private let accountExporter: AccountExporter
    private let accountDeletionPlanLoader: AccountDeletionPlanLoader
    private let accountDeleter: AccountDeleter
    private let familyMembersLoader: FamilyMembersLoader
    private let familyMemberRemover: FamilyMemberRemover
    private let familyLeaver: FamilyLeaver
    private let familyOwnershipTransferer: FamilyOwnershipTransferer
    private let familyInvitationsLoader: FamilyInvitationsLoader
    private let familyInvitationCreator: FamilyInvitationCreator
    private let familyInvitationRevoker: FamilyInvitationRevoker
    private var bootstrapTasks: [CacheScope: Task<BootstrapResponse, Error>] = [:]
    private var homeTasks: [CacheScope: Task<HomeResponse, Error>] = [:]
    private var eventsTasks: [CacheScope: Task<[AppEvent], Error>] = [:]
    private var productsTasks: [CacheScope: Task<ProductRecommendationsResponse, Error>] = [:]
    private var eventTasks: [String: Task<AppEvent, Error>] = [:]
    private var profileTasks: [CacheScope: Task<ProfileData, Error>] = [:]
    private var memoriesTasks: [CacheScope: Task<FamilyMemoriesResponse, Error>] = [:]
    private var activityTimelineTasks: [String: Task<ActivityTimelineResponse, Error>] = [:]
    private var activityOverviewTasks: [String: Task<ActivityOverviewResponse, Error>] = [:]

    init(
        cache: DiskCache,
        bootstrapLoader: @escaping BootstrapLoader,
        homeLoader: @escaping HomeLoader = { _ in throw APIError.invalidResponse },
        eventsLoader: @escaping EventsLoader = { _ in throw APIError.invalidResponse },
        productsLoader: @escaping ProductsLoader = { _ in throw APIError.invalidResponse },
        eventLoader: @escaping EventLoader = { _ in throw APIError.invalidResponse },
        eventActionLoader: @escaping EventActionLoader = { _, _ in throw APIError.invalidResponse },
        profileLoader: @escaping ProfileLoader = { _ in throw APIError.invalidResponse },
        rulesUpdater: @escaping RulesUpdater = { _, _ in throw APIError.invalidResponse },
        carePreferencesUpdater: @escaping CarePreferencesUpdater = { _, _ in throw APIError.invalidResponse },
        productPreferencesUpdater: @escaping ProductPreferencesUpdater = { _, _ in throw APIError.invalidResponse },
        elderProfileUpdater: @escaping ElderProfileUpdater = { _, _, _ in throw APIError.invalidResponse },
        messageActionLoader: @escaping MessageActionLoader = { _, _, _ in throw APIError.invalidResponse },
        memoriesLoader: @escaping MemoriesLoader = { _ in throw APIError.invalidResponse },
        memoryCreator: @escaping MemoryCreator = { _, _ in throw APIError.invalidResponse },
        memoryUpdater: @escaping MemoryUpdater = { _, _, _ in throw APIError.invalidResponse },
        memoryCommentCreator: @escaping MemoryCommentCreator = { _, _, _ in throw APIError.invalidResponse },
        memoryFavoriteUpdater: @escaping MemoryFavoriteUpdater = { _, _, _ in throw APIError.invalidResponse },
        memoryDeleter: @escaping MemoryDeleter = { _, _ in throw APIError.invalidResponse },
        memoryMediaUploader: @escaping MemoryMediaUploader = { _, _, _ in throw APIError.invalidResponse },
        memoryMediaBatchUploader: MemoryMediaBatchUploader? = nil,
        activityTimelineLoader: @escaping ActivityTimelineLoader = { _, _ in throw APIError.invalidResponse },
        activityOverviewLoader: @escaping ActivityOverviewLoader = { _, _ in throw APIError.invalidResponse },
        activityHistoryDeleter: @escaping ActivityHistoryDeleter = { _ in throw APIError.invalidResponse },
        cameraCreator: @escaping CameraCreator = { _ in throw APIError.invalidResponse },
        cameraUpdater: @escaping CameraUpdater = { _, _ in throw APIError.invalidResponse },
        cameraDeleter: @escaping CameraDeleter = { _ in throw APIError.invalidResponse },
        deviceUnbinder: @escaping DeviceUnbinder = { _ in throw APIError.invalidResponse },
        accountExporter: @escaping AccountExporter = { throw APIError.invalidResponse },
        accountDeletionPlanLoader: @escaping AccountDeletionPlanLoader = { throw APIError.invalidResponse },
        accountDeleter: @escaping AccountDeleter = { throw APIError.invalidResponse },
        familyMembersLoader: @escaping FamilyMembersLoader = { _ in throw APIError.invalidResponse },
        familyMemberRemover: @escaping FamilyMemberRemover = { _, _ in throw APIError.invalidResponse },
        familyLeaver: @escaping FamilyLeaver = { _ in throw APIError.invalidResponse },
        familyOwnershipTransferer: @escaping FamilyOwnershipTransferer = { _, _ in throw APIError.invalidResponse },
        familyInvitationsLoader: @escaping FamilyInvitationsLoader = { _ in throw APIError.invalidResponse },
        familyInvitationCreator: @escaping FamilyInvitationCreator = { _ in throw APIError.invalidResponse },
        familyInvitationRevoker: @escaping FamilyInvitationRevoker = { _, _ in throw APIError.invalidResponse }
    ) {
        self.cache = cache
        self.bootstrapLoader = bootstrapLoader
        self.homeLoader = homeLoader
        self.eventsLoader = eventsLoader
        self.productsLoader = productsLoader
        self.eventLoader = eventLoader
        self.eventActionLoader = eventActionLoader
        self.profileLoader = profileLoader
        self.rulesUpdater = rulesUpdater
        self.carePreferencesUpdater = carePreferencesUpdater
        self.productPreferencesUpdater = productPreferencesUpdater
        self.elderProfileUpdater = elderProfileUpdater
        self.messageActionLoader = messageActionLoader
        self.memoriesLoader = memoriesLoader
        self.memoryCreator = memoryCreator
        self.memoryUpdater = memoryUpdater
        self.memoryCommentCreator = memoryCommentCreator
        self.memoryFavoriteUpdater = memoryFavoriteUpdater
        self.memoryDeleter = memoryDeleter
        self.memoryMediaUploader = memoryMediaUploader
        self.memoryMediaBatchUploader = memoryMediaBatchUploader ?? { familyID, images in
            var assets: [MemoryUploadedAsset] = []
            for image in images {
                assets.append(try await memoryMediaUploader(familyID, image.data, image.contentType).asset)
            }
            return MemoryMediaBatchUploadResponse(assets: assets)
        }
        self.activityTimelineLoader = activityTimelineLoader
        self.activityOverviewLoader = activityOverviewLoader
        self.activityHistoryDeleter = activityHistoryDeleter
        self.cameraCreator = cameraCreator
        self.cameraUpdater = cameraUpdater
        self.cameraDeleter = cameraDeleter
        self.deviceUnbinder = deviceUnbinder
        self.accountExporter = accountExporter
        self.accountDeletionPlanLoader = accountDeletionPlanLoader
        self.accountDeleter = accountDeleter
        self.familyMembersLoader = familyMembersLoader
        self.familyMemberRemover = familyMemberRemover
        self.familyLeaver = familyLeaver
        self.familyOwnershipTransferer = familyOwnershipTransferer
        self.familyInvitationsLoader = familyInvitationsLoader
        self.familyInvitationCreator = familyInvitationCreator
        self.familyInvitationRevoker = familyInvitationRevoker
    }

    func fetchBootstrap() async throws -> BootstrapResponse {
        try await bootstrapLoader()
    }

    func cacheBootstrap(_ value: BootstrapResponse, scope: CacheScope) async {
        try? await cache.write(value, key: "bootstrap", scope: scope, ttl: 24 * 60 * 60)
    }

    func bootstrap(scope: CacheScope, onUpdate: @escaping BootstrapUpdate) async {
        let cached = try? await cache.read(BootstrapResponse.self, key: "bootstrap", scope: scope)
        await onUpdate(Loadable(value: cached, isRefreshing: true, staleReason: nil))

        do {
            let refreshed = try await refreshBootstrap(scope: scope)
            try await cache.write(refreshed, key: "bootstrap", scope: scope, ttl: 24 * 60 * 60)
            await onUpdate(Loadable(value: refreshed, isRefreshing: false, staleReason: nil))
        } catch is CancellationError {
            await onUpdate(Loadable(value: cached, isRefreshing: false, staleReason: nil))
        } catch {
            await onUpdate(Loadable(
                value: cached,
                isRefreshing: false,
                staleReason: cached == nil ? error.localizedDescription : "暂时无法刷新，正在显示上次内容"
            ))
        }
    }

    func home(scope: CacheScope, onUpdate: @escaping HomeUpdate) async {
        let cached = try? await cache.read(HomeResponse.self, key: "home", scope: scope)
        await onUpdate(Loadable(value: cached, isRefreshing: true, staleReason: nil))

        do {
            let refreshed = try await refreshHome(scope: scope)
            try await cache.write(refreshed, key: "home", scope: scope, ttl: 6 * 60 * 60)
            await onUpdate(Loadable(value: refreshed, isRefreshing: false, staleReason: nil))
        } catch is CancellationError {
            await onUpdate(Loadable(value: cached, isRefreshing: false, staleReason: nil))
        } catch {
            await onUpdate(Loadable(
                value: cached,
                isRefreshing: false,
                staleReason: cached == nil ? error.localizedDescription : "暂时无法更新"
            ))
        }
    }

    func events(scope: CacheScope, onUpdate: @escaping @Sendable (Loadable<[AppEvent]>) async -> Void) async {
        let cached = try? await cache.read([AppEvent].self, key: "events", scope: scope)
        await onUpdate(Loadable(value: cached, isRefreshing: true, staleReason: nil))

        do {
            let refreshed = try await refreshEvents(scope: scope)
            try await cache.write(refreshed, key: "events", scope: scope, ttl: 24 * 60 * 60)
            await onUpdate(Loadable(value: refreshed, isRefreshing: false, staleReason: nil))
        } catch is CancellationError {
            await onUpdate(Loadable(value: cached, isRefreshing: false, staleReason: nil))
        } catch {
            await onUpdate(Loadable(
                value: cached,
                isRefreshing: false,
                staleReason: cached == nil ? error.localizedDescription : "暂时无法更新"
            ))
        }
    }

    func products(
        scope: CacheScope,
        onUpdate: @escaping @Sendable (Loadable<ProductRecommendationsResponse>) async -> Void
    ) async {
        let cached = try? await cache.read(ProductRecommendationsResponse.self, key: "products", scope: scope)
        await onUpdate(Loadable(value: cached, isRefreshing: true, staleReason: nil))

        do {
            let refreshed = try await refreshProducts(scope: scope)
            try await cache.write(refreshed, key: "products", scope: scope, ttl: 24 * 60 * 60)
            await onUpdate(Loadable(value: refreshed, isRefreshing: false, staleReason: nil))
        } catch is CancellationError {
            await onUpdate(Loadable(value: cached, isRefreshing: false, staleReason: nil))
        } catch {
            await onUpdate(Loadable(
                value: cached,
                isRefreshing: false,
                staleReason: cached == nil ? "推荐暂时无法更新" : "当前显示上次更新的推荐"
            ))
        }
    }

    func fetchEvent(_ id: String) async throws -> AppEvent {
        if let task = eventTasks[id] { return try await task.value }
        let task = Task { try await eventLoader(id) }
        eventTasks[id] = task
        defer { eventTasks[id] = nil }
        return try await task.value
    }

    func updateEvent(_ event: AppEvent, resolution: String) async throws -> AppEvent {
        let updated = try await eventActionLoader(event.id, resolution)
        return updated
    }

    func cacheEvents(_ events: [AppEvent], scope: CacheScope) async {
        try? await cache.write(events, key: "events", scope: scope, ttl: 24 * 60 * 60)
    }

    func profile(scope: CacheScope, onUpdate: @escaping @Sendable (Loadable<ProfileData>) async -> Void) async {
        let cached = try? await cache.read(ProfileData.self, key: "profile", scope: scope)
        await onUpdate(Loadable(value: cached, isRefreshing: true, staleReason: nil))

        do {
            let refreshed = try await refreshProfile(scope: scope)
            try await cache.write(refreshed, key: "profile", scope: scope, ttl: 24 * 60 * 60)
            await onUpdate(Loadable(value: refreshed, isRefreshing: false, staleReason: nil))
        } catch is CancellationError {
            await onUpdate(Loadable(value: cached, isRefreshing: false, staleReason: nil))
        } catch {
            await onUpdate(Loadable(
                value: cached,
                isRefreshing: false,
                staleReason: cached == nil ? "配置暂时无法更新" : "当前显示上次保存的配置"
            ))
        }
    }

    func updateRules(familyID: String, patch: RulePatch) async throws -> FamilyRules {
        try await rulesUpdater(familyID, patch)
    }

    func updateCarePreferences(familyID: String, patch: CarePreferencesPatch) async throws -> CarePreferences {
        try await carePreferencesUpdater(familyID, patch)
    }

    func updateProductPreferences(familyID: String, preferences: ProductPreferences) async throws -> ProductPreferences {
        try await productPreferencesUpdater(familyID, preferences).preferences
    }

    func updateElderProfile(familyID: String, elderID: String, payload: ProfilePayload) async throws -> ElderProfile {
        try await elderProfileUpdater(familyID, elderID, payload)
    }

    func recordMessageAction(
        familyID: String,
        messageID: String,
        request: CareMessageActionRequest
    ) async throws -> CareMessageActionResponse {
        try await messageActionLoader(familyID, messageID, request)
    }

    func memories(scope: CacheScope, onUpdate: @escaping @Sendable (Loadable<FamilyMemoriesResponse>) async -> Void) async {
        let cached = try? await cache.read(FamilyMemoriesResponse.self, key: "memories", scope: scope)
        await onUpdate(Loadable(value: cached, isRefreshing: true, staleReason: nil))
        do {
            let refreshed = try await refreshMemories(scope: scope)
            try await cache.write(refreshed, key: "memories", scope: scope, ttl: 24 * 60 * 60)
            await onUpdate(Loadable(value: refreshed, isRefreshing: false, staleReason: nil))
        } catch is CancellationError {
            await onUpdate(Loadable(value: cached, isRefreshing: false, staleReason: nil))
        } catch {
            await onUpdate(Loadable(value: cached, isRefreshing: false, staleReason: cached == nil ? "记忆暂时无法更新" : "当前显示上次内容"))
        }
    }

    func createMemory(familyID: String, request: MemoryDraftRequest) async throws -> FamilyMemory {
        try await memoryCreator(familyID, request).memory
    }

    func updateMemory(familyID: String, memoryID: String, request: MemoryDraftRequest) async throws -> FamilyMemory {
        try await memoryUpdater(familyID, memoryID, request).memory
    }

    func addMemoryComment(familyID: String, memoryID: String, body: String) async throws -> FamilyMemory {
        try await memoryCommentCreator(familyID, memoryID, MemoryCommentRequest(body: body)).memory
    }

    func setMemoryFavorite(familyID: String, memoryID: String, favorite: Bool) async throws -> FamilyMemory {
        try await memoryFavoriteUpdater(familyID, memoryID, favorite).memory
    }

    func deleteMemory(familyID: String, memoryID: String) async throws {
        _ = try await memoryDeleter(familyID, memoryID)
    }

    func uploadMemoryMedia(familyID: String, data: Data, contentType: String) async throws -> MemoryUploadedAsset {
        try await memoryMediaUploader(familyID, data, contentType).asset
    }

    func uploadMemoryMediaBatch(familyID: String, media: [MemoryUploadAsset]) async throws -> [MemoryUploadedAsset] {
        try await memoryMediaBatchUploader(familyID, media).assets
    }

    func cacheMemories(_ value: FamilyMemoriesResponse, scope: CacheScope) async {
        try? await cache.write(value, key: "memories", scope: scope, ttl: 24 * 60 * 60)
    }

    func cacheProfile(_ profile: ProfileData, scope: CacheScope) async {
        try? await cache.write(profile, key: "profile", scope: scope, ttl: 24 * 60 * 60)
    }

    func activityTimeline(
        scope: CacheScope,
        date: String,
        onUpdate: @escaping @Sendable (Loadable<ActivityTimelineResponse>) async -> Void
    ) async {
        let key = "activity-timeline-\(date)"
        let cached = try? await cache.read(ActivityTimelineResponse.self, key: key, scope: scope)
        await onUpdate(Loadable(value: cached, isRefreshing: true, staleReason: nil))
        do {
            let taskKey = "\(scope.userID):\(scope.familyID):\(date)"
            let refreshed: ActivityTimelineResponse
            if let task = activityTimelineTasks[taskKey] {
                refreshed = try await task.value
            } else {
                let task = Task { try await activityTimelineLoader(scope.familyID, date) }
                activityTimelineTasks[taskKey] = task
                defer { activityTimelineTasks[taskKey] = nil }
                refreshed = try await task.value
            }
            try await cache.write(refreshed, key: key, scope: scope, ttl: 24 * 60 * 60)
            await onUpdate(Loadable(value: refreshed, isRefreshing: false, staleReason: nil))
        } catch is CancellationError {
            await onUpdate(Loadable(value: cached, isRefreshing: false, staleReason: nil))
        } catch {
            await onUpdate(Loadable(value: cached, isRefreshing: false, staleReason: cached == nil ? "轨迹暂时无法更新" : "当前显示上次活动轨迹"))
        }
    }

    func activityOverview(
        scope: CacheScope,
        date: String,
        onUpdate: @escaping @Sendable (Loadable<ActivityOverviewResponse>) async -> Void
    ) async {
        let key = "activity-overview-\(date)"
        let cached = try? await cache.read(ActivityOverviewResponse.self, key: key, scope: scope)
        await onUpdate(Loadable(value: cached, isRefreshing: true, staleReason: nil))
        do {
            let taskKey = "\(scope.userID):\(scope.familyID):\(date)"
            let refreshed: ActivityOverviewResponse
            if let task = activityOverviewTasks[taskKey] {
                refreshed = try await task.value
            } else {
                let task = Task { try await activityOverviewLoader(scope.familyID, date) }
                activityOverviewTasks[taskKey] = task
                defer { activityOverviewTasks[taskKey] = nil }
                refreshed = try await task.value
            }
            try await cache.write(refreshed, key: key, scope: scope, ttl: 24 * 60 * 60)
            await onUpdate(Loadable(value: refreshed, isRefreshing: false, staleReason: nil))
        } catch is CancellationError {
            await onUpdate(Loadable(value: cached, isRefreshing: false, staleReason: nil))
        } catch {
            await onUpdate(Loadable(value: cached, isRefreshing: false, staleReason: cached == nil ? "活动摘要暂时无法更新" : "当前显示上次活动摘要"))
        }
    }

    func deleteActivityHistory(scope: CacheScope, date: String) async throws -> Int {
        let response = try await activityHistoryDeleter(scope.familyID)
        try? await cache.remove(key: "activity-timeline-\(date)", scope: scope)
        try? await cache.remove(key: "activity-overview-\(date)", scope: scope)
        return response.deleted
    }

    func createCamera(_ request: CameraCreateRequest) async throws -> CameraConfig {
        try await cameraCreator(request)
    }

    func updateCamera(id: String, request: CameraUpdateRequest) async throws -> CameraConfig {
        try await cameraUpdater(id, request)
    }

    func deleteCamera(id: String) async throws {
        _ = try await cameraDeleter(id)
    }

    func unbindDevice(bindingID: String) async throws -> DeviceUnbindResponse {
        try await deviceUnbinder(bindingID)
    }

    func exportAccountData() async throws -> Data {
        try await accountExporter()
    }

    func accountDeletionPlan() async throws -> AccountDeletionPlan {
        try await accountDeletionPlanLoader()
    }

    func deleteAccount() async throws {
        let response = try await accountDeleter()
        guard response.deleted else { throw APIError.invalidResponse }
    }

    func familyMembers(familyID: String) async throws -> FamilyMembersResponse {
        try await familyMembersLoader(familyID)
    }

    func removeFamilyMember(familyID: String, memberID: String) async throws {
        guard try await familyMemberRemover(familyID, memberID).removed else { throw APIError.invalidResponse }
    }

    func leaveFamily(familyID: String) async throws {
        guard try await familyLeaver(familyID).left else { throw APIError.invalidResponse }
    }

    func transferFamilyOwnership(familyID: String, memberID: String) async throws {
        guard try await familyOwnershipTransferer(familyID, memberID).transferred else { throw APIError.invalidResponse }
    }

    func familyInvitations(familyID: String) async throws -> FamilyInvitationsResponse {
        try await familyInvitationsLoader(familyID)
    }

    func createFamilyInvitation(familyID: String) async throws -> FamilyInvitation {
        try await familyInvitationCreator(familyID)
    }

    func revokeFamilyInvitation(familyID: String, invitationID: String) async throws -> FamilyInvitation {
        try await familyInvitationRevoker(familyID, invitationID)
    }

    private func refreshBootstrap(scope: CacheScope) async throws -> BootstrapResponse {
        if let task = bootstrapTasks[scope] { return try await task.value }
        let task = Task { try await bootstrapLoader() }
        bootstrapTasks[scope] = task
        defer { bootstrapTasks[scope] = nil }
        return try await task.value
    }

    private func refreshHome(scope: CacheScope) async throws -> HomeResponse {
        if let task = homeTasks[scope] { return try await task.value }
        let task = Task { try await homeLoader(scope.familyID) }
        homeTasks[scope] = task
        defer { homeTasks[scope] = nil }
        return try await task.value
    }

    private func refreshEvents(scope: CacheScope) async throws -> [AppEvent] {
        if let task = eventsTasks[scope] { return try await task.value }
        let task = Task { try await eventsLoader(scope.familyID) }
        eventsTasks[scope] = task
        defer { eventsTasks[scope] = nil }
        return try await task.value
    }

    private func refreshProducts(scope: CacheScope) async throws -> ProductRecommendationsResponse {
        if let task = productsTasks[scope] { return try await task.value }
        let task = Task { try await productsLoader(scope.familyID) }
        productsTasks[scope] = task
        defer { productsTasks[scope] = nil }
        return try await task.value
    }

    private func refreshProfile(scope: CacheScope) async throws -> ProfileData {
        if let task = profileTasks[scope] { return try await task.value }
        let task = Task { try await profileLoader(scope.familyID) }
        profileTasks[scope] = task
        defer { profileTasks[scope] = nil }
        return try await task.value
    }

    private func refreshMemories(scope: CacheScope) async throws -> FamilyMemoriesResponse {
        if let task = memoriesTasks[scope] { return try await task.value }
        let task = Task { try await memoriesLoader(scope.familyID) }
        memoriesTasks[scope] = task
        defer { memoriesTasks[scope] = nil }
        return try await task.value
    }
}
