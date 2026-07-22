import XCTest
@testable import GoHomeShell

final class SessionContextStoreTests: XCTestCase {
    func testScopeRoundTripAndClear() async throws {
        let suite = "SessionContextStoreTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let store = SessionContextStore(defaults: defaults)
        let scope = CacheScope(userID: "user-7", familyID: "family-12")

        await store.save(scope: scope)
        let restored = await store.scope()
        XCTAssertEqual(restored, scope)

        await store.clear()
        let cleared = await store.scope()
        XCTAssertNil(cleared)
    }
}
