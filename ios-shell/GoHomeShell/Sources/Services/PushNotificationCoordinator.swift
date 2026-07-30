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

    var deduplicationID: String? {
        switch self {
        case let .home(messageID): return messageID.map { "message:\($0)" }
        case let .event(eventID, _): return "event:\(eventID)"
        }
    }
}

struct PushNotificationStatus: Equatable {
    enum Authorization: Equatable {
        case unknown
        case notDetermined
        case denied
        case allowed
    }

    var authorization: Authorization = .unknown
    var alertEnabled = false
    var notificationCenterEnabled = false
    var lockScreenEnabled = false
    var soundEnabled = false

    var permissionSummary: String {
        switch authorization {
        case .unknown: return "检查中"
        case .notDetermined: return "未设置"
        case .denied: return "已关闭"
        case .allowed:
            return alertEnabled && notificationCenterEnabled ? "已允许" : "展示受限"
        }
    }

    var channelSummary: String {
        guard authorization == .allowed else { return permissionSummary }
        let enabled = [
            alertEnabled ? "横幅" : nil,
            notificationCenterEnabled ? "通知中心" : nil,
            lockScreenEnabled ? "锁屏" : nil,
            soundEnabled ? "声音" : nil,
        ].compactMap { $0 }
        return enabled.isEmpty ? "无展示通道" : enabled.joined(separator: " · ")
    }
}

enum PushNotificationTestState: Equatable {
    case idle
    case sending
    case queued
    case failed(String)

    var isSending: Bool {
        if case .sending = self { return true }
        return false
    }

    var message: String? {
        switch self {
        case .idle: return nil
        case .sending: return "正在发送"
        case .queued: return "测试通知已进入推送队列"
        case let .failed(message): return message
        }
    }
}

@MainActor
final class PushNotificationCoordinator: ObservableObject {
    @Published private(set) var pendingRoute: PushNotificationRoute?
    @Published private(set) var status = PushNotificationStatus()
    @Published private(set) var registrationActive = false
    @Published private(set) var testState = PushNotificationTestState.idle

