import Foundation

enum AppRepositoryLiveFactory {
    static func make(client: APIClient, cache: DiskCache) -> AppRepository {
            return AppRepository(
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
                productPreferencesUpdater: { familyID, preferences in
                    let endpoint: Endpoint<ProductPreferencesEnvelope> = try .jsonBody(
                        method: .put,
                        path: "/api/v2/product-preferences",
                        body: preferences,
                        queryItems: [URLQueryItem(name: "family_id", value: familyID)]
                    )
                    return try await client.send(endpoint)
                },
                elderProfileUpdater: { familyID, elderID, payload in
                    let endpoint: Endpoint<ElderProfile> = try .jsonBody(
                        method: .put,
                        path: "/api/v1/families/\(familyID)/elders/\(elderID)/profile",
                        body: payload
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
                memoryMediaBatchUploader: { familyID, media in
                    try await MemoryMediaUploadTransaction.execute(
                        client: client,
                        familyID: familyID,
                        media: media
                    )
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
                },
                cameraCreator: { request in
                    let endpoint: Endpoint<CameraConfig> = try .jsonBody(
                        method: .post,
                        path: "/api/cameras",
                        body: request
                    )
                    return try await client.send(endpoint)
                },
                cameraUpdater: { cameraID, request in
                    let endpoint: Endpoint<CameraConfig> = try .jsonBody(
                        method: .patch,
                        path: "/api/cameras/\(cameraID)",
                        body: request
                    )
                    return try await client.send(endpoint)
                },
                cameraDeleter: { cameraID in
                    try await client.send(Endpoint(method: .delete, path: "/api/cameras/\(cameraID)"))
                },
                deviceUnbinder: { bindingID in
                    try await client.send(Endpoint(method: .delete, path: "/api/device-bindings/\(bindingID)"))
                },
                accountExporter: {
                    try await client.data(path: "/api/v2/account/export")
                },
                accountDeletionPlanLoader: {
                    try await client.send(Endpoint(path: "/api/v2/account/deletion-plan"))
                },
                accountDeleter: {
                    let endpoint: Endpoint<AccountDeleteResponse> = try .jsonBody(
                        method: .delete,
                        path: "/api/v2/account",
                        body: AccountDeleteRequest(confirmation: "DELETE_ACCOUNT")
                    )
                    return try await client.send(endpoint)
                },
                accountProfileLoader: {
                    try await client.send(Endpoint(path: "/api/v2/account/profile"))
                },
                accountProfileUpdater: { patch in
                    let endpoint: Endpoint<AccountProfileEnvelope> = try .jsonBody(
                        method: .patch,
                        path: "/api/v2/account/profile",
                        body: patch
                    )
                    return try await client.send(endpoint)
                },
                familyMembersLoader: { familyID in
                    try await client.send(Endpoint(path: "/api/v2/families/\(familyID)/members"))
                },
                familyMemberRemover: { familyID, memberID in
                    try await client.send(Endpoint(method: .delete, path: "/api/v2/families/\(familyID)/members/\(memberID)"))
                },
                familyLeaver: { familyID in
                    try await client.send(Endpoint(method: .post, path: "/api/v2/families/\(familyID)/leave"))
                },
                familyOwnershipTransferer: { familyID, memberID in
                    let endpoint: Endpoint<FamilyOwnershipTransferResponse> = try .jsonBody(
                        method: .post,
                        path: "/api/v2/families/\(familyID)/ownership-transfer",
                        body: FamilyOwnershipTransferRequest(targetMemberID: memberID, confirmation: "TRANSFER_OWNERSHIP")
                    )
                    return try await client.send(endpoint)
                },
                familyInvitationsLoader: { familyID in
                    try await client.send(Endpoint(path: "/api/v2/families/\(familyID)/invitations"))
                },
                familyInvitationCreator: { familyID in
                    let endpoint: Endpoint<FamilyInvitation> = try .jsonBody(
                        method: .post,
                        path: "/api/v2/families/\(familyID)/invitations",
                        body: FamilyInvitationCreateRequest(expiresInMinutes: 10)
                    )
                    return try await client.send(endpoint)
                },
                familyInvitationRevoker: { familyID, invitationID in
                    try await client.send(Endpoint(
                        method: .delete,
                        path: "/api/v2/families/\(familyID)/invitations/\(invitationID)"
                    ))
                }
            )
    }
}

private struct EventActionRequest: Encodable {
    let acknowledged: Bool
    let resolution: String
}
