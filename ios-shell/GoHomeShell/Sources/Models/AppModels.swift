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

    init(id: String, name: String, role: String?) {
        self.id = id
        self.name = name
        self.role = role
    }

    enum CodingKeys: String, CodingKey { case id, name, role }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decodeFlexibleID(forKey: .id)
        name = try values.decode(String.self, forKey: .name)
        role = try values.decodeIfPresent(String.self, forKey: .role)
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
    let articles: [HomeArticle]
    let cameras: [HomeCamera]
    let revision: String

    enum CodingKeys: String, CodingKey {
        case family, weather, calendar, distance, articles, cameras, revision
        case criticalAlert = "critical_alert"
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
}
