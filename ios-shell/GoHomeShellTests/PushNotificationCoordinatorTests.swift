import XCTest
@testable import GoHomeShell

final class PushNotificationCoordinatorTests: XCTestCase {
    func testEventNotificationParsesNativeRoute() {
        let route = PushNotificationRoute(userInfo: [
            "gohome": [
                "route": "event",
                "event_id": 208,
                "camera_id": "2",
                "message_id": "event-alert-208",
            ],
        ])
        XCTAssertEqual(route, .event(eventID: "208", cameraID: "2"))
    }

    func testGenericNotificationRoutesHome() {
        let route = PushNotificationRoute(userInfo: [
            "gohome": ["route": "home", "message_id": "daily-summary-1"],
        ])
        XCTAssertEqual(route, .home(messageID: "daily-summary-1"))
    }

    func testMalformedEventNotificationIsIgnored() {
        XCTAssertNil(PushNotificationRoute(userInfo: ["gohome": ["route": "event"]]))
        XCTAssertNil(PushNotificationRoute(userInfo: ["unrelated": true]))
    }

    @MainActor
    func testInstallIdentifierIsStable() throws {
        let suite = "com.gohome.family.push-tests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let client = APIClient(baseURL: URL(string: "https://example.invalid")!)
        let first = PushNotificationCoordinator(
            client: client,
            enabled: false,
            environment: "sandbox",
            defaults: defaults,
            registerForRemoteNotifications: {}
        )
        let firstID = defaults.string(forKey: "gohome.app-install-id")
        _ = first
        _ = PushNotificationCoordinator(
            client: client,
            enabled: false,
            environment: "sandbox",
            defaults: defaults,
            registerForRemoteNotifications: {}
        )
        XCTAssertNotNil(firstID)
        XCTAssertEqual(defaults.string(forKey: "gohome.app-install-id"), firstID)
    }
}
