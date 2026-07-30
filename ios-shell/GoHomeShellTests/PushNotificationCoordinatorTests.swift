import XCTest
@testable import GoHomeShell

final class PushNotificationCoordinatorTests: XCTestCase {
    func testForegroundNotificationsRemainInNotificationCenter() {
        let options = GoHomeAppDelegate.foregroundPresentationOptions
        XCTAssertTrue(options.contains(.banner))
        XCTAssertTrue(options.contains(.list))
        XCTAssertTrue(options.contains(.badge))
        XCTAssertTrue(options.contains(.sound))
    }

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

    func testNotificationStatusSeparatesPermissionFromVisibleChannels() {
        XCTAssertEqual(
            PushNotificationStatus(
                authorization: .allowed,
                alertEnabled: false,
                notificationCenterEnabled: true,
                lockScreenEnabled: true,
                soundEnabled: false
            ).permissionSummary,
            "展示受限"
        )
        XCTAssertEqual(
            PushNotificationStatus(
                authorization: .allowed,
                alertEnabled: true,
                notificationCenterEnabled: true,
                lockScreenEnabled: true,
                soundEnabled: true
            ).channelSummary,
            "横幅 · 通知中心 · 锁屏 · 声音"
        )
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

    @MainActor
    func testDuplicateMessageIsPresentedAndRoutedOnlyOnce() throws {
        let suite = "com.gohome.family.push-dedup-tests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let coordinator = PushNotificationCoordinator(
            client: APIClient(baseURL: URL(string: "https://example.invalid")!),
            enabled: false,
            environment: "sandbox",
            defaults: defaults,
            registerForRemoteNotifications: {},
            now: { Date(timeIntervalSince1970: 1_000) }
        )
        let payload: [AnyHashable: Any] = [
            "gohome": ["route": "home", "message_id": "daily-summary-1"],
        ]

        XCTAssertTrue(coordinator.shouldPresentNotification(userInfo: payload))
        XCTAssertFalse(coordinator.shouldPresentNotification(userInfo: payload))
        coordinator.handleNotification(userInfo: payload)
        XCTAssertEqual(coordinator.pendingRoute, .home(messageID: "daily-summary-1"))
        coordinator.consume(.home(messageID: "daily-summary-1"))
        coordinator.handleNotification(userInfo: payload)
        XCTAssertNil(coordinator.pendingRoute)
    }

    @MainActor
    func testNotificationsWithoutStableIdentifiersAreNotIncorrectlyDeduplicated() throws {
        let suite = "com.gohome.family.push-no-id-tests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let coordinator = PushNotificationCoordinator(
            client: APIClient(baseURL: URL(string: "https://example.invalid")!),
            enabled: false,
            environment: "sandbox",
            defaults: defaults,
            registerForRemoteNotifications: {}
        )
        let payload: [AnyHashable: Any] = ["gohome": ["route": "home"]]

        XCTAssertTrue(coordinator.shouldPresentNotification(userInfo: payload))
        XCTAssertTrue(coordinator.shouldPresentNotification(userInfo: payload))
        coordinator.handleNotification(userInfo: payload)
        XCTAssertEqual(coordinator.pendingRoute, .home(messageID: nil))
        coordinator.consume(.home(messageID: nil))
        coordinator.handleNotification(userInfo: payload)
        XCTAssertEqual(coordinator.pendingRoute, .home(messageID: nil))
    }
}
