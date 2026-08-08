import Foundation

enum MemoryMediaUploadTransaction {
    static func execute(
        client: APIClient,
        familyID: String,
        media: [MemoryUploadAsset]
    ) async throws -> MemoryMediaBatchUploadResponse {
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
        let intentResponse = try await client.send(intentEndpoint)
        let finalizationRequest = MemoryMediaUploadCompleteRequest(items: intentResponse.uploads.map {
            MemoryMediaUploadCompleteItemRequest(assetID: $0.assetID, uploadToken: $0.uploadToken)
        })

        do {
            guard intentResponse.uploads.count == media.count else { throw APIError.invalidResponse }
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
            try Task.checkCancellation()

            let completeEndpoint: Endpoint<MemoryMediaBatchUploadResponse> = try .jsonBody(
                method: .post,
                path: "/api/v2/memory-media-upload-complete",
                body: finalizationRequest,
                queryItems: [URLQueryItem(name: "family_id", value: familyID)]
            )
            return try await client.send(completeEndpoint)
        } catch {
            await abort(client: client, familyID: familyID, request: finalizationRequest)
            throw error
        }
    }

    private static func abort(
        client: APIClient,
        familyID: String,
        request: MemoryMediaUploadCompleteRequest
    ) async {
        let cleanup = Task.detached(priority: .utility) {
            let endpoint: Endpoint<MemoryMediaUploadAbortResponse> = try .jsonBody(
                method: .post,
                path: "/api/v2/memory-media-upload-abort",
                body: request,
                queryItems: [URLQueryItem(name: "family_id", value: familyID)]
            )
            return try await client.send(endpoint)
        }
        _ = try? await cleanup.value
    }
}
