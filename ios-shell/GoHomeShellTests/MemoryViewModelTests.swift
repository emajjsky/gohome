import XCTest
@testable import GoHomeShell

final class MemoryViewModelTests: XCTestCase {
    func testMemoryMediaLayoutMatchesMomentsGridRules() {
        XCTAssertEqual((1...9).map(MemoryMediaLayout.columnCount), [1, 2, 3, 2, 3, 3, 3, 3, 3])
        XCTAssertEqual(MemoryMediaLayout.aspectRatio(for: 1), 4 / 3)
        XCTAssertEqual(MemoryMediaLayout.aspectRatio(for: 4), 1)
        XCTAssertEqual(MemoryMediaLayout.columnCount(for: 12), 3)
    }

    func testMemoryResponseDecodesPrivateTimelineFields() throws {
        let response = try JSONDecoder().decode(FamilyMemoriesResponse.self, from: Data(#"{"memories":[{"id":"memory-1","family_id":"family-1","author":{"id":"user-1","display_name":"小林"},"body":"一起看晚霞。","happened_at":"2026-07-20T02:00:00Z","location_name":"滨江步道","people":["爸爸","小林"],"media":[{"id":"media-1","asset_id":"asset-1","image_url":"/api/v1/video/assets/asset-1","sort_order":0,"alt_text":""}],"comments":[],"favorite_count":1,"is_favorite":true,"created_at":"2026-07-20T02:00:00Z","updated_at":"2026-07-20T02:00:00Z"}],"revision":"r1"}"#.utf8))

        XCTAssertEqual(response.memories.first?.author?.displayName, "小林")
        XCTAssertEqual(response.memories.first?.media.first?.assetID, "asset-1")
        XCTAssertEqual(response.memories.first?.people, ["爸爸", "小林"])
        XCTAssertTrue(response.memories.first?.isFavorite == true)
    }

    func testMemoryCacheIsDeliveredBeforeRefresh() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let cache = try DiskCache(rootURL: root)
        let scope = CacheScope(userID: "user-1", familyID: "family-1")
        let cached = FamilyMemoriesResponse(memories: [], revision: "cached")
        let fresh = FamilyMemoriesResponse(memories: [], revision: "fresh")
        try await cache.write(cached, key: "memories", scope: scope)
        let repository = AppRepository(
            cache: cache,
            bootstrapLoader: { throw APIError.invalidResponse },
            memoriesLoader: { _ in fresh }
        )
        let recorder = MemoryStateRecorder()

        await repository.memories(scope: scope) { await recorder.append($0) }

        let states = await recorder.values
        XCTAssertEqual(states.map(\.value?.revision), ["cached", "fresh"])
        XCTAssertEqual(states.first?.isRefreshing, true)
        XCTAssertEqual(states.last?.isRefreshing, false)
    }

    @MainActor
    func testMemoryWriteLifecycleUpdatesLocalTimelineWithoutReloading() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let cache = try DiskCache(rootURL: root)
        let scope = CacheScope(userID: "user-1", familyID: "family-1")
        let recorder = MemoryWriteRecorder()
        let created = makeMemory(id: "memory-1", body: "第一次记录")
        let favorited = makeMemory(id: "memory-1", body: "第一次记录", favoriteCount: 1, isFavorite: true)
        let commented = makeMemory(id: "memory-1", body: "第一次记录", comments: [
            MemoryComment(id: "comment-1", authorUserID: "user-1", body: "很好", createdAt: "2026-07-23T08:00:00Z")
        ])
        let repository = AppRepository(
            cache: cache,
            bootstrapLoader: { throw APIError.invalidResponse },
            memoryCreator: { _, request in
                await recorder.recordCreated(request)
                return FamilyMemoryEnvelope(memory: created)
            },
            memoryCommentCreator: { _, _, request in
                await recorder.recordComment(request.body)
                return FamilyMemoryEnvelope(memory: commented)
            },
            memoryFavoriteUpdater: { _, _, value in
                await recorder.recordFavorite(value)
                return FamilyMemoryEnvelope(memory: favorited)
            },
            memoryDeleter: { _, memoryID in
                await recorder.recordDeleted(memoryID)
                return MemoryDeleteResponse(deleted: true, memoryID: memoryID)
            }
        )
        let model = MemoryViewModel(repository: repository, scope: scope)

        let didSave = await model.save(
            existing: nil,
            body: "  第一次记录  ",
            happenedAt: Date(timeIntervalSince1970: 1_753_257_600),
            locationName: "家里",
            people: ["小林"],
            retainedMediaIDs: [],
            newImages: []
        )
        XCTAssertTrue(didSave)
        XCTAssertEqual(model.memories.map(\.id), ["memory-1"])
        var writes = await recorder.snapshot()
        XCTAssertEqual(writes.createdBody, "第一次记录")

        await model.toggleFavorite(created)
        XCTAssertTrue(model.memories.first?.isFavorite == true)
        writes = await recorder.snapshot()
        XCTAssertEqual(writes.favoriteValue, true)

        let didComment = await model.addComment("很好", to: favorited)
        XCTAssertTrue(didComment)
        XCTAssertEqual(model.memories.first?.comments.first?.body, "很好")
        writes = await recorder.snapshot()
        XCTAssertEqual(writes.commentBody, "很好")

        let didDelete = await model.delete(commented)
        XCTAssertTrue(didDelete)
        XCTAssertTrue(model.memories.isEmpty)
        writes = await recorder.snapshot()
        XCTAssertEqual(writes.deletedMemoryID, "memory-1")
    }

