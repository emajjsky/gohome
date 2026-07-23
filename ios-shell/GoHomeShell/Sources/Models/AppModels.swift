import Foundation

struct Loadable<Value: Equatable>: Equatable {
    var value: Value?
    var isRefreshing = false
    var staleReason: String?
}

struct AppUser: Codable, Equatable, Sendable {
    let id: String
    let phone: String?
    let displayName: String?

    enum CodingKeys: String, CodingKey {
        case id, phone
        case displayName = "display_name"
    }

    init(id: String, phone: String?, displayName: String?) {
        self.id = id
        self.phone = phone
        self.displayName = displayName
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decodeFlexibleID(forKey: .id)
        phone = try values.decodeIfPresent(String.self, forKey: .phone)
        displayName = try values.decodeIfPresent(String.self, forKey: .displayName)
    }
}

struct AppFamily: Codable, Equatable, Sendable {
    let id: String
    let name: String
    let role: String?
    let memberCount: Int?
    let joinCode: String?

    init(id: String, name: String, role: String?, memberCount: Int? = nil, joinCode: String? = nil) {
        self.id = id
        self.name = name
        self.role = role
        self.memberCount = memberCount
        self.joinCode = joinCode
    }

    enum CodingKeys: String, CodingKey {
        case id, name, role
        case memberCount = "member_count"
        case joinCode = "join_code"
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decodeFlexibleID(forKey: .id)
        name = try values.decode(String.self, forKey: .name)
        role = try values.decodeIfPresent(String.self, forKey: .role)
        memberCount = try values.decodeIfPresent(Int.self, forKey: .memberCount)
        joinCode = try values.decodeIfPresent(String.self, forKey: .joinCode)
    }
}

struct OnboardingState: Codable, Equatable, Sendable {
    let nextStep: OnboardingStep
    let complete: Bool

    enum CodingKeys: String, CodingKey {
        case nextStep = "next_step"
        case complete
    }
}

struct BootstrapResponse: Codable, Equatable, Sendable {
    let user: AppUser
    let families: [AppFamily]
    let activeFamilyID: String?
    let onboarding: OnboardingState
    let unreadCount: Int
    let revision: String

    enum CodingKeys: String, CodingKey {
        case user, families, onboarding, revision
        case activeFamilyID = "active_family_id"
        case unreadCount = "unread_count"
    }

    init(user: AppUser, families: [AppFamily], activeFamilyID: String?, onboarding: OnboardingState, unreadCount: Int, revision: String) {
        self.user = user
        self.families = families
        self.activeFamilyID = activeFamilyID
        self.onboarding = onboarding
        self.unreadCount = unreadCount
        self.revision = revision
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        user = try values.decode(AppUser.self, forKey: .user)
        families = try values.decode([AppFamily].self, forKey: .families)
        activeFamilyID = try values.decodeFlexibleIDIfPresent(forKey: .activeFamilyID)
        onboarding = try values.decode(OnboardingState.self, forKey: .onboarding)
        unreadCount = try values.decode(Int.self, forKey: .unreadCount)
        revision = try values.decode(String.self, forKey: .revision)
    }
}

struct HomeResponse: Codable, Equatable, Sendable {
    let family: AppFamily?
    let weather: HomeWeather?
    let calendar: [HomeCalendarEvent]
    let distance: HomeDistance?
    let criticalAlert: HomeCriticalAlert?
    let careMessage: CareMessage?
    let articles: [HomeArticle]
    let cameras: [HomeCamera]
    let revision: String

    enum CodingKeys: String, CodingKey {
        case family, weather, calendar, distance, articles, cameras, revision
        case criticalAlert = "critical_alert"
        case careMessage = "care_message"
    }
}

struct CareMessage: Codable, Equatable, Sendable, Identifiable {
    let messageID: String
    let messageType: String
    let title: String
    let subtitle: String
    let body: String
    let facts: [String]
    let actions: [CareMessageActionOption]
    let status: String
    let metadata: CareMessageMetadata
    let createdAt: String?
    let updatedAt: String?

    var id: String { messageID }

