import Foundation
import UIKit
import UserNotifications

enum PushNotificationRoute: Equatable {
    case home(messageID: String?)
    case event(eventID: String, cameraID: String?)

    init?(userInfo: [AnyHashable: Any]) {
        guard let payload = userInfo["gohome"] as? [String: Any] else { return nil }
        let route = Self.text(payload["route"])
        let eventID = Self.text(payload["event_id"])
        let messageID = Self.text(payload["message_id"])
        let cameraID = Self.text(payload["camera_id"])
        if route == "event" || eventID != nil {
            guard let eventID else { return nil }
            self = .event(eventID: eventID, cameraID: cameraID)
        } else {
            self = .home(messageID: messageID)
        }
    }

    private static func text(_ value: Any?) -> String? {
        let text: String
        switch value {
        case let value as String: text = value
        case let value as NSNumber: text = value.stringValue
        default: return nil
        }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}

@MainActor
final class PushNotificationCoordinator: ObservableObject {
    @Published private(set) var pendingRoute: PushNotificationRoute?

    private let client: APIClient
    private let enabled: Bool
    private let environment: String
    private let installID: String
    private let deviceName: String
    private let appVersion: String
    private let notificationCenter: UNUserNotificationCenter
    private let registerForRemoteNotifications: () -> Void
    private var familyID: String?
    private var deviceToken = ""
    private var registrationTask: Task<Void, Never>?
    private var registrationSignature = ""

    init(
        client: APIClient,
        enabled: Bool,
        environment: String,
        defaults: UserDefaults = .standard,
        notificationCenter: UNUserNotificationCenter = .current(),
        registerForRemoteNotifications: (() -> Void)? = nil,
        deviceName: String? = nil,
        appVersion: String = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? ""
    ) {
        self.client = client
        self.enabled = enabled
        self.environment = environment
        self.notificationCenter = notificationCenter
        self.registerForRemoteNotifications = registerForRemoteNotifications ?? {
            UIApplication.shared.registerForRemoteNotifications()
        }
        self.deviceName = deviceName ?? UIDevice.current.model
        self.appVersion = appVersion
        let key = "gohome.app-install-id"
        if let existing = defaults.string(forKey: key), !existing.isEmpty {
            installID = existing
        } else {
            let created = UUID().uuidString.lowercased()
            defaults.set(created, forKey: key)
            installID = created
        }
    }

    static func live(client: APIClient, bundle: Bundle = .main) -> PushNotificationCoordinator {
        let enabled = bundle.object(forInfoDictionaryKey: "GoHomePushEnabled") as? Bool ?? false
#if DEBUG
        let environment = "sandbox"
#else
        let environment = "production"
#endif
        return PushNotificationCoordinator(client: client, enabled: enabled, environment: environment)
    }

    func activate(familyID: String) async {
        self.familyID = familyID
        guard enabled else { return }
        let settings = await notificationCenter.notificationSettings()
        var authorized = settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional
        if settings.authorizationStatus == .notDetermined {
            authorized = (try? await notificationCenter.requestAuthorization(options: [.alert, .badge, .sound])) == true
        }
        guard authorized else { return }
        registerForRemoteNotifications()
        registerTokenIfReady()
    }

    func receiveDeviceToken(_ data: Data) {
        deviceToken = data.map { String(format: "%02x", $0) }.joined()
        registerTokenIfReady()
    }

    func receiveRegistrationError(_ error: Error) {
        _ = error
        deviceToken = ""
        registrationSignature = ""
    }

    func handleNotification(userInfo: [AnyHashable: Any]) {
        guard let route = PushNotificationRoute(userInfo: userInfo) else { return }
        pendingRoute = route
    }

    func consume(_ route: PushNotificationRoute) {
        guard pendingRoute == route else { return }
        pendingRoute = nil
    }

    func deactivate() async {
        registrationTask?.cancel()
        registrationTask = nil
        registrationSignature = ""
        familyID = nil
        let escapedInstallID = installID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? installID
        let endpoint = Endpoint<PushTokenRevocationResponse>(
            method: .delete,
            path: "/api/v1/app/push-tokens/\(escapedInstallID)"
        )
        _ = try? await client.send(endpoint)
    }

    private func registerTokenIfReady() {
        guard enabled, let familyID, !deviceToken.isEmpty else { return }
        let signature = [familyID, deviceToken, environment, appVersion].joined(separator: ":")
        guard signature != registrationSignature else { return }
        registrationTask?.cancel()
        registrationTask = Task { [client, installID, environment, deviceName, appVersion, deviceToken] in
            do {
                let request = PushTokenRegistrationRequest(
                    familyID: familyID,
                    appInstallID: installID,
                    platform: "ios",
                    provider: "apns",
                    pushToken: deviceToken,
                    environment: environment,
                    deviceName: deviceName,
                    appVersion: appVersion
                )
                let endpoint: Endpoint<PushTokenRegistrationResponse> = try .jsonBody(
                    method: .post,
                    path: "/api/v1/app/push-tokens",
                    body: request
                )
                _ = try await client.send(endpoint)
                guard !Task.isCancelled else { return }
                registrationSignature = signature
            } catch is CancellationError {
                return
            } catch {
                registrationSignature = ""
            }
        }
    }
}

private struct PushTokenRegistrationRequest: Encodable {
    let familyID: String
    let appInstallID: String
    let platform: String
    let provider: String
    let pushToken: String
    let environment: String
    let deviceName: String
    let appVersion: String

    enum CodingKeys: String, CodingKey {
        case platform, provider, environment
        case familyID = "family_id"
        case appInstallID = "app_install_id"
        case pushToken = "push_token"
        case deviceName = "device_name"
        case appVersion = "app_version"
    }
}

private struct PushTokenRegistrationResponse: Decodable {
    let status: String?
}

private struct PushTokenRevocationResponse: Decodable {
    let ok: Bool
}