    @MainActor
    func testParallelMediaUploadsPreserveSelectionOrder() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let cache = try DiskCache(rootURL: root)
        let scope = CacheScope(userID: "user-1", familyID: "family-1")
        let requestRecorder = MemoryRequestRecorder()
        let repository = AppRepository(
            cache: cache,
            bootstrapLoader: { throw APIError.invalidResponse },
            memoryCreator: { _, request in
                await requestRecorder.record(request)
                return FamilyMemoryEnvelope(memory: self.makeMemory(id: "memory-ordered", body: request.body))
            },
            memoryMediaUploader: { _, data, _ in
                let index = Int(data.first ?? 0)
                try await Task.sleep(nanoseconds: UInt64(3 - index) * 20_000_000)
                return MemoryMediaUploadResponse(asset: MemoryUploadedAsset(
                    id: "asset-\(index)",
                    contentType: "image/jpeg",
                    imageURL: "/assets/\(index)",
                    sizeBytes: data.count
                ))
            }
        )
        let model = MemoryViewModel(repository: repository, scope: scope)

        let didSave = await model.save(
            existing: nil,
            body: "按选择顺序发布",
            happenedAt: Date(),
            locationName: "",
            people: [],
            retainedMediaIDs: ["retained"],
            newImages: [1, 2, 3].map { (Data([$0]), "image/jpeg") }
        )

        XCTAssertTrue(didSave)
        let request = await requestRecorder.value
        XCTAssertEqual(request?.assetIDs, ["retained", "asset-1", "asset-2", "asset-3"])
    }

    @MainActor
    func testMemorySaveCapsMediaAtNineAssets() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let cache = try DiskCache(rootURL: root)
        let scope = CacheScope(userID: "user-1", familyID: "family-1")
        let requestRecorder = MemoryRequestRecorder()
        let repository = AppRepository(
            cache: cache,
            bootstrapLoader: { throw APIError.invalidResponse },
            memoryCreator: { _, request in
                await requestRecorder.record(request)
                return FamilyMemoryEnvelope(memory: self.makeMemory(id: "memory-capped", body: request.body))
            },
            memoryMediaUploader: { _, data, _ in
                let index = Int(data.first ?? 0)
                return MemoryMediaUploadResponse(asset: MemoryUploadedAsset(
                    id: "asset-\(index)",
                    contentType: "image/jpeg",
                    imageURL: "/assets/\(index)",
                    sizeBytes: data.count
                ))
            }
        )
        let model = MemoryViewModel(repository: repository, scope: scope)

        let didSave = await model.save(
            existing: nil,
            body: "最多九张",
            happenedAt: Date(),
            locationName: "",
            people: [],
            retainedMediaIDs: (1...7).map { "retained-\($0)" },
            newImages: [8, 9, 10].map { (Data([$0]), "image/jpeg") }
        )

        XCTAssertTrue(didSave)
        let request = await requestRecorder.value
        XCTAssertEqual(request?.assetIDs.count, 9)
        XCTAssertEqual(request?.assetIDs.suffix(2), ["asset-8", "asset-9"])
    }

    private func makeMemory(
        id: String,
        body: String,
        favoriteCount: Int = 0,
        isFavorite: Bool = false,
        comments: [MemoryComment] = []
    ) -> FamilyMemory {
        FamilyMemory(
            id: id,
            familyID: "family-1",
            author: MemoryAuthor(id: "user-1", displayName: "小林"),
            body: body,
            happenedAt: "2026-07-23T08:00:00Z",
            locationName: "家里",
            people: ["小林"],
            media: [],
            comments: comments,
            favoriteCount: favoriteCount,
            isFavorite: isFavorite,
            createdAt: "2026-07-23T08:00:00Z",
            updatedAt: "2026-07-23T08:00:00Z"
        )
    }
}

private actor MemoryStateRecorder {
    private(set) var values: [Loadable<FamilyMemoriesResponse>] = []
    func append(_ value: Loadable<FamilyMemoriesResponse>) { values.append(value) }
}

private actor MemoryWriteRecorder {
    private(set) var createdBody: String?
    private(set) var favoriteValue: Bool?
    private(set) var commentBody: String?
    private(set) var deletedMemoryID: String?

    func recordCreated(_ request: MemoryDraftRequest) { createdBody = request.body }
    func recordFavorite(_ value: Bool) { favoriteValue = value }
    func recordComment(_ body: String) { commentBody = body }
    func recordDeleted(_ memoryID: String) { deletedMemoryID = memoryID }

    func snapshot() -> (createdBody: String?, favoriteValue: Bool?, commentBody: String?, deletedMemoryID: String?) {
        (createdBody, favoriteValue, commentBody, deletedMemoryID)
    }
}

private actor MemoryRequestRecorder {
    private(set) var value: MemoryDraftRequest?
    func record(_ request: MemoryDraftRequest) { value = request }
}
