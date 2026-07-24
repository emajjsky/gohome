import AVFoundation
import XCTest
@testable import GoHomeShell

final class MemoryViewModelTests: XCTestCase {
    func testMemoryPublishPhaseUsesConciseProductStatus() {
        XCTAssertEqual(MemoryPublishPhase.idle.toolbarTitle, "发布")
        XCTAssertEqual(MemoryPublishPhase.uploading(itemCount: 4).toolbarTitle, "上传中")
        XCTAssertEqual(MemoryPublishPhase.uploading(itemCount: 4).statusText, "正在上传 4 项内容")
        XCTAssertEqual(MemoryPublishPhase.saving.toolbarTitle, "保存中")
        XCTAssertEqual(MemoryPublishPhase.saving.statusText, "正在保存记忆")
    }

    func testMemoryMediaLayoutMatchesMomentsGridRules() {
        XCTAssertEqual((1...9).map(MemoryMediaLayout.columnCount), [1, 2, 3, 2, 3, 3, 3, 3, 3])
        XCTAssertEqual(MemoryMediaLayout.aspectRatio(for: 1), 4 / 3)
        XCTAssertEqual(MemoryMediaLayout.aspectRatio(for: 4), 1)
        XCTAssertEqual(MemoryMediaLayout.columnCount(for: 12), 3)
    }

