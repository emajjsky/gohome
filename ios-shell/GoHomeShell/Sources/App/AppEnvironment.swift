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
            },
            eventsLoader: { _ in
                try await client.send(Endpoint(
                    path: "/api/v1/events",
                    queryItems: [
                        URLQueryItem(name: "limit", value: "30"),
                        URLQueryItem(name: "view", value: "summary"),
                    ]
                ))
            },
            eventLoader: { eventID in
                try await client.send(Endpoint(path: "/api/v1/events/\(eventID)"))
            },
            eventActionLoader: { eventID, resolution in
                let endpoint: Endpoint<AppEvent> = try .jsonBody(
                    method: .patch,
                    path: "/api/v1/events/\(eventID)",
                    body: EventActionRequest(acknowledged: true, resolution: resolution)
                )
                return try await client.send(endpoint)
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

private struct EventActionRequest: Encodable {
    let acknowledged: Bool
    let resolution: String
}