    enum CodingKeys: String, CodingKey {
        case title, subtitle, body, facts, actions, status, metadata
        case messageID = "message_id"
        case messageType = "message_type"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct CareMessageMetadata: Codable, Equatable, Sendable {
    let triggerReason: String
    let topics: [String]
    let messageVariants: [String]
    let snoozedUntil: String?

    enum CodingKeys: String, CodingKey {
        case topics
        case triggerReason = "trigger_reason"
        case messageVariants = "message_variants"
        case snoozedUntil = "snoozed_until"
    }
}

struct CareMessageActionOption: Codable, Equatable, Sendable {
    let type: String
    let label: String?

    enum CodingKeys: String, CodingKey { case type, key, label }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        type = try values.decodeIfPresent(String.self, forKey: .type)
            ?? values.decode(String.self, forKey: .key)
        label = try values.decodeIfPresent(String.self, forKey: .label)
    }

    func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encode(type, forKey: .type)
        try values.encodeIfPresent(label, forKey: .label)
    }
}

struct CareMessageActionRequest: Encodable, Equatable, Sendable {
    let actionType: String
    let payload: [String: String]
    let idempotencyKey: String

    enum CodingKeys: String, CodingKey {
        case payload
        case actionType = "action_type"
        case idempotencyKey = "idempotency_key"
    }
}

struct CareMessageActionResponse: Decodable, Equatable, Sendable {
    let message: CareMessage
}

struct ActivityTimelineResponse: Codable, Equatable, Sendable {
    let date: String?
    let intervals: [ActivityInterval]
    let revision: String
}

struct ActivityInterval: Codable, Equatable, Sendable, Identifiable {
    let id: String
    let cameraID: String?
    let room: String
    let startedAt: String
    let endedAt: String
    let personCountMax: Int
    let postures: [String]
    let confidence: Double?

    enum CodingKeys: String, CodingKey {
        case id, room, postures, confidence
        case cameraID = "camera_id"
        case startedAt = "started_at"
        case endedAt = "ended_at"
        case personCountMax = "person_count_max"
    }
}

struct FamilyMemoriesResponse: Codable, Equatable, Sendable {
    let memories: [FamilyMemory]
    let revision: String
}

struct FamilyMemoryEnvelope: Codable, Equatable, Sendable {
    let memory: FamilyMemory
}

struct FamilyMemory: Codable, Equatable, Sendable, Identifiable {
    let id: String
    let familyID: String
    let author: MemoryAuthor?
    let body: String
    let happenedAt: String
    let locationName: String
    let people: [String]
    let media: [MemoryMedia]
    let comments: [MemoryComment]
    let favoriteCount: Int
    let isFavorite: Bool
    let createdAt: String?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, author, body, people, media, comments
        case familyID = "family_id"
        case happenedAt = "happened_at"
        case locationName = "location_name"
        case favoriteCount = "favorite_count"
        case isFavorite = "is_favorite"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct MemoryAuthor: Codable, Equatable, Sendable {
    let id: String
    let displayName: String

    enum CodingKeys: String, CodingKey {
        case id
        case displayName = "display_name"
    }
}

struct MemoryMedia: Codable, Equatable, Sendable, Identifiable {
    let id: String
    let assetID: String
    let imageURL: String
    let sortOrder: Int
    let altText: String

    enum CodingKeys: String, CodingKey {
        case id
        case assetID = "asset_id"
        case imageURL = "image_url"
        case sortOrder = "sort_order"
        case altText = "alt_text"
    }
}

struct MemoryComment: Codable, Equatable, Sendable, Identifiable {
    let id: String
    let authorUserID: String
    let body: String
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, body
        case authorUserID = "author_user_id"
        case createdAt = "created_at"
    }
}

struct MemoryDraftRequest: Encodable, Equatable, Sendable {
    let body: String
    let happenedAt: String
    let locationName: String
    let people: [String]
    let assetIDs: [String]

    enum CodingKeys: String, CodingKey {
        case body, people
        case happenedAt = "happened_at"
        case locationName = "location_name"
        case assetIDs = "asset_ids"
    }
}

struct MemoryCommentRequest: Encodable, Equatable, Sendable {
    let body: String
}

struct MemoryMediaUploadResponse: Decodable, Equatable, Sendable {
    let asset: MemoryUploadedAsset
}

struct MemoryUploadedAsset: Decodable, Equatable, Sendable {
    let id: String
    let contentType: String
    let imageURL: String
    let sizeBytes: Int

