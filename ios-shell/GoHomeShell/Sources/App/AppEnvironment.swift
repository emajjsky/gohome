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
        let pushNotifications = PushNotificationCoordinator.live(client: client, bundle: bundle)
        let legacyMemoryBatchUpload: AppRepository.MemoryMediaBatchUploader = { familyID, media in
            guard media.allSatisfy({ !$0.isVideo }) else { throw APIError.invalidResponse }
            let request = MemoryMediaBatchRequest(images: media.map {
                MemoryMediaBatchItemRequest(
                    data: $0.data,
                    contentType: $0.contentType,
                    pixelWidth: $0.pixelWidth,
                    pixelHeight: $0.pixelHeight
                )
            })
            let endpoint: Endpoint<MemoryMediaBatchUploadResponse> = try .jsonBody(
                method: .post,
                path: "/api/v2/memory-media-batch",
                body: request,
                queryItems: [URLQueryItem(name: "family_id", value: familyID)]
            )
            return try await client.send(endpoint)
        }
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
            productsLoader: { familyID in
                try await client.send(Endpoint(
                    path: "/api/v2/products",
                    queryItems: [URLQueryItem(name: "family_id", value: familyID)]
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
            },
            profileLoader: { familyID in
                async let bindings: [DeviceBinding] = client.send(Endpoint(
                    path: "/api/device-bindings",
                    queryItems: [URLQueryItem(name: "family_id", value: familyID)]
                ))
                async let cameras: [CameraConfig] = client.send(Endpoint(path: "/api/app/cameras"))
                async let rules: FamilyRules = client.send(Endpoint(
                    path: "/api/v1/rules",
                    queryItems: [URLQueryItem(name: "family_id", value: familyID)]
                ))
                async let carePreferences: CarePreferences = client.send(Endpoint(
                    path: "/api/v1/families/\(familyID)/care-preferences"
                ))
                async let productEnvelope: ProductPreferencesEnvelope? = try? client.send(Endpoint(
                    path: "/api/v2/product-preferences",
                    queryItems: [URLQueryItem(name: "family_id", value: familyID)]
                ))
                async let elder: ElderProfile? = try? client.send(Endpoint(
                    path: "/api/v1/families/\(familyID)/elders/elder_primary/profile"
                ))

                let loadedCameras = try await cameras

                return try await ProfileData(
                    elder: elder,
                    bindings: bindings,
                    cameras: loadedCameras.filter { $0.familyID == familyID },
                    rules: rules,
                    carePreferences: carePreferences,
                    productPreferences: productEnvelope?.preferences ?? ProductPreferences(categories: [], needs: [])
                )
            },
            rulesUpdater: { familyID, patch in
                let endpoint: Endpoint<FamilyRules> = try .jsonBody(
                    method: .put,
                    path: "/api/v1/rules",
                    body: patch,
                    queryItems: [URLQueryItem(name: "family_id", value: familyID)]
                )
                return try await client.send(endpoint)
            },
            carePreferencesUpdater: { familyID, patch in
                let endpoint: Endpoint<CarePreferences> = try .jsonBody(
                    method: .put,
                    path: "/api/v1/families/\(familyID)/care-preferences",
                    body: patch
                )
                return try await client.send(endpoint)
            },
            messageActionLoader: { familyID, messageID, request in
                let endpoint: Endpoint<CareMessageActionResponse> = try .jsonBody(
                    method: .post,
                    path: "/api/v2/messages/\(messageID)/actions",
                    body: request,
                    queryItems: [URLQueryItem(name: "family_id", value: familyID)]
                )
                return try await client.send(endpoint)
            },
            memoriesLoader: { familyID in
                try await client.send(Endpoint(
                    path: "/api/v2/memories",
                    queryItems: [URLQueryItem(name: "family_id", value: familyID)]
                ))
            },
            memoryCreator: { familyID, request in
                let endpoint: Endpoint<FamilyMemoryEnvelope> = try .jsonBody(
                    method: .post,
                    path: "/api/v2/memories",
                    body: request,
                    queryItems: [URLQueryItem(name: "family_id", value: familyID)]
                )
                return try await client.send(endpoint)
            },
            memoryUpdater: { familyID, memoryID, request in
                let endpoint: Endpoint<FamilyMemoryEnvelope> = try .jsonBody(
                    method: .patch,
                    path: "/api/v2/memories/\(memoryID)",
                    body: request,
                    queryItems: [URLQueryItem(name: "family_id", value: familyID)]
                )
                return try await client.send(endpoint)
            },
            memoryCommentCreator: { familyID, memoryID, request in
                let endpoint: Endpoint<FamilyMemoryEnvelope> = try .jsonBody(
                    method: .post,
                    path: "/api/v2/memories/\(memoryID)/comments",
                    body: request,
                    queryItems: [URLQueryItem(name: "family_id", value: familyID)]
                )
                return try await client.send(endpoint)
            },
            memoryFavoriteUpdater: { familyID, memoryID, favorite in
                try await client.send(Endpoint(
                    method: favorite ? .put : .delete,
                    path: "/api/v2/memories/\(memoryID)/favorite",
                    queryItems: [URLQueryItem(name: "family_id", value: familyID)]
                ))
            },
            memoryDeleter: { familyID, memoryID in
                try await client.send(Endpoint(
                    method: .delete,
                    path: "/api/v2/memories/\(memoryID)",
                    queryItems: [URLQueryItem(name: "family_id", value: familyID)]
                ))
            },
            memoryMediaUploader: { familyID, data, contentType in
                try await client.upload(
                    path: "/api/v2/memory-media",
                    queryItems: [URLQueryItem(name: "family_id", value: familyID)],
                    data: data,
                    contentType: contentType,
                    response: MemoryMediaUploadResponse.self
                )
            },
            memoryMediaBatchUploader: { familyID, media in
                let intentRequest = MemoryMediaUploadIntentRequest(items: media.map {
                    MemoryMediaUploadIntentItemRequest(
                        contentType: $0.contentType,
                        sizeBytes: $0.data.count,
                        pixelWidth: $0.pixelWidth,
                        pixelHeight: $0.pixelHeight,
                        durationSeconds: $0.durationSeconds
                    )
                })
                let intentEndpoint: Endpoint<MemoryMediaUploadIntentResponse> = try .jsonBody(
                    method: .post,
                    path: "/api/v2/memory-media-upload-intents",
                    body: intentRequest,
                    queryItems: [URLQueryItem(name: "family_id", value: familyID)]
                )
                let intentResponse: MemoryMediaUploadIntentResponse
                do {
                    intentResponse = try await client.send(intentEndpoint)
                } catch let APIError.server(statusCode, _) where statusCode == 404 || statusCode == 503 {
                    return try await legacyMemoryBatchUpload(familyID, media)
                }
                guard intentResponse.uploads.count == media.count else { throw APIError.invalidResponse }

                do {
                    try await withThrowingTaskGroup(of: Void.self) { group in
                        for (intent, item) in zip(intentResponse.uploads, media) {
                            group.addTask {
                                try await client.uploadDirectly(
                                    to: intent.uploadURL,
                                    data: item.data,
                                    contentType: intent.contentType
                                )
                            }
                        }
                        try await group.waitForAll()
                    }

                    let completeRequest = MemoryMediaUploadCompleteRequest(items: intentResponse.uploads.map {
                        MemoryMediaUploadCompleteItemRequest(assetID: $0.assetID, uploadToken: $0.uploadToken)
                    })
                    let completeEndpoint: Endpoint<MemoryMediaBatchUploadResponse> = try .jsonBody(
                        method: .post,
                        path: "/api/v2/memory-media-upload-complete",
                        body: completeRequest,
                        queryItems: [URLQueryItem(name: "family_id", value: familyID)]
                    )
                    return try await client.send(completeEndpoint)
                } catch {
                    let abortRequest = MemoryMediaUploadCompleteRequest(items: intentResponse.uploads.map {
                        MemoryMediaUploadCompleteItemRequest(assetID: $0.assetID, uploadToken: $0.uploadToken)
                    })
                    if let abortEndpoint: Endpoint<MemoryMediaUploadAbortResponse> = try? .jsonBody(
                        method: .post,
                        path: "/api/v2/memory-media-upload-abort",
                        body: abortRequest,
                        queryItems: [URLQueryItem(name: "family_id", value: familyID)]
                    ) {
                        _ = try? await client.send(abortEndpoint)
                    }
                    throw error
                }
            },
            activityTimelineLoader: { familyID, date in
                try await client.send(Endpoint(
                    path: "/api/v2/activity-timeline",
                    queryItems: [
                        URLQueryItem(name: "family_id", value: familyID),
                        URLQueryItem(name: "date", value: date),
                    ]
                ))
            },
            activityOverviewLoader: { familyID, date in
                try await client.send(Endpoint(
                    path: "/api/v2/activity-overview",
                    queryItems: [
                        URLQueryItem(name: "family_id", value: familyID),
                        URLQueryItem(name: "date", value: date),
                    ]
                ))
            },
            activityHistoryDeleter: { familyID in
                try await client.send(Endpoint(
                    method: .delete,
                    path: "/api/v2/activity-history",
                    queryItems: [URLQueryItem(name: "family_id", value: familyID)]
                ))
            }
        )
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
}

private struct EventActionRequest: Encodable {
    let acknowledged: Bool
    let resolution: String
}

private struct LogoutResponse: Decodable {
    let ok: Bool
}
