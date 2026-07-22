import UIKit
import UserNotifications

final class GoHomeAppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    weak var runtime: GoHomeShellRuntime? {
        didSet {
            guard let runtime, let payload = pendingNotificationUserInfo else { return }
            runtime.handleNotificationResponse(userInfo: payload)
            pendingNotificationUserInfo = nil
        }
    }
    private var pendingNotificationUserInfo: [AnyHashable: Any]?

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        if let payload = launchOptions?[.remoteNotification] as? [AnyHashable: Any] {
            if let runtime { runtime.handleNotificationResponse(userInfo: payload) }
            else { pendingNotificationUserInfo = payload }
        }
        return true
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        Task { @MainActor in runtime?.updatePushToken(deviceToken) }
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        Task { @MainActor in runtime?.clearPushToken(error: error) }
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .badge, .sound])
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        Task { @MainActor in
            let payload = response.notification.request.content.userInfo
            if let runtime { runtime.handleNotificationResponse(userInfo: payload) }
            else { pendingNotificationUserInfo = payload }
            completionHandler()
        }
    }
}