    enum CodingKeys: String, CodingKey {
        case id
        case contentType = "content_type"
        case imageURL = "image_url"
        case sizeBytes = "size_bytes"
    }
}

struct MemoryDeleteResponse: Decodable, Equatable, Sendable {
    let deleted: Bool
    let memoryID: String

    enum CodingKeys: String, CodingKey {
        case deleted
        case memoryID = "memory_id"
    }
}

struct HomeWeather: Codable, Equatable, Sendable {
    let city: String
    let temperature: Double
    let condition: String

    init(city: String, temperature: Double, condition: String) {
        self.city = city
        self.temperature = temperature
        self.condition = condition
    }

    enum CodingKeys: String, CodingKey { case city, temperature, condition }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        city = try values.decodeIfPresent(String.self, forKey: .city) ?? ""
        condition = try values.decodeIfPresent(String.self, forKey: .condition) ?? ""
        if let number = try? values.decode(Double.self, forKey: .temperature) {
            temperature = number
        } else if let text = try? values.decode(String.self, forKey: .temperature), let number = Double(text) {
            temperature = number
        } else {
            throw DecodingError.typeMismatch(
                Double.self,
                DecodingError.Context(codingPath: decoder.codingPath, debugDescription: "Expected numeric weather temperature")
            )
        }
    }
}

struct HomeCalendarEvent: Codable, Equatable, Sendable, Identifiable {
    let id: String
    let title: String
    let startsAt: String

    init(id: String, title: String, startsAt: String) {
        self.id = id
        self.title = title
        self.startsAt = startsAt
    }

    enum CodingKeys: String, CodingKey {
        case id, title
        case startsAt = "starts_at"
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decodeFlexibleID(forKey: .id)
        title = try values.decode(String.self, forKey: .title)
        startsAt = try values.decode(String.self, forKey: .startsAt)
    }
}

struct HomeDistance: Codable, Equatable, Sendable {
    let meters: Double
    let travelMinutes: Int?
    let userLatitude: Double?
    let userLongitude: Double?
    let homeLatitude: Double?
    let homeLongitude: Double?

    init(
        meters: Double,
        travelMinutes: Int?,
        userLatitude: Double? = nil,
        userLongitude: Double? = nil,
        homeLatitude: Double? = nil,
        homeLongitude: Double? = nil
    ) {
        self.meters = meters
        self.travelMinutes = travelMinutes
        self.userLatitude = userLatitude
        self.userLongitude = userLongitude
        self.homeLatitude = homeLatitude
        self.homeLongitude = homeLongitude
    }

    enum CodingKeys: String, CodingKey {
        case meters
        case travelMinutes = "travel_minutes"
        case userLatitude = "user_latitude"
        case userLongitude = "user_longitude"
        case homeLatitude = "home_latitude"
        case homeLongitude = "home_longitude"
    }
}

struct HomeCriticalAlert: Codable, Equatable, Sendable, Identifiable {
    let id: String
    let title: String
    let level: String
    let acknowledged: Bool

    init(id: String, title: String, level: String, acknowledged: Bool) {
        self.id = id
        self.title = title
        self.level = level
        self.acknowledged = acknowledged
    }

    enum CodingKeys: String, CodingKey { case id, title, level, acknowledged }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decodeFlexibleID(forKey: .id)
        title = try values.decodeIfPresent(String.self, forKey: .title) ?? "需要关注"
        level = try values.decodeIfPresent(String.self, forKey: .level) ?? "critical"
        acknowledged = try values.decodeIfPresent(Bool.self, forKey: .acknowledged) ?? false
    }
}

struct HomeArticle: Codable, Equatable, Sendable, Identifiable {
    let id: String
    let category: String
    let title: String
    let summary: String
    let imageURL: String
    let sourceName: String
    let sourceURL: String
    let publishedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, category, title, summary
        case imageURL = "image_url"
        case sourceName = "source_name"
        case sourceURL = "source_url"
        case publishedAt = "published_at"
    }
}

struct HomeCamera: Codable, Equatable, Sendable, Identifiable {
    let id: String
    let name: String
    let status: String?

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decodeFlexibleID(forKey: .id)
        name = try values.decodeIfPresent(String.self, forKey: .name) ?? "摄像头"
        status = try values.decodeIfPresent(String.self, forKey: .status)
    }

    enum CodingKeys: String, CodingKey { case id, name, status }
}

