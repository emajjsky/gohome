import Foundation

struct AuthChallengeResponse: Codable, Equatable, Sendable {
    let challengeID: String?
    let expiresAt: String?
    let delivery: String?
    let demoCode: String?

    enum CodingKeys: String, CodingKey {
        case challengeID = "challenge_id"
        case expiresAt = "expires_at"
        case delivery
        case demoCode = "demo_code"
    }
}

struct AuthSessionResponse: Codable, Equatable, Sendable {
    let token: String
    let user: AppUser?
}
