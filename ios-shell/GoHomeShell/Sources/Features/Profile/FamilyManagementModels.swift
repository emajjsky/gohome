import Foundation

struct FamilyMember: Codable, Equatable, Identifiable, Sendable {
    let id: String
    let userID: String
    let displayName: String
    let accountHint: String
    let role: String
    let isCurrentUser: Bool
    let joinedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, role
        case userID = "user_id"
        case displayName = "display_name"
        case accountHint = "account_hint"
        case isCurrentUser = "is_current_user"
        case joinedAt = "joined_at"
    }

    var isCreator: Bool { ["owner", "creator"].contains(role.lowercased()) }
}

struct FamilyMembersResponse: Decodable, Equatable, Sendable {
    let familyID: String
    let members: [FamilyMember]
    let revision: String

    enum CodingKeys: String, CodingKey {
        case members, revision
        case familyID = "family_id"
    }
}

struct FamilyMemberRemovalResponse: Decodable, Equatable, Sendable {
    let removed: Bool
}

struct FamilyLeaveResponse: Decodable, Equatable, Sendable {
    let left: Bool
}

struct FamilyOwnershipTransferResponse: Decodable, Equatable, Sendable {
    let transferred: Bool
}

struct FamilyOwnershipTransferRequest: Encodable, Equatable, Sendable {
    let targetMemberID: String
    let confirmation: String

    enum CodingKeys: String, CodingKey {
        case confirmation
        case targetMemberID = "target_member_id"
    }
}

struct FamilyInvitation: Codable, Equatable, Identifiable, Sendable {
    let id: String
    let familyID: String
    let status: String
    let codeHint: String
    let code: String?
    let expiresAt: String?
    let createdAt: String?
    let usedAt: String?
    let revokedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, status, code
        case familyID = "family_id"
        case codeHint = "code_hint"
        case expiresAt = "expires_at"
        case createdAt = "created_at"
        case usedAt = "used_at"
        case revokedAt = "revoked_at"
    }

    var isActive: Bool { status == "active" }
}

struct FamilyInvitationsResponse: Decodable, Equatable, Sendable {
    let familyID: String
    let invitations: [FamilyInvitation]
    let revision: String

    enum CodingKeys: String, CodingKey {
        case invitations, revision
        case familyID = "family_id"
    }
}

struct FamilyInvitationCreateRequest: Encodable, Equatable, Sendable {
    let expiresInMinutes: Int

    enum CodingKeys: String, CodingKey {
        case expiresInMinutes = "expires_in_minutes"
    }
}

struct FamilyInvitationConsumeRequest: Encodable, Equatable, Sendable {
    let code: String
}

struct FamilyInvitationConsumeResponse: Decodable, Equatable, Sendable {
    let joined: Bool
    let family: AppFamily
}
