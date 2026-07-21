import XCTest
@testable import GoHomeShell

final class AppSmokeTests: XCTestCase {
    func testNativeRouteSupportsSignedOutAndOnboardingStates() {
        XCTAssertEqual(AppRoute.signedOut, .signedOut)
        XCTAssertEqual(AppRoute.onboarding(.camera), .onboarding(.camera))
    }
}
