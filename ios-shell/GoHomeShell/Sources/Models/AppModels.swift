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
}

struct AppFamily: Codable, Equatable, Sendable {
    let id: String
    let name: String
    let role: String?
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
}

struct HomeResponse: Codable, Equatable, Sendable {
    let revision: String
}
