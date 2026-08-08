import XCTest
@testable import GoHomeShell

final class AppSmokeTests: XCTestCase {
    func testMainShellRequiresAnExactLiveFamilyOutsideUITests() {
        let family = AppFamily(id: "family-1", name: "杭州的家", role: "owner")
        let valid = bootstrap(activeFamilyID: family.id, families: [family])
        let missingID = bootstrap(activeFamilyID: nil, families: [family])
        let mismatched = bootstrap(
            activeFamilyID: "family-missing",
            families: [family]
        )

        XCTAssertEqual(
            MainShellResolution.resolve(bootstrap: valid, allowsUITestPreview: false),
            .live(bootstrap: valid, family: family)
        )
        XCTAssertEqual(
            MainShellResolution.resolve(bootstrap: missingID, allowsUITestPreview: false),
            .unavailable
        )
        XCTAssertEqual(
            MainShellResolution.resolve(bootstrap: mismatched, allowsUITestPreview: false),
            .unavailable
        )
        XCTAssertEqual(
            MainShellResolution.resolve(bootstrap: nil, allowsUITestPreview: true),
            .uiTestPreview
        )
    }

    func testBundledProductImagesResolveAsJPEGResources() {
        let imageNames = [
            "avatar",
            "grandma-reading",
            "memory-garden-sun",
            "memory-generations",
            "memory-relax-chat",
        ]

        for name in imageNames {
            XCTAssertNotNil(GoHomeImageResource.loadJPEG(named: name), "Missing bundled image: \(name).jpg")
        }
    }

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

private func bootstrap(activeFamilyID: String?, families: [AppFamily]) -> BootstrapResponse {
    BootstrapResponse(
        user: AppUser(id: "user-1", phone: "13800138000", displayName: "测试用户"),
        families: families,
        activeFamilyID: activeFamilyID,
        onboarding: OnboardingState(nextStep: .complete, complete: true),
        unreadCount: 0,
        revision: "test-r1"
    )
}
