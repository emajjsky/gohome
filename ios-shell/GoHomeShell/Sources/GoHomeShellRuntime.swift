import Foundation
import UIKit
import UserNotifications

@MainActor
final class GoHomeShellRuntime: ObservableObject {
    @Published private(set) var webAppURL: URL = ShellConfig.webAppURL
    @Published private(set) var hasPresentedWebContent = false
    @Published private(set) var webLoadError: String?
    @Published private(set) var webReloadID = UUID()

    private let center = UNUserNotificationCenter.current()
    private let defaults = UserDefaults.standard
    private let installIDKey = "gohome.appInstallID"
    private let appVersion = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0.1.0"
    private var pushToken = ""
    private var pendingLaunchPayload: [String: Any]?

    func markWebContentLoading() {
        webLoadError = nil
    }

    func markWebContentReady() {
        hasPresentedWebContent = true
        webLoadError = nil
    }

    func markWebContentFailed() {
        guard !hasPresentedWebContent else { return }
        webLoadError = "暂时无法连接服务，请检查网络后重试"
    }

    func retryWebContent() {
        webLoadError = nil
        webReloadID = UUID()
    }

    var appInstallID: String {
        if let existing = defaults.string(forKey: installIDKey), !existing.isEmpty {
            return existing
        }
        let value = "ios-\(UUID().uuidString.lowercased())"
        defaults.set(value, forKey: installIDKey)
        return value
    }

    func handleIncomingURL(_ url: URL) {
        guard url.scheme?.lowercased() == ShellConfig.deepLinkScheme.lowercased() else { return }
        let components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        let next = components?.queryItems?.first(where: { $0.name == "next" })?.value ?? ""
        pendingLaunchPayload = [
            "url": url.absoluteString,
            "next": next,
        ]
        navigate(to: next)
    }

    func handleNotificationResponse(userInfo: [AnyHashable: Any]) {
        guard let gohome = userInfo["gohome"] as? [String: Any] else { return }
        var payload: [String: Any] = [:]
        let openDeepLink = String(gohome["open_deep_link"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        payload["next"] = nextPath(from: openDeepLink, fallback: gohome)
        payload["event_id"] = gohome["event_id"]
        payload["camera_id"] = gohome["camera_id"]
        payload["open_deep_link"] = openDeepLink
        pendingLaunchPayload = payload
        navigate(to: payload["next"] as? String ?? "")
    }

    func updatePushToken(_ data: Data) {
        pushToken = data.map { String(format: "%02x", $0) }.joined()
    }

    func clearPushToken(error: Error? = nil) {
        if error != nil {
            pushToken = ""
        }
    }

    func registerForPush() async throws -> [String: Any] {
        guard ShellConfig.pushEnabled else {
            throw GoHomeShellError.pushUnavailableForDemo
        }
        let granted = try await center.requestAuthorization(options: [.alert, .badge, .sound])
        guard granted else {
            throw GoHomeShellError.pushPermissionDenied
        }
        UIApplication.shared.registerForRemoteNotifications()
        if !pushToken.isEmpty {
            return pushRegistrationPayload()
        }
        for _ in 0..<20 {
            try await Task.sleep(nanoseconds: 500_000_000)
            if !pushToken.isEmpty {
                return pushRegistrationPayload()
            }
        }
        throw GoHomeShellError.pushTokenUnavailable
    }

    func consumeLaunchPayload() -> [String: Any]? {
        let payload = pendingLaunchPayload
        pendingLaunchPayload = nil
        return payload
    }

    func openExternalURL(_ rawURL: String) async throws -> [String: Any] {
        let value = rawURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: value), let scheme = url.scheme?.lowercased() else {
            throw GoHomeShellError.invalidExternalURL
        }
        guard ["tel", "sms", "weixin"].contains(scheme) else {
            throw GoHomeShellError.externalURLNotAllowed
        }
        guard await UIApplication.shared.open(url) else {
            throw GoHomeShellError.externalAppUnavailable
        }
        return ["opened": true, "scheme": scheme]
    }

    private func navigate(to path: String) {
        let value = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty, let target = URL(string: value, relativeTo: ShellConfig.webAppURL)?.absoluteURL else { return }
        guard target.host?.lowercased() == ShellConfig.webAppURL.host?.lowercased() else { return }
        webAppURL = target
    }

    private func pushRegistrationPayload() -> [String: Any] {
        [
            "app_install_id": appInstallID,
            "platform": "ios",
            "provider": "apns",
            "push_token": pushToken,
            "device_name": UIDevice.current.name,
            "app_version": appVersion,
            "environment": ShellConfig.pushEnvironment,
            "metadata": [
                "native_shell": "ios",
            ],
        ]
    }

    private func nextPath(from deepLink: String, fallback: [String: Any]) -> String {
        if
            !deepLink.isEmpty,
            let url = URL(string: deepLink),
            let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
            let next = components.queryItems?.first(where: { $0.name == "next" })?.value,
            !next.isEmpty
        {
            return next
        }
        if let eventID = fallback["event_id"] {
            return "event_detail.html?eventId=\(eventID)"
        }
        if let cameraID = fallback["camera_id"] {
            return "watch.html?cameraId=\(cameraID)"
        }
        return ""
    }
}

enum GoHomeShellError: LocalizedError {
    case pushUnavailableForDemo
    case pushPermissionDenied
    case pushTokenUnavailable
    case invalidExternalURL
    case externalURLNotAllowed
    case externalAppUnavailable

    var errorDescription: String? {
        switch self {
        case .pushUnavailableForDemo:
            return "Push is disabled for the demo build"
        case .pushPermissionDenied:
            return "Push permission was denied"
        case .pushTokenUnavailable:
            return "APNs device token is still unavailable"
        case .invalidExternalURL:
            return "无法识别要打开的链接"
        case .externalURLNotAllowed:
            return "该外部链接不允许从 App 打开"
        case .externalAppUnavailable:
            return "手机上没有安装对应应用，或系统暂时无法打开"
        }
    }
}

enum ShellConfig {
    static let webAppURL: URL = {
        let raw = Bundle.main.object(forInfoDictionaryKey: "GoHomeWebAppURL") as? String ?? "https://gohome.ai2shx.club/index.html?app=1"
        return URL(string: raw) ?? URL(string: "https://gohome.ai2shx.club/index.html?app=1")!
    }()

    static let pushEnvironment: String = {
        let raw = (Bundle.main.object(forInfoDictionaryKey: "GoHomePushEnvironment") as? String ?? "sandbox").trimmingCharacters(in: .whitespacesAndNewlines)
        return raw.isEmpty ? "sandbox" : raw.lowercased()
    }()

    static let pushEnabled: Bool = {
        Bundle.main.object(forInfoDictionaryKey: "GoHomePushEnabled") as? Bool ?? false
    }()

    static let deepLinkScheme: String = {
        let types = Bundle.main.object(forInfoDictionaryKey: "CFBundleURLTypes") as? [[String: Any]]
        let first = (types?.first?["CFBundleURLSchemes"] as? [String])?.first ?? "gohome"
        return first
    }()
}