struct AppEvent: Codable, Equatable, Sendable, Identifiable {
    let id: String
    let type: String
    let level: String
    let summary: String?
    let room: String
    let cameraID: String?
    let cameraName: String
    let occurredAt: String
    let createdAt: String
    let updatedAt: String
    let acknowledged: Bool
    let resolution: String
    let snapshotURL: String?
    let mediaAssetID: String?
    let evidenceMedia: [EventEvidence]
    let payload: EventPayload

    enum CodingKeys: String, CodingKey {
        case id, type, level, summary, room, resolution, acknowledged, payload
        case cameraID = "camera_id"
        case cameraName = "camera_name"
        case occurredAt = "occurred_at"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case snapshotURL = "snapshot_url"
        case mediaAssetID = "media_asset_id"
        case evidenceMedia = "evidence_media"
    }

    init(
        id: String,
        type: String,
        level: String,
        summary: String? = nil,
        room: String = "",
        cameraID: String? = nil,
        cameraName: String = "",
        occurredAt: String,
        createdAt: String,
        updatedAt: String,
        acknowledged: Bool = false,
        resolution: String = "",
        snapshotURL: String? = nil,
        mediaAssetID: String? = nil,
        evidenceMedia: [EventEvidence] = [],
        payload: EventPayload = EventPayload()
    ) {
        self.id = id
        self.type = type
        self.level = level
        self.summary = summary
        self.room = room
        self.cameraID = cameraID
        self.cameraName = cameraName
        self.occurredAt = occurredAt
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.acknowledged = acknowledged
        self.resolution = resolution
        self.snapshotURL = snapshotURL
        self.mediaAssetID = mediaAssetID
        self.evidenceMedia = evidenceMedia
        self.payload = payload
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decodeFlexibleID(forKey: .id)
        type = try values.decodeIfPresent(String.self, forKey: .type) ?? "unknown"
        level = try values.decodeIfPresent(String.self, forKey: .level) ?? "info"
        summary = try values.decodeIfPresent(String.self, forKey: .summary)
        room = try values.decodeIfPresent(String.self, forKey: .room) ?? ""
        cameraID = try values.decodeFlexibleIDIfPresent(forKey: .cameraID)
        cameraName = try values.decodeIfPresent(String.self, forKey: .cameraName) ?? ""
        occurredAt = try values.decodeIfPresent(String.self, forKey: .occurredAt) ?? ""
        createdAt = try values.decodeIfPresent(String.self, forKey: .createdAt) ?? occurredAt
        updatedAt = try values.decodeIfPresent(String.self, forKey: .updatedAt) ?? createdAt
        acknowledged = try values.decodeIfPresent(Bool.self, forKey: .acknowledged) ?? false
        resolution = try values.decodeIfPresent(String.self, forKey: .resolution) ?? ""
        snapshotURL = try values.decodeIfPresent(String.self, forKey: .snapshotURL)
        mediaAssetID = try values.decodeFlexibleIDIfPresent(forKey: .mediaAssetID)
        evidenceMedia = try values.decodeIfPresent([EventEvidence].self, forKey: .evidenceMedia) ?? []
        payload = try values.decodeIfPresent(EventPayload.self, forKey: .payload) ?? EventPayload()
    }
}

struct EventEvidence: Codable, Equatable, Sendable, Identifiable {
    let assetID: String
    let role: String
    let capturedAt: String
    let postures: [String]

    var id: String { assetID + ":" + role }

    enum CodingKeys: String, CodingKey {
        case assetID = "asset_id"
        case role, capturedAt = "captured_at", postures
    }

    init(assetID: String, role: String, capturedAt: String, postures: [String] = []) {
        self.assetID = assetID
        self.role = role
        self.capturedAt = capturedAt
        self.postures = postures
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        assetID = try values.decodeFlexibleID(forKey: .assetID)
        role = try values.decodeIfPresent(String.self, forKey: .role) ?? "evidence"
        capturedAt = try values.decodeIfPresent(String.self, forKey: .capturedAt) ?? ""
        postures = try values.decodeIfPresent([String].self, forKey: .postures) ?? []
    }
}

struct EventPayload: Codable, Equatable, Sendable {
    let incident: EventIncident?
    let verification: EventVerification?
    let rule: EventRule?