    private let client: APIClient
    private let enabled: Bool
    private let environment: String
    private let installID: String
    private let deviceName: String
    private let appVersion: String
    private let notificationCenter: UNUserNotificationCenter
    private let registerForRemoteNotifications: () -> Void
    private let defaults: UserDefaults
    private let now: () -> Date
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
        appVersion: String = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "",
        now: @escaping () -> Date = Date.init
    ) {
        self.client = client
        self.enabled = enabled
        self.environment = environment
        self.notificationCenter = notificationCenter
        self.defaults = defaults
        self.now = now
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
        updateStatus(settings)
        var authorized = settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional
        if settings.authorizationStatus == .notDetermined {
            authorized = (try? await notificationCenter.requestAuthorization(options: [.alert, .badge, .sound])) == true
            updateStatus(await notificationCenter.notificationSettings())
        }
        guard authorized else { return }
        registerForRemoteNotifications()
        registerTokenIfReady()
    }

    func refreshStatus() async {
        guard enabled else {
            status = PushNotificationStatus(authorization: .denied)
            return
        }
        updateStatus(await notificationCenter.notificationSettings())
    }

    func receiveDeviceToken(_ data: Data) {
        deviceToken = data.map { String(format: "%02x", $0) }.joined()
        registerTokenIfReady()
    }

    func receiveRegistrationError(_ error: Error) {
        _ = error
        deviceToken = ""
        registrationSignature = ""
        registrationActive = false
    }

    func handleNotification(userInfo: [AnyHashable: Any]) {
        reportReceipt(state: "opened", userInfo: userInfo)
        guard let route = PushNotificationRoute(userInfo: userInfo) else { return }
        if let identifier = route.deduplicationID {
            guard markIfNew(identifier, namespace: "route") else { return }
        }
        pendingRoute = route
    }

    func shouldPresentNotification(userInfo: [AnyHashable: Any]) -> Bool {
        guard let route = PushNotificationRoute(userInfo: userInfo) else { return true }
        guard let identifier = route.deduplicationID else { return true }
        return markIfNew(identifier, namespace: "presentation")
    }

    func recordForegroundReceipt(userInfo: [AnyHashable: Any]) {
        reportReceipt(state: "received_foreground", userInfo: userInfo)
    }

    func sendTest(familyID: String) async {
        guard !testState.isSending else { return }
        testState = .sending
        do {
            let endpoint: Endpoint<PushNotificationTestResponse> = try .jsonBody(
                method: .post,
                path: "/api/v1/app/push-test",
                body: PushNotificationTestRequest(familyID: familyID)
            )
            _ = try await client.send(endpoint)
            testState = .queued
        } catch {
            testState = .failed("测试通知发送失败，请稍后重试")
        }
    }

    func consume(_ route: PushNotificationRoute) {
        guard pendingRoute == route else { return }
        pendingRoute = nil
    }

    func deactivate() async {
        registrationTask?.cancel()
        registrationTask = nil
        registrationSignature = ""
        registrationActive = false
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
                registrationActive = true
            } catch is CancellationError {
                return
            } catch {
                registrationSignature = ""
                registrationActive = false
            }
        }
    }

    private func updateStatus(_ settings: UNNotificationSettings) {
        let authorization: PushNotificationStatus.Authorization
        switch settings.authorizationStatus {
        case .authorized, .provisional, .ephemeral: authorization = .allowed
        case .denied: authorization = .denied
        case .notDetermined: authorization = .notDetermined
        @unknown default: authorization = .unknown
        }
        status = PushNotificationStatus(
            authorization: authorization,
            alertEnabled: settings.alertSetting == .enabled,
            notificationCenterEnabled: settings.notificationCenterSetting == .enabled,
            lockScreenEnabled: settings.lockScreenSetting == .enabled,
            soundEnabled: settings.soundSetting == .enabled
        )
    }

    private func reportReceipt(state: String, userInfo: [AnyHashable: Any]) {
        guard
            let payload = userInfo["gohome"] as? [String: Any],
            let deliveryID = Self.text(payload["delivery_id"]),
            !deliveryID.isEmpty
        else { return }
        let request = PushNotificationReceiptRequest(
            deliveryID: deliveryID,
            state: state,
            appInstallID: installID,
            appVersion: appVersion
        )
        Task { [client] in
            guard let endpoint: Endpoint<PushNotificationReceiptResponse> = try? .jsonBody(
                method: .post,
                path: "/api/v1/notifications/receipts",
                body: request
            ) else { return }
            _ = try? await client.send(endpoint)
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

    private func markIfNew(_ identifier: String, namespace: String) -> Bool {
        let key = "gohome.push-dedup.\(namespace)"
        let timestamp = now().timeIntervalSince1970
        let cutoff = timestamp - 24 * 60 * 60
        var recent = defaults.dictionary(forKey: key) as? [String: Double] ?? [:]
        recent = recent.filter { $0.value >= cutoff }
        guard recent[identifier] == nil else {
            defaults.set(recent, forKey: key)
            return false
        }
        recent[identifier] = timestamp
        if recent.count > 128 {
            for item in recent.sorted(by: { $0.value < $1.value }).prefix(recent.count - 128) {
                recent[item.key] = nil
            }
        }
        defaults.set(recent, forKey: key)
        return true
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

private struct PushNotificationTestRequest: Encodable {
    let familyID: String

    enum CodingKeys: String, CodingKey {
        case familyID = "family_id"
    }
}

private struct PushNotificationTestResponse: Decodable {
    let ok: Bool
}

private struct PushNotificationReceiptRequest: Encodable {
    let deliveryID: String
    let state: String
    let appInstallID: String
    let appVersion: String

    enum CodingKeys: String, CodingKey {
        case state
        case deliveryID = "delivery_id"
        case appInstallID = "app_install_id"
        case appVersion = "app_version"
    }
}

private struct PushNotificationReceiptResponse: Decodable {
    let ok: Bool
}

private struct PushTokenRevocationResponse: Decodable {
    let ok: Bool
}
