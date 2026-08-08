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
        XCTAssertEqual(AppRoute.sessionUnavailable, .sessionUnavailable)
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

    @MainActor
    func testUnauthorizedBootstrapSignsOutButTransientFailureCanRetry() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let successfulBootstrap = bootstrap(
            activeFamilyID: "family-1",
            families: [AppFamily(id: "family-1", name: "杭州的家", role: "owner")]
        )
        let loader = BootstrapSequenceLoader(results: [
            .failure(URLError(.timedOut)),
            .success(successfulBootstrap),
            .failure(APIError.unauthorized),
        ])
        let repository = AppRepository(
            cache: try DiskCache(rootURL: root),
            bootstrapLoader: { try await loader.load() }
        )
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "com.gohome.family.tests.\(UUID().uuidString)"))
        let contextStore = SessionContextStore(defaults: defaults)
        let model = AppModel(
            repository: repository,
            sessionContextStore: contextStore
        )

        model.authenticated()
        await waitUntil { model.route == .sessionUnavailable }
        XCTAssertNotNil(model.bootstrap.staleReason)

        model.retryAuthenticatedState()
        await waitUntil { model.route == .main }
        XCTAssertEqual(model.bootstrap.value, successfulBootstrap)

        model.authenticated()
        await waitUntil { model.route == .signedOut }
        let clearedScope = await contextStore.scope()
        XCTAssertNil(clearedScope)
    }

    @MainActor
    func testCancelledBootstrapCannotRestoreMainRouteAfterSignOut() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let value = bootstrap(
            activeFamilyID: "family-1",
            families: [AppFamily(id: "family-1", name: "杭州的家", role: "owner")]
        )
        let repository = AppRepository(
            cache: try DiskCache(rootURL: root),
            bootstrapLoader: {
                try? await Task.sleep(nanoseconds: 80_000_000)
                return value
            }
        )
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "com.gohome.family.tests.\(UUID().uuidString)"))
        let model = AppModel(
            repository: repository,
            sessionContextStore: SessionContextStore(defaults: defaults)
        )

        model.authenticated()
        model.signOut()
        try await Task.sleep(nanoseconds: 150_000_000)

        XCTAssertEqual(model.route, .signedOut)
        XCTAssertNil(model.bootstrap.value)
    }
}

private actor BootstrapSequenceLoader {
    private var results: [Result<BootstrapResponse, Error>]

    init(results: [Result<BootstrapResponse, Error>]) {
        self.results = results
    }

    func load() throws -> BootstrapResponse {
        guard !results.isEmpty else { throw APIError.invalidResponse }
        return try results.removeFirst().get()
    }
}

@MainActor
private func waitUntil(
    timeout: TimeInterval = 1,
    condition: @escaping @MainActor () -> Bool
) async {
    let deadline = Date().addingTimeInterval(timeout)
    while !condition(), Date() < deadline {
        try? await Task.sleep(nanoseconds: 10_000_000)
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