    init(incident: EventIncident? = nil, verification: EventVerification? = nil, rule: EventRule? = nil) {
        self.incident = incident
        self.verification = verification
        self.rule = rule
    }
}

struct EventIncident: Codable, Equatable, Sendable {
    let status: String
    let primaryEventID: String?
    let sourceCameraIDs: [String]
    let startedAt: String?
    let transitions: [EventTransition]

    enum CodingKeys: String, CodingKey {
        case status, transitions
        case primaryEventID = "primary_event_id"
        case sourceCameraIDs = "source_camera_ids"
        case startedAt = "started_at"
    }

    init(
        status: String = "",
        primaryEventID: String? = nil,
        sourceCameraIDs: [String] = [],
        startedAt: String? = nil,
        transitions: [EventTransition] = []
    ) {
        self.status = status
        self.primaryEventID = primaryEventID
        self.sourceCameraIDs = sourceCameraIDs
        self.startedAt = startedAt
        self.transitions = transitions
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        status = try values.decodeIfPresent(String.self, forKey: .status) ?? ""
        primaryEventID = try values.decodeFlexibleIDIfPresent(forKey: .primaryEventID)
        sourceCameraIDs = try values.decodeFlexibleIDsIfPresent(forKey: .sourceCameraIDs) ?? []
        startedAt = try values.decodeIfPresent(String.self, forKey: .startedAt)
        transitions = try values.decodeIfPresent([EventTransition].self, forKey: .transitions) ?? []
    }
}

struct EventTransition: Codable, Equatable, Sendable {
    let status: String
    let source: String
    let resolution: String?
    let at: String?

    enum CodingKeys: String, CodingKey { case status, source, resolution, at }

    init(status: String, source: String, resolution: String? = nil, at: String? = nil) {
        self.status = status
        self.source = source
        self.resolution = resolution
        self.at = at
    }
}

struct EventVerification: Codable, Equatable, Sendable {
    let status: String
    let decision: String?
    let result: EventVerificationResult?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case status, decision, result
        case updatedAt = "updated_at"
    }

    init(status: String = "", decision: String? = nil, result: EventVerificationResult? = nil, updatedAt: String? = nil) {
        self.status = status
        self.decision = decision
        self.result = result
        self.updatedAt = updatedAt
    }
}

struct EventVerificationResult: Codable, Equatable, Sendable {
    let reason: String?

    init(reason: String? = nil) { self.reason = reason }
}

struct EventRule: Codable, Equatable, Sendable {
    let label: String?
    let reason: String?

    init(label: String? = nil, reason: String? = nil) {
        self.label = label
        self.reason = reason
    }
}

enum EventSegment: String, CaseIterable, Identifiable, Sendable {
    case pending
    case handled
    case falsePositive

    var id: String { rawValue }
    var title: String {
        switch self {
        case .pending: return "待处理"
        case .handled: return "已处理"
        case .falsePositive: return "误报"
        }
    }
}

struct EventGroup: Identifiable, Equatable, Sendable {
    let id: String
    let primary: AppEvent
    let related: [AppEvent]

    var cameraCount: Int {
        let directIDs = ([primary] + related).compactMap(\.cameraID)
        let incidentIDs = ([primary] + related).flatMap { $0.payload.incident?.sourceCameraIDs ?? [] }
        return max(Set(directIDs + incidentIDs).count, 1)
    }
}

enum EventPresentation {
    static func segment(_ event: AppEvent) -> EventSegment {
        event.resolution == "false_positive" ? .falsePositive : (event.acknowledged ? .handled : .pending)
    }

    static func groups(_ events: [AppEvent], segment: EventSegment) -> [EventGroup] {
        let visible = events.filter { self.segment($0) == segment }
        var grouped: [String: [AppEvent]] = [:]
        for event in visible {
            let key = event.payload.incident?.primaryEventID ?? event.id
            grouped[key, default: []].append(event)
        }
        return grouped.values.compactMap { values in
            guard let newest = values.sorted(by: sort).first else { return nil }
            let primaryID = newest.payload.incident?.primaryEventID
            let primary = values.first(where: { $0.id == primaryID }) ?? newest
            return EventGroup(id: primary.id, primary: primary, related: values.filter { $0.id != primary.id }.sorted(by: sort))
        }.sorted { sort($0.primary, $1.primary) }
    }

