import Foundation

struct AppEnvironment {
    let authStore: KeychainAuthStore
    let sessionContextStore: SessionContextStore
    let cache: DiskCache
    let apiClient: APIClient
    let repository: AppRepository

    static func live(bundle: Bundle = .main) throws -> AppEnvironment {
        guard
            let rawURL = bundle.object(forInfoDictionaryKey: "GoHomeAPIBaseURL") as? String,
            let baseURL = URL(string: rawURL)
        else { throw APIError.invalidResponse }
        let authStore = KeychainAuthStore()
        let sessionContextStore = SessionContextStore()
        let cache = try DiskCache()
        let client = APIClient(baseURL: baseURL) { try? await authStore.token() }
        let repository = AppRepository(
            cache: cache,
            bootstrapLoader: {
                try await client.send(Endpoint(path: "/api/v2/app/bootstrap"))
            },
            homeLoader: { familyID in
                try await client.send(Endpoint(
                    path: "/api/v2/home",
                    queryItems: [URLQueryItem(name: "family_id", value: familyID)]
                ))
            }
        )
        return AppEnvironment(
            authStore: authStore,
            sessionContextStore: sessionContextStore,
            cache: cache,
            apiClient: client,
            repository: repository
        )
    }
}
