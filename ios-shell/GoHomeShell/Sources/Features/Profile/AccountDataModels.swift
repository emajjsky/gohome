import Foundation

struct AccountDeletionPlan: Decodable, Equatable, Sendable {
    let canDelete: Bool
    let requiresOwnershipTransfer: Bool
    let families: [AccountDeletionFamily]
    let blockers: [AccountDeletionBlocker]
    let deletionScope: AccountDeletionScope
    let retentionNote: String

    enum CodingKeys: String, CodingKey {
        case canDelete = "can_delete"
        case requiresOwnershipTransfer = "requires_ownership_transfer"
        case families, blockers
        case deletionScope = "deletion_scope"
        case retentionNote = "retention_note"
    }
}

struct AccountDeletionFamily: Decodable, Equatable, Sendable, Identifiable {
    let id: String
    let name: String
    let role: String
    let ownsFamily: Bool
    let activeMemberCount: Int
    let action: String

    enum CodingKeys: String, CodingKey {
        case id, name, role, action
        case ownsFamily = "owns_family"
        case activeMemberCount = "active_member_count"
    }
}

struct AccountDeletionBlocker: Decodable, Equatable, Sendable, Identifiable {
    let code: String
    let familyID: String
    let familyName: String
    let message: String

    var id: String { "\(code):\(familyID)" }

    enum CodingKeys: String, CodingKey {
        case code, message
        case familyID = "family_id"
        case familyName = "family_name"
    }
}

struct AccountDeletionScope: Decodable, Equatable, Sendable {
    let familiesToDelete: [String]
    let membershipsToLeave: [String]
    let authoredMemories: Int

    enum CodingKeys: String, CodingKey {
        case familiesToDelete = "families_to_delete"
        case membershipsToLeave = "memberships_to_leave"
        case authoredMemories = "authored_memories"
    }
}

struct AccountDeleteRequest: Encodable, Equatable, Sendable {
    let confirmation: String
}

struct AccountDeleteResponse: Decodable, Equatable, Sendable {
    let deleted: Bool
}