    static func label(for type: String) -> String {
        switch type {
        case "black_screen": return "画面异常"
        case "camera_offline": return "设备离线"
        case "no_motion": return "长时间无变化"
        case "no_person": return "长时间未见"
        case "fall_candidate": return "疑似跌倒"
        case "prolonged_floor_lying": return "长时间倒地"
        case "long_absence": return "长时间未见"
        default: return "安全提醒"
        }
    }

    static func title(for event: AppEvent) -> String {
        let place = event.room.isEmpty ? (event.cameraName.isEmpty ? "家庭画面" : event.cameraName) : event.room
        switch event.type {
        case "fall_candidate": return "\(place)出现疑似跌倒"
        case "prolonged_floor_lying": return "\(place)检测到长时间倒地"
        case "camera_offline": return "\(place)暂时离线"
        case "black_screen": return "\(place)画面异常"
        case "no_person", "long_absence": return "\(place)长时间未见人"
        case "no_motion": return "\(place)长时间没有变化"
        default: return label(for: event.type)
        }
    }

    static func verificationText(_ verification: EventVerification?, evidenceCount: Int) -> String {
        guard let verification, !verification.status.isEmpty else { return "等待云端复核" }
        switch verification.status {
        case "confirmed": return evidenceCount > 1 ? "云端复核支持异常判断 · \(evidenceCount) 张证据" : "云端复核支持异常判断"
        case "rejected": return "云端复核未发现明确异常"
        case "uncertain": return "云端证据不足，需要人工确认"
        case "pending", "verifying", "retrying": return "云端正在复核证据"
        case "failed", "unavailable": return "云端复核暂未完成"
        default: return "已收到云端复核结果"
        }
    }

    static func timeline(for event: AppEvent) -> [EventTimelineItem] {
        var items = [EventTimelineItem(
            id: "detected",
            title: "家庭盒子发现异常",
            detail: "\(event.cameraName.isEmpty ? event.room.isEmpty ? "家庭画面" : event.room : event.cameraName)记录了\(label(for: event.type))。",
            date: event.occurredAt,
            symbol: "sensor.tag.radiowaves.forward",
            tone: event.level == "critical" ? .warning : .neutral
        )]
        if event.cameraCountForIncident > 1 {
            items.append(EventTimelineItem(
                id: "multi-camera",
                title: "多路画面提供佐证",
                detail: "同一时间窗口的画面已合并为一条守护事件。",
                date: event.payload.incident?.startedAt ?? event.occurredAt,
                symbol: "video.badge.waveform",
                tone: .neutral
            ))
        }
        let transitions = event.payload.incident?.transitions ?? []
        for transition in transitions {
            let copy = transitionCopy(transition)
            items.append(EventTimelineItem(id: "transition-\(items.count)", title: copy.title, detail: copy.detail, date: transition.at ?? event.createdAt, symbol: copy.symbol, tone: copy.tone))
        }
        if let verification = event.payload.verification, !transitions.contains(where: { $0.source == "vision_verification" }) {
            let copy = verificationCopy(verification)
            items.append(EventTimelineItem(id: "verification", title: copy.title, detail: copy.detail, date: verification.updatedAt ?? event.createdAt, symbol: copy.symbol, tone: copy.tone))
        }
        if event.acknowledged && !transitions.contains(where: { $0.source == "app_user" || $0.status == "acknowledged" }) {
            items.append(EventTimelineItem(id: "acknowledged", title: event.resolution == "false_positive" ? "已标记为误报" : "已确认收到", detail: event.resolution == "false_positive" ? "记录和证据保留，用于后续校准。" : "这条提醒已停止重复推送。", date: event.updatedAt, symbol: event.resolution == "false_positive" ? "checkmark.seal" : "checkmark", tone: .neutral))
        }
        return items.sorted { ($0.date ?? "") < ($1.date ?? "") }
    }

    private static func sort(_ lhs: AppEvent, _ rhs: AppEvent) -> Bool {
        lhs.occurredAt > rhs.occurredAt
    }

