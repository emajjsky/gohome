import UIKit
import UserNotifications

final class GoHomeAppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    static let foregroundPresentationOptions: UNNotificationPresentationOptions = [
        .banner,
        .list,
        .badge,
        .sound,
    ]

    weak var notificationCoordinator: PushNotificationCoordinator? {
        didSet {
            if let token = pendingDeviceToken {
                notificationCoordinator?.receiveDeviceToken(token)
                pendingDeviceToken = nil
            }
            if let error = pendingRegistrationError {
                notificationCoordinator?.receiveRegistrationError(error)
                pendingRegistrationError = nil
            }
            if let payload = pendingNotificationUserInfo {
                notificationCoordinator?.handleNotification(userInfo: payload)
                pendingNotificationUserInfo = nil
            }
        }
    }
    private var pendingNotificationUserInfo: [AnyHashable: Any]?
    private var pendingDeviceToken: Data?
    private var pendingRegistrationError: Error?

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        if let payload = launchOptions?[.remoteNotification] as? [AnyHashable: Any] {
            if let notificationCoordinator { notificationCoordinator.handleNotification(userInfo: payload) }
            else { pendingNotificationUserInfo = payload }
        }
        return true
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        if let notificationCoordinator { notificationCoordinator.receiveDeviceToken(deviceToken) }
        else { pendingDeviceToken = deviceToken }
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        if let notificationCoordinator { notificationCoordinator.receiveRegistrationError(error) }
        else { pendingRegistrationError = error }
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        Task { @MainActor in
            let payload = notification.request.content.userInfo
            let shouldPresent = notificationCoordinator?.shouldPresentNotification(userInfo: payload) ?? true
            notificationCoordinator?.recordForegroundReceipt(userInfo: payload)
            completionHandler(shouldPresent ? Self.foregroundPresentationOptions : [])
        }
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        Task { @MainActor in
            let payload = response.notification.request.content.userInfo
            if let notificationCoordinator { notificationCoordinator.handleNotification(userInfo: payload) }
            else { pendingNotificationUserInfo = payload }
            completionHandler()
        }
    }
}
