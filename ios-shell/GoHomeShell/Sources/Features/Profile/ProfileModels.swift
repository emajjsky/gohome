import Foundation

struct FamilyRules: Codable, Equatable, Sendable {
    let canEdit: Bool
    var offlineEnabled: Bool
    var blackScreenEnabled: Bool
    var noMotionEnabled: Bool
    var personDetectionEnabled: Bool
    var fallDetectionEnabled: Bool
    var activityDetectionEnabled: Bool
    var fireDetectionEnabled: Bool
    var notificationEnabled: Bool
    var captureIntervalSeconds: Int
    var noMotionSeconds: Int
    var noPersonSeconds: Int
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case canEdit = "can_edit"
        case offlineEnabled = "offline_enabled"
        case blackScreenEnabled = "black_screen_enabled"
        case noMotionEnabled = "no_motion_enabled"
        case personDetectionEnabled = "person_detection_enabled"
        case fallDetectionEnabled = "fall_detection_enabled"
        case activityDetectionEnabled = "activity_detection_enabled"
        case fireDetectionEnabled = "fire_detection_enabled"
        case notificationEnabled = "notification_enabled"
        case captureIntervalSeconds = "capture_interval_seconds"
        case noMotionSeconds = "no_motion_seconds"
        case noPersonSeconds = "no_person_seconds"
        case updatedAt = "updated_at"
    }

    init(
        canEdit: Bool,
        offlineEnabled: Bool,
        blackScreenEnabled: Bool,
        noMotionEnabled: Bool,
        personDetectionEnabled: Bool,
        fallDetectionEnabled: Bool,
        activityDetectionEnabled: Bool,
        fireDetectionEnabled: Bool,
        notificationEnabled: Bool,
        captureIntervalSeconds: Int = 5,
        noMotionSeconds: Int = 900,
        noPersonSeconds: Int = 900,
        updatedAt: String? = nil
    ) {
        self.canEdit = canEdit
        self.offlineEnabled = offlineEnabled
        self.blackScreenEnabled = blackScreenEnabled
        self.noMotionEnabled = noMotionEnabled
        self.personDetectionEnabled = personDetectionEnabled
        self.fallDetectionEnabled = fallDetectionEnabled
        self.activityDetectionEnabled = activityDetectionEnabled
        self.fireDetectionEnabled = fireDetectionEnabled
        self.notificationEnabled = notificationEnabled
        self.captureIntervalSeconds = captureIntervalSeconds
        self.noMotionSeconds = noMotionSeconds
        self.noPersonSeconds = noPersonSeconds
        self.updatedAt = updatedAt
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        canEdit = try values.decodeIfPresent(Bool.self, forKey: .canEdit) ?? false
        offlineEnabled = try values.decodeIfPresent(Bool.self, forKey: .offlineEnabled) ?? true
        blackScreenEnabled = try values.decodeIfPresent(Bool.self, forKey: .blackScreenEnabled) ?? true
        noMotionEnabled = try values.decodeIfPresent(Bool.self, forKey: .noMotionEnabled) ?? true
        personDetectionEnabled = try values.decodeIfPresent(Bool.self, forKey: .personDetectionEnabled) ?? true
        fallDetectionEnabled = try values.decodeIfPresent(Bool.self, forKey: .fallDetectionEnabled) ?? true
        activityDetectionEnabled = try values.decodeIfPresent(Bool.self, forKey: .activityDetectionEnabled) ?? true
        fireDetectionEnabled = try values.decodeIfPresent(Bool.self, forKey: .fireDetectionEnabled) ?? true
        notificationEnabled = try values.decodeIfPresent(Bool.self, forKey: .notificationEnabled) ?? true
        captureIntervalSeconds = try values.decodeIfPresent(Int.self, forKey: .captureIntervalSeconds) ?? 5
        noMotionSeconds = try values.decodeIfPresent(Int.self, forKey: .noMotionSeconds) ?? 900
        noPersonSeconds = try values.decodeIfPresent(Int.self, forKey: .noPersonSeconds) ?? 900
        updatedAt = try values.decodeIfPresent(String.self, forKey: .updatedAt)
    }

    var editablePayload: RulePatch {
        RulePatch(
            offlineEnabled: offlineEnabled,
            blackScreenEnabled: blackScreenEnabled,
            noMotionEnabled: noMotionEnabled,
            personDetectionEnabled: personDetectionEnabled,
            fallDetectionEnabled: fallDetectionEnabled,
            activityDetectionEnabled: activityDetectionEnabled,
            fireDetectionEnabled: fireDetectionEnabled,
            notificationEnabled: notificationEnabled,
            captureIntervalSeconds: captureIntervalSeconds,
            noMotionSeconds: noMotionSeconds,
            noPersonSeconds: noPersonSeconds
        )
    }
}