    func testMemoryTimelineShowsActualPublishedTime() throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "Asia/Shanghai"))
        let now = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-07-24T13:30:00Z"))

        XCTAssertEqual(
            MemoryDateFormatting.publishedText("2026-07-24T13:05:00.000Z", now: now, calendar: calendar),
            "发布于 今天 21:05"
        )
        XCTAssertEqual(
            MemoryDateFormatting.publishedText("2026-07-23T12:00:00Z", now: now, calendar: calendar),
            "发布于 昨天 20:00"
        )
    }

    func testMemoryMediaPolicyKeepsVideoSeparateFromImageGrid() {
        let image = memoryUpload(1)
        let video = MemoryUploadAsset(
            data: Data([2]), contentType: "video/mp4", pixelWidth: 1280, pixelHeight: 720, durationSeconds: 30
        )
        XCTAssertTrue(MemoryMediaPolicy.accepts(retained: [], newMedia: Array(repeating: image, count: 9)))
        XCTAssertFalse(MemoryMediaPolicy.accepts(retained: [], newMedia: Array(repeating: image, count: 10)))
        XCTAssertTrue(MemoryMediaPolicy.accepts(retained: [], newMedia: [video]))
        XCTAssertFalse(MemoryMediaPolicy.accepts(retained: [], newMedia: [video, image]))
    }

    func testMemoryVideoCompressionPlanUsesFallbacksWithinUploadLimit() {
        XCTAssertEqual(
            MemoryVideoCompressionPlan.presets(for: 12),
            [AVAssetExportPreset1280x720, AVAssetExportPresetMediumQuality, AVAssetExportPresetLowQuality]
        )
        XCTAssertEqual(
            MemoryVideoCompressionPlan.presets(for: 50),
            [AVAssetExportPresetMediumQuality, AVAssetExportPresetLowQuality]
        )
        XCTAssertEqual(MemoryMediaPolicy.maximumVideoBytes, 24 * 1024 * 1024)
    }

    func testMemoryPickerAcceptsNinePhotosOrOneVideoOnly() {
        XCTAssertTrue(MemoryMediaSelectionPolicy.accepts(Array(repeating: .image, count: 9)))
        XCTAssertFalse(MemoryMediaSelectionPolicy.accepts(Array(repeating: .image, count: 10)))
        XCTAssertTrue(MemoryMediaSelectionPolicy.accepts([.video]))
        XCTAssertFalse(MemoryMediaSelectionPolicy.accepts([.image, .video]))
        XCTAssertFalse(MemoryMediaSelectionPolicy.accepts([.video, .video]))
        XCTAssertFalse(MemoryMediaSelectionPolicy.accepts([]))
    }

    func testMemoryLibraryPickerEnforcesLimitsBeforeSubmission() {
        XCTAssertEqual(MemoryLibrarySelectionMode.images.selectionLimit, 9)
        XCTAssertEqual(MemoryLibrarySelectionMode.images.kind, .image)
        XCTAssertEqual(MemoryLibrarySelectionMode.video.selectionLimit, 1)
        XCTAssertEqual(MemoryLibrarySelectionMode.video.kind, .video)
    }

    func testMemoryResponseDecodesPrivateTimelineFields() throws {
        let response = try JSONDecoder().decode(FamilyMemoriesResponse.self, from: Data(#"{"memories":[{"id":"memory-1","family_id":"family-1","author":{"id":"user-1","display_name":"小林"},"body":"一起看晚霞。","happened_at":"2026-07-20T02:00:00Z","location_name":"滨江步道","people":["爸爸","小林"],"media":[{"id":"media-1","asset_id":"asset-1","image_url":"/api/v1/video/assets/asset-1","sort_order":0,"alt_text":""}],"comments":[],"favorite_count":1,"is_favorite":true,"created_at":"2026-07-20T02:00:00Z","updated_at":"2026-07-20T02:00:00Z"}],"revision":"r1"}"#.utf8))

        XCTAssertEqual(response.memories.first?.author?.displayName, "小林")
        XCTAssertEqual(response.memories.first?.media.first?.assetID, "asset-1")
        XCTAssertEqual(response.memories.first?.people, ["爸爸", "小林"])
        XCTAssertTrue(response.memories.first?.isFavorite == true)
    }

    func testMemoryVideoContractDecodesTypeAndEncodesDuration() throws {
        let response = try JSONDecoder().decode(FamilyMemoriesResponse.self, from: Data(#"{"memories":[{"id":"memory-video","family_id":"family-1","body":"家庭短片","happened_at":"2026-07-24T02:00:00Z","location_name":"","people":[],"media":[{"id":"media-video","asset_id":"asset-video","image_url":"/api/v1/video/assets/asset-video","media_url":"/api/v1/video/assets/asset-video","media_type":"video","content_type":"video/mp4","duration_seconds":42.5,"sort_order":0,"alt_text":""}],"comments":[],"favorite_count":0,"is_favorite":false}],"revision":"video-r1"}"#.utf8))
        let media = try XCTUnwrap(response.memories.first?.media.first)
        XCTAssertTrue(media.isVideo)
        XCTAssertEqual(media.playbackURL, "/api/v1/video/assets/asset-video")
        XCTAssertEqual(media.durationSeconds, 42.5)

        let request = MemoryMediaUploadIntentRequest(items: [
            MemoryMediaUploadIntentItemRequest(
                contentType: "video/mp4",
                sizeBytes: 2_000_000,
                pixelWidth: 1280,
                pixelHeight: 720,
                durationSeconds: 42.5
            )
        ])
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any])
        let item = try XCTUnwrap((json["items"] as? [[String: Any]])?.first)
        XCTAssertEqual(item["duration_seconds"] as? Double, 42.5)
    }

    func testMemoryPlaybackResponseDecodesSignedURL() throws {
        let response = try JSONDecoder().decode(
            MemoryMediaPlaybackResponse.self,
            from: Data(#"{"url":"https://example.cos.ap-shanghai.myqcloud.com/memory.mp4?q-signature=test","expires_at":"2026-07-24T12:05:00.000Z"}"#.utf8)
        )

        XCTAssertEqual(response.url, "https://example.cos.ap-shanghai.myqcloud.com/memory.mp4?q-signature=test")
        XCTAssertEqual(response.expiresAt, "2026-07-24T12:05:00.000Z")
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
            },
            memoryMediaBatchUploader: { _, _ in throw APIError.invalidResponse }
        )
        let model = MemoryViewModel(repository: repository, scope: scope)

        let outcome = await model.save(
            existing: nil,
            body: "  第一次记录  ",
            happenedAt: Date(timeIntervalSince1970: 1_753_257_600),
            locationName: "家里",
            people: ["小林"],
            retainedMediaIDs: [],
            newMedia: []
        )
        XCTAssertNotNil(outcome)
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
    func testBatchMediaUploadPreservesSelectionOrder() async throws {
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
            memoryMediaBatchUploader: { _, images in
                MemoryMediaBatchUploadResponse(assets: images.map { image in
                    let index = Int(image.data.first ?? 0)
                    return MemoryUploadedAsset(
                        id: "asset-\(index)",
                        contentType: image.contentType,
                        imageURL: "/assets/\(index)",
                        mediaURL: nil,
                        mediaType: "image",
                        sizeBytes: image.data.count
                    )
                })
            }
        )
        let model = MemoryViewModel(repository: repository, scope: scope)

        let outcome = await model.save(
            existing: nil,
            body: "按选择顺序发布",
            happenedAt: Date(),
            locationName: "",
            people: [],
            retainedMediaIDs: ["retained"],
            newMedia: [1, 2, 3].map(memoryUpload)
        )

        XCTAssertNotNil(outcome)
        XCTAssertEqual(outcome?.uploadedAssets.map(\.id), ["asset-1", "asset-2", "asset-3"])
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
            memoryMediaBatchUploader: { _, images in
                MemoryMediaBatchUploadResponse(assets: images.map { image in
                    let index = Int(image.data.first ?? 0)
                    return MemoryUploadedAsset(
                        id: "asset-\(index)",
                        contentType: image.contentType,
                        imageURL: "/assets/\(index)",
                        mediaURL: nil,
                        mediaType: "image",
                        sizeBytes: image.data.count
                    )
                })
            }
        )
        let model = MemoryViewModel(repository: repository, scope: scope)

        let outcome = await model.save(
            existing: nil,
            body: "最多九张",
            happenedAt: Date(),
            locationName: "",
            people: [],
            retainedMediaIDs: (1...7).map { "retained-\($0)" },
            newMedia: [8, 9, 10].map(memoryUpload)
        )

        XCTAssertNotNil(outcome)
        let request = await requestRecorder.value
        XCTAssertEqual(request?.assetIDs.count, 9)
        XCTAssertEqual(request?.assetIDs.suffix(2), ["asset-8", "asset-9"])
    }

    private func memoryUpload(_ value: Int) -> MemoryUploadAsset {
        MemoryUploadAsset(
            data: Data([UInt8(value)]),
            contentType: "image/jpeg",
            pixelWidth: 1280,
            pixelHeight: 960,
            durationSeconds: nil
        )
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
