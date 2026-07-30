import Foundation

enum AppRoute: Equatable {
    case launching
    case signedOut
    case onboarding(OnboardingStep)
    case main
}

enum OnboardingStep: String, Codable, Equatable {
    case family
    case profile
    case device
    case camera
    case complete
}