struct RulePatch: Encodable, Equatable, Sendable {
    let offlineEnabled: Bool
    let blackScreenEnabled: Bool
    let noMotionEnabled: Bool
    let personDetectionEnabled: Bool
    let fallDetectionEnabled: Bool
    let activityDetectionEnabled: Bool
    let fireDetectionEnabled: Bool
    let notificationEnabled: Bool
    let captureIntervalSeconds: Int
    let noMotionSeconds: Int
    let noPersonSeconds: Int

    enum CodingKeys: String, CodingKey {
        case offlineEnabled = "offline_enabled"
        case blackScreenEnabled = "black_screen_enabled"
        case noMotionEnabled = "no_motion_enabled"
        case personDetectionEnabled = "person_detection_enabled"
        case fallDetectionEnabled = "fall_detection_enabled"
        case activityDetectionEnabled = "activity_detection_enabled"
        case fireDetectionEnabled = "fire_detection_enabled"
        case notificationEnabled = "notification_enabled"
        case captureIntervalSeconds = "capture_interval_seconds"
        case noMotionSeconds = "no_motion_seconds"
        case noPersonSeconds = "no_person_seconds"
    }
}

struct QuietHours: Codable, Equatable, Sendable {
    var start: String
    var end: String
}

struct ActivityHistorySettings: Codable, Equatable, Sendable {
    var trackingEnabled: Bool
    var dailySummaryEnabled: Bool
    var weeklyReportEnabled: Bool
    var anomalyRemindersEnabled: Bool
    var multimodalReviewEnabled: Bool
    var retentionDays: Int

    enum CodingKeys: String, CodingKey {
        case trackingEnabled = "tracking_enabled"
        case dailySummaryEnabled = "daily_summary_enabled"
        case weeklyReportEnabled = "weekly_report_enabled"
        case anomalyRemindersEnabled = "anomaly_reminders_enabled"
        case multimodalReviewEnabled = "multimodal_review_enabled"
        case retentionDays = "retention_days"
    }

    init(
        trackingEnabled: Bool = true,
        dailySummaryEnabled: Bool = true,
        weeklyReportEnabled: Bool = true,
        anomalyRemindersEnabled: Bool = true,
        multimodalReviewEnabled: Bool = true,
        retentionDays: Int = 30
    ) {
        self.trackingEnabled = trackingEnabled
        self.dailySummaryEnabled = dailySummaryEnabled
        self.weeklyReportEnabled = weeklyReportEnabled
        self.anomalyRemindersEnabled = anomalyRemindersEnabled
        self.multimodalReviewEnabled = multimodalReviewEnabled
        self.retentionDays = min(365, max(7, retentionDays))
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            trackingEnabled: try values.decodeIfPresent(Bool.self, forKey: .trackingEnabled) ?? true,
            dailySummaryEnabled: try values.decodeIfPresent(Bool.self, forKey: .dailySummaryEnabled) ?? true,
            weeklyReportEnabled: try values.decodeIfPresent(Bool.self, forKey: .weeklyReportEnabled) ?? true,
            anomalyRemindersEnabled: try values.decodeIfPresent(Bool.self, forKey: .anomalyRemindersEnabled) ?? true,
            multimodalReviewEnabled: try values.decodeIfPresent(Bool.self, forKey: .multimodalReviewEnabled) ?? true,
            retentionDays: try values.decodeIfPresent(Int.self, forKey: .retentionDays) ?? 30
        )
    }

    static let standard = ActivityHistorySettings(
        trackingEnabled: true,
        dailySummaryEnabled: true,
        weeklyReportEnabled: true,
        anomalyRemindersEnabled: true,
        multimodalReviewEnabled: true,
        retentionDays: 30
    )
}

