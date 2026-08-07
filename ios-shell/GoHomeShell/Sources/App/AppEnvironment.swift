import Foundation

struct AppEnvironment {
    let authStore: KeychainAuthStore
    let sessionContextStore: SessionContextStore
    let cache: DiskCache
    let apiClient: APIClient
    let repository: AppRepository
    let pushNotifications: PushNotificationCoordinator

    @MainActor
    static func live(bundle: Bundle = .main) throws -> AppEnvironment {
        guard
            let rawURL = bundle.object(forInfoDictionaryKey: "GoHomeAPIBaseURL") as? String,
            let baseURL = URL(string: rawURL)
        else { throw APIError.invalidResponse }

        let authStore = KeychainAuthStore()
        let sessionContextStore = SessionContextStore()
        let cache = try DiskCache()
        let client = APIClient(baseURL: baseURL) { try? await authStore.token() }
        let repository = AppRepositoryLiveFactory.make(client: client, cache: cache)
        let pushNotifications = PushNotificationCoordinator.live(client: client, bundle: bundle)

        return AppEnvironment(
            authStore: authStore,
            sessionContextStore: sessionContextStore,
            cache: cache,
            apiClient: client,
            repository: repository,
            pushNotifications: pushNotifications
        )
    }

    func clearAuthenticatedSession(scope: CacheScope?) async {
        let endpoint = Endpoint<LogoutResponse>(method: .post, path: "/api/auth/logout")
        _ = try? await apiClient.send(endpoint)
        try? await authStore.clear()
        if let scope { try? await cache.clear(scope: scope) }
        await sessionContextStore.clear()
    }

    func clearDeletedAccountSession() async {
        try? await authStore.clear()
        try? await cache.clearAll()
        await sessionContextStore.clear()
    }
}

private struct LogoutResponse: Decodable {
    let ok: Bool
}