    private static func transitionCopy(_ transition: EventTransition) -> (title: String, detail: String, symbol: String, tone: EventTimelineTone) {
        if transition.source == "app_user" || transition.status == "acknowledged" { return ("已确认收到", "这条提醒已停止重复推送。", "checkmark", .neutral) }
        if transition.source == "edge_admin" || transition.resolution == "false_positive" { return ("已核对为误报", "记录和证据保留，用于后续校准。", "checkmark.seal", .neutral) }
        if transition.source == "presence_recovery" || transition.status == "resolved" { return ("家中状态已经恢复", "摄像头重新检测到人，本次提醒自动结束。", "person.crop.circle.badge.checkmark", .neutral) }
        if transition.source == "vision_verification" {
            return verificationCopy(EventVerification(status: transition.status))
        }
        return ("守护提醒已建立", "系统将持续跟踪，直到收到处理结果。", "bell.badge", .warning)
    }

    private static func verificationCopy(_ verification: EventVerification) -> (title: String, detail: String, symbol: String, tone: EventTimelineTone) {
        switch verification.status {
        case "confirmed": return ("云端模型支持异常判断", safeVerificationReason(verification.result?.reason), "checkmark.seal", .warning)
        case "rejected": return ("云端模型未发现明确异常", "原始记录仍然保留，供你核对。", "checkmark", .neutral)
        case "uncertain": return ("云端证据不足", "模型无法明确判断，需要人工确认。", "questionmark.circle", .warning)
        default: return ("云端正在复核", "系统正在检查事件截图和边缘检测依据。", "icloud.and.arrow.down", .neutral)
        }
    }

    private static func safeVerificationReason(_ value: String?) -> String {
        guard let value, !value.isEmpty else { return "请结合截图或实时画面尽快确认。" }
        let blocked = ["fall_score", "threshold", "rtsp", "ffmpeg", "opencv", "traceback", "http ", "edge_agent"]
        return blocked.contains(where: { value.lowercased().contains($0) })
            ? "请结合截图或实时画面尽快确认。"
            : value
    }
}

enum EventTimelineTone: Sendable { case neutral, warning }

struct EventTimelineItem: Identifiable, Equatable, Sendable {
    let id: String
    let title: String
    let detail: String
    let date: String?
    let symbol: String
    let tone: EventTimelineTone
}

private extension AppEvent {
    var cameraCountForIncident: Int {
        let ids = Set(([cameraID] + (payload.incident?.sourceCameraIDs ?? [])).compactMap { $0 })
        return max(ids.count, 1)
    }
}

struct ElderProfile: Codable, Equatable, Sendable {
    let id: String
    let elderID: String
    var displayName: String
    var relationship: String
    var age: Int?
    var city: String
    var district: String
    var phone: String
    var mobilePhone: String
    var homePhone: String

    enum CodingKeys: String, CodingKey {
        case id
        case elderID = "elder_id"
        case displayName = "display_name"
        case relationship, age, city, district, phone
        case mobilePhone = "mobile_phone"
        case homePhone = "home_phone"
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decodeFlexibleID(forKey: .id)
        elderID = try values.decodeFlexibleID(forKey: .elderID)
        displayName = try values.decode(String.self, forKey: .displayName)
        relationship = try values.decode(String.self, forKey: .relationship)
        age = try values.decodeIfPresent(Int.self, forKey: .age)
        city = try values.decodeIfPresent(String.self, forKey: .city) ?? ""
        district = try values.decodeIfPresent(String.self, forKey: .district) ?? ""
        phone = try values.decodeIfPresent(String.self, forKey: .phone) ?? ""
        mobilePhone = try values.decodeIfPresent(String.self, forKey: .mobilePhone) ?? ""
        homePhone = try values.decodeIfPresent(String.self, forKey: .homePhone) ?? ""
    }
}

struct DeviceBinding: Codable, Equatable, Sendable {
    let id: String
    let familyID: String
    let deviceID: String
    let deviceName: String
    let status: String
    let lastSeenAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case familyID = "family_id"
        case deviceID = "device_id"
        case deviceName = "device_name"
        case status
        case lastSeenAt = "last_seen_at"
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decodeFlexibleID(forKey: .id)
        familyID = try values.decodeFlexibleID(forKey: .familyID)
        deviceID = try values.decodeFlexibleID(forKey: .deviceID)
        deviceName = try values.decode(String.self, forKey: .deviceName)
        status = try values.decode(String.self, forKey: .status)
        lastSeenAt = try values.decodeIfPresent(String.self, forKey: .lastSeenAt)
    }
}

struct ClaimableDevice: Codable, Equatable, Sendable, Identifiable {
    let deviceID: String
    let serialNumber: String
    let name: String
    let status: String
    let lastSeenAt: String?

