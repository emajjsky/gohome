import XCTest
@testable import GoHomeShell

final class AppSmokeTests: XCTestCase {
    func testNativeRouteSupportsSignedOutAndOnboardingStates() {
        XCTAssertEqual(AppRoute.signedOut, .signedOut)
        XCTAssertEqual(AppRoute.onboarding(.camera), .onboarding(.camera))
    }

    @MainActor
    func testAuthenticatedImmediatelyLeavesSignedOutRoute() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let repository = AppRepository(
            cache: try DiskCache(rootURL: root),
            bootstrapLoader: {
                try await Task.sleep(nanoseconds: 5_000_000_000)
                throw APIError.invalidResponse
            }
        )
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "com.gohome.family.tests.\(UUID().uuidString)"))
        let model = AppModel(
            repository: repository,
            sessionContextStore: SessionContextStore(defaults: defaults)
        )
        model.signOut()
        XCTAssertEqual(model.route, .signedOut)

        model.authenticated()

        XCTAssertEqual(model.route, .launching)
    }
}