struct CarePreferencesMetadata: Codable, Equatable, Sendable {
    var activityHistory: ActivityHistorySettings

    enum CodingKeys: String, CodingKey {
        case activityHistory = "activity_history"
    }

    init(activityHistory: ActivityHistorySettings = .standard) {
        self.activityHistory = activityHistory
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        activityHistory = try values.decodeIfPresent(ActivityHistorySettings.self, forKey: .activityHistory) ?? .standard
    }
}

struct CarePreferences: Codable, Equatable, Sendable {
    let familyID: String
    let elderID: String?
    var frequency: String
    var quietHours: QuietHours
    var interests: [String]
    var textModelEnabled: Bool
    var imageGenerationEnabled: Bool
    var contentRecommendationsEnabled: Bool
    var contentSourcesEnabled: Bool
    var metadata: CarePreferencesMetadata

    enum CodingKeys: String, CodingKey {
        case familyID = "family_id"
        case elderID = "elder_id"
        case frequency
        case quietHours = "quiet_hours"
        case interests
        case textModelEnabled = "text_model_enabled"
        case imageGenerationEnabled = "image_generation_enabled"
        case contentRecommendationsEnabled = "content_recommendations_enabled"
        case contentSourcesEnabled = "content_sources_enabled"
        case metadata
    }

    init(
        familyID: String,
        elderID: String? = nil,
        frequency: String = "daily",
        quietHours: QuietHours = QuietHours(start: "21:30", end: "08:00"),
        interests: [String] = [],
        textModelEnabled: Bool = false,
        imageGenerationEnabled: Bool = false,
        contentRecommendationsEnabled: Bool = true,
        contentSourcesEnabled: Bool = true,
        metadata: CarePreferencesMetadata = CarePreferencesMetadata()
    ) {
        self.familyID = familyID
        self.elderID = elderID
        self.frequency = frequency
        self.quietHours = quietHours
        self.interests = interests
        self.textModelEnabled = textModelEnabled
        self.imageGenerationEnabled = imageGenerationEnabled
        self.contentRecommendationsEnabled = contentRecommendationsEnabled
        self.contentSourcesEnabled = contentSourcesEnabled
        self.metadata = metadata
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        familyID = try values.decodeFlexibleID(forKey: .familyID)
        elderID = try values.decodeFlexibleIDIfPresent(forKey: .elderID)
        frequency = try values.decodeIfPresent(String.self, forKey: .frequency) ?? "daily"
        quietHours = try values.decodeIfPresent(QuietHours.self, forKey: .quietHours) ?? QuietHours(start: "21:30", end: "08:00")
        interests = try values.decodeIfPresent([String].self, forKey: .interests) ?? []
        textModelEnabled = try values.decodeIfPresent(Bool.self, forKey: .textModelEnabled) ?? false
        imageGenerationEnabled = try values.decodeIfPresent(Bool.self, forKey: .imageGenerationEnabled) ?? false
        contentRecommendationsEnabled = try values.decodeIfPresent(Bool.self, forKey: .contentRecommendationsEnabled) ?? true
        contentSourcesEnabled = try values.decodeIfPresent(Bool.self, forKey: .contentSourcesEnabled) ?? true
        metadata = try values.decodeIfPresent(CarePreferencesMetadata.self, forKey: .metadata) ?? CarePreferencesMetadata()
    }