    var id: String { deviceID }

    enum CodingKeys: String, CodingKey {
        case deviceID = "device_id"
        case serialNumber = "serial_number"
        case name, status
        case lastSeenAt = "last_seen_at"
    }


    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        deviceID = try values.decodeFlexibleID(forKey: .deviceID)
        serialNumber = try values.decode(String.self, forKey: .serialNumber)
        name = try values.decode(String.self, forKey: .name)
        status = try values.decode(String.self, forKey: .status)
        lastSeenAt = try values.decodeIfPresent(String.self, forKey: .lastSeenAt)
    }
}

struct DeviceClaimResponse: Codable, Equatable, Sendable {
    let ok: Bool
    let binding: DeviceBinding
    let device: ClaimableDevice
    let next: String?
}

struct DeviceBindingCode: Codable, Equatable, Sendable {
    let id: String
    let familyID: String
    let code: String
    let status: String
    let expiresAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case familyID = "family_id"
        case code, status
        case expiresAt = "expires_at"
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decodeFlexibleID(forKey: .id)
        familyID = try values.decodeFlexibleID(forKey: .familyID)
        code = try values.decode(String.self, forKey: .code)
        status = try values.decode(String.self, forKey: .status)
        expiresAt = try values.decode(String.self, forKey: .expiresAt)
    }
}

struct CameraConfig: Codable, Equatable, Sendable, Identifiable {
    let id: String
    let familyID: String?
    let deviceID: String?
    let name: String
    let room: String
    let status: String
    let syncStatus: String?
    let connectionOwner: String?
    let hasStreamConfig: Bool?

    enum CodingKeys: String, CodingKey {
        case id
        case familyID = "family_id"
        case deviceID = "device_id"
        case name, room, status
        case syncStatus = "sync_status"
        case connectionOwner = "connection_owner"
        case hasStreamConfig = "has_stream_config"
    }


    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decodeFlexibleID(forKey: .id)
        familyID = try values.decodeFlexibleIDIfPresent(forKey: .familyID)
        deviceID = try values.decodeFlexibleIDIfPresent(forKey: .deviceID)
        name = try values.decode(String.self, forKey: .name)
        room = try values.decode(String.self, forKey: .room)
        status = try values.decode(String.self, forKey: .status)
        syncStatus = try values.decodeIfPresent(String.self, forKey: .syncStatus)
        connectionOwner = try values.decodeIfPresent(String.self, forKey: .connectionOwner)
        hasStreamConfig = try values.decodeIfPresent(Bool.self, forKey: .hasStreamConfig)
    }
}

struct CameraConnectionResult: Codable, Equatable, Sendable {
    let ok: Bool
    let status: String
    let connectionOwner: String
    let hasStreamConfig: Bool
    let latencyMS: Int?
    let message: String?

    enum CodingKeys: String, CodingKey {
        case ok, status
        case connectionOwner = "connection_owner"
        case hasStreamConfig = "has_stream_config"
        case latencyMS = "latency_ms"
        case message
    }
}

private extension KeyedDecodingContainer {
    func decodeFlexibleID(forKey key: Key) throws -> String {
        if let value = try? decode(String.self, forKey: key) { return value }
        if let value = try? decode(Int.self, forKey: key) { return String(value) }
        if let value = try? decode(Int64.self, forKey: key) { return String(value) }
        throw DecodingError.typeMismatch(
            String.self,
            DecodingError.Context(codingPath: codingPath + [key], debugDescription: "Expected a string or numeric identifier")
        )
    }

    func decodeFlexibleIDIfPresent(forKey key: Key) throws -> String? {
        guard contains(key), try !decodeNil(forKey: key) else { return nil }
        return try decodeFlexibleID(forKey: key)
    }

    func decodeFlexibleIDsIfPresent(forKey key: Key) throws -> [String]? {
        guard contains(key), try !decodeNil(forKey: key) else { return nil }
        var values: [String] = []
        var container = try nestedUnkeyedContainer(forKey: key)
        while !container.isAtEnd {
            if let string = try? container.decode(String.self) {
                values.append(string)
            } else if let number = try? container.decode(Int.self) {
                values.append(String(number))
            } else {
                _ = try container.superDecoder()
            }
        }
        return values
    }
}
