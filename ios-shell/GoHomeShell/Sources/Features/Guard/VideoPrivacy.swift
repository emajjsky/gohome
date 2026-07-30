import Foundation

enum VideoPrivacyMode: String, CaseIterable, Codable, Identifiable, Sendable {
    case original
    case personBlur = "person_blur"
    case skeleton

    var id: String { rawValue }

    var title: String {
        switch self {
        case .original: return "原画"
        case .personBlur: return "模糊"
        case .skeleton: return "骨架"
        }
    }

    var symbol: String {
        switch self {
        case .original: return "eye"
        case .personBlur: return "person.crop.rectangle"
        case .skeleton: return "figure.stand"
        }
    }

    var rank: Int {
        switch self {
        case .original: return 0
        case .personBlur: return 1
        case .skeleton: return 2
        }
    }

    func constrained(to minimum: VideoPrivacyMode) -> VideoPrivacyMode {
        rank >= minimum.rank ? self : minimum
    }
}

struct VideoPrivacyPolicy: Codable, Equatable, Sendable {
    let familyID: String
    let minimumMode: VideoPrivacyMode
    let updatedAt: String?
    let canManage: Bool

    enum CodingKeys: String, CodingKey {
        case familyID = "family_id"
        case minimumMode = "minimum_mode"
        case updatedAt = "updated_at"
        case canManage = "can_manage"
    }

    init(
        familyID: String,
        minimumMode: VideoPrivacyMode = .original,
        updatedAt: String? = nil,
        canManage: Bool = false
    ) {
        self.familyID = familyID
        self.minimumMode = minimumMode
        self.updatedAt = updatedAt
        self.canManage = canManage
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        if let text = try? values.decode(String.self, forKey: .familyID) {
            familyID = text
        } else if let number = try? values.decode(Int.self, forKey: .familyID) {
            familyID = String(number)
        } else {
            throw DecodingError.dataCorruptedError(
                forKey: .familyID,
                in: values,
                debugDescription: "family_id must be a string or integer"
            )
        }
        minimumMode = try values.decodeIfPresent(VideoPrivacyMode.self, forKey: .minimumMode) ?? .original
        updatedAt = try values.decodeIfPresent(String.self, forKey: .updatedAt)
        canManage = try values.decodeIfPresent(Bool.self, forKey: .canManage) ?? false
    }
}

private struct VideoPrivacyPolicyPatch: Encodable {
    let minimumMode: VideoPrivacyMode

    enum CodingKeys: String, CodingKey {
        case minimumMode = "minimum_mode"
    }
}

protocol VideoPrivacyServicing: Sendable {
    func fetch(familyID: String) async throws -> VideoPrivacyPolicy
    func update(familyID: String, minimumMode: VideoPrivacyMode) async throws -> VideoPrivacyPolicy
}

struct VideoPrivacyService: VideoPrivacyServicing, Sendable {
    let apiClient: APIClient

    func fetch(familyID: String) async throws -> VideoPrivacyPolicy {
        try await apiClient.send(Endpoint(
            path: "/api/v1/families/\(familyID)/video-privacy"
        ))
    }

    func update(familyID: String, minimumMode: VideoPrivacyMode) async throws -> VideoPrivacyPolicy {
        let body = try JSONEncoder().encode(VideoPrivacyPolicyPatch(minimumMode: minimumMode))
        return try await apiClient.send(Endpoint(
            method: .put,
            path: "/api/v1/families/\(familyID)/video-privacy",
            body: body
        ))
    }
}