    var editablePayload: CarePreferencesPatch {
        CarePreferencesPatch(
            frequency: frequency,
            quietHours: quietHours,
            interests: interests,
            textModelEnabled: textModelEnabled,
            imageGenerationEnabled: imageGenerationEnabled,
            contentRecommendationsEnabled: contentRecommendationsEnabled,
            contentSourcesEnabled: contentSourcesEnabled,
            metadata: metadata
        )
    }
}

struct CarePreferencesPatch: Encodable, Equatable, Sendable {
    let frequency: String
    let quietHours: QuietHours
    let interests: [String]
    let textModelEnabled: Bool
    let imageGenerationEnabled: Bool
    let contentRecommendationsEnabled: Bool
    let contentSourcesEnabled: Bool
    let metadata: CarePreferencesMetadata

    enum CodingKeys: String, CodingKey {
        case frequency
        case quietHours = "quiet_hours"
        case interests
        case textModelEnabled = "text_model_enabled"
        case imageGenerationEnabled = "image_generation_enabled"
        case contentRecommendationsEnabled = "content_recommendations_enabled"
        case contentSourcesEnabled = "content_sources_enabled"
        case metadata
    }
}

struct ProductPreferences: Codable, Equatable, Sendable {
    var categories: [String]
    var needs: [String]
}

struct ProductPreferencesEnvelope: Codable, Equatable, Sendable {
    let preferences: ProductPreferences
}

struct CameraCreateRequest: Encodable, Equatable, Sendable {
    let familyID: String
    let deviceID: String
    let name: String
    let room: String
    let streamURL: String
    let username: String
    let password: String
    let enabled: Bool

    enum CodingKeys: String, CodingKey {
        case familyID = "family_id"
        case deviceID = "device_id"
        case name, room, username, password, enabled
        case streamURL = "stream_url"
    }
}

struct CameraUpdateRequest: Encodable, Equatable, Sendable {
    let name: String
    let room: String
    let streamURL: String
    let username: String?
    let password: String?
    let enabled: Bool

    enum CodingKeys: String, CodingKey {
        case name, room, username, password, enabled
        case streamURL = "stream_url"
    }
}

enum CameraStreamAddress {
    static func makeURL(scheme: String, host: String, port: String, path: String) -> String? {
        let cleanScheme = scheme.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let cleanHost = host.trimmingCharacters(in: .whitespacesAndNewlines)
        guard ["rtsp", "rtsps"].contains(cleanScheme), !cleanHost.isEmpty,
              let portNumber = Int(port), (1...65_535).contains(portNumber)
        else { return nil }

        let cleanPath = path.trimmingCharacters(in: .whitespacesAndNewlines)
        let normalizedPath = cleanPath.hasPrefix("/") ? cleanPath : "/\(cleanPath)"
        guard let relative = URLComponents(string: "rtsp://camera\(normalizedPath)") else { return nil }
        var components = URLComponents()
        components.scheme = cleanScheme
        components.host = cleanHost
        components.port = portNumber
        components.percentEncodedPath = relative.percentEncodedPath
        components.percentEncodedQuery = relative.percentEncodedQuery
        return components.string
    }
}

struct ProfileData: Codable, Equatable, Sendable {
    var elder: ElderProfile?
    var bindings: [DeviceBinding]
    var cameras: [CameraConfig]
    var rules: FamilyRules
    var carePreferences: CarePreferences
    var productPreferences: ProductPreferences
}

enum FamilyRole: String, Equatable, Sendable {
    case creator = "创建者"
    case member = "成员"

    static func resolve(familyRole: String?, canEdit: Bool) -> FamilyRole {
        let normalized = String(familyRole ?? "").lowercased()
        if canEdit || normalized == "owner" || normalized == "creator" || normalized == "创建者" {
            return .creator
        }
        return .member
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
}
