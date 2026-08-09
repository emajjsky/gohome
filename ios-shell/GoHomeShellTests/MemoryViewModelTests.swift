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

    func testFirstPickerSelectionPromotesTheExactMediaRequest() throws {
        let url = try makeStagedMediaFile()
        defer { try? FileManager.default.removeItem(at: url) }
        let media = MemoryPickedMedia(kind: .image, localURL: url)
        var presentation = MemoryComposerPresentationState()

        presentation.stage([media])
        let pendingID = try XCTUnwrap(presentation.pendingRequest?.id)
        presentation.promotePending()

        XCTAssertEqual(presentation.activeRequest?.id, pendingID)
        XCTAssertEqual(presentation.activeRequest?.seed.media.map(\.localURL), [url])
        XCTAssertNil(presentation.pendingRequest)
    }

    func testReplacingPendingPickerSelectionRemovesAbandonedFiles() throws {
        let abandonedURL = try makeStagedMediaFile()
        let retainedURL = try makeStagedMediaFile()
        defer { try? FileManager.default.removeItem(at: retainedURL) }
        var presentation = MemoryComposerPresentationState()

        presentation.stage([MemoryPickedMedia(kind: .image, localURL: abandonedURL)])
        presentation.stage([MemoryPickedMedia(kind: .image, localURL: retainedURL)])

        XCTAssertFalse(FileManager.default.fileExists(atPath: abandonedURL.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: retainedURL.path))
        XCTAssertEqual(presentation.pendingRequest?.seed.media.map(\.localURL), [retainedURL])
    }

    func testCancellingPendingPickerSelectionLeavesNoComposerRequest() throws {
        let url = try makeStagedMediaFile()
        var presentation = MemoryComposerPresentationState()

        presentation.stage([MemoryPickedMedia(kind: .video, localURL: url)])
        presentation.discardPending()

        XCTAssertNil(presentation.pendingRequest)
        XCTAssertNil(presentation.activeRequest)
        XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    }

    func testEditingMemoryPresentsAnEmptySeed() {
        let memory = makeMemory(id: "memory-edit", body: "准备修改")
        var presentation = MemoryComposerPresentationState()

        presentation.presentEditor(for: memory)

        XCTAssertEqual(presentation.activeRequest?.memory, memory)
        XCTAssertTrue(presentation.activeRequest?.seed.media.isEmpty == true)
        XCTAssertNil(presentation.pendingRequest)
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
    func testCancelledMemoryLoadCannotPublishLateResponse() async throws {
        let original = FamilyMemoriesResponse(memories: [makeMemory(id: "memory-original", body: "原始内容")], revision: "original")
        let late = FamilyMemoriesResponse(memories: [makeMemory(id: "memory-late", body: "迟到内容")], revision: "late")
        let repository = AppRepository(
            cache: try DiskCache(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)),
            bootstrapLoader: { throw APIError.invalidResponse },
            memoriesLoader: { _ in
                try? await Task.sleep(nanoseconds: 100_000_000)
                return late
            }
        )
        let model = MemoryViewModel(
            repository: repository,
            scope: CacheScope(userID: "user-1", familyID: "family-1"),
            seed: original
        )

        model.start()
        await waitUntil { model.state.isRefreshing }
        XCTAssertEqual(model.state.value, original)
        model.cancelInFlightLoad()
        try await Task.sleep(nanoseconds: 150_000_000)

        XCTAssertEqual(model.state.value, original)
        XCTAssertFalse(model.state.isRefreshing)
        XCTAssertNil(model.state.staleReason)
    }

    @MainActor
    func testMemoryLoadRestartsAfterLifecycleCancellation() async throws {
        let fresh = FamilyMemoriesResponse(memories: [makeMemory(id: "memory-fresh", body: "重新进入")], revision: "fresh")
        let repository = AppRepository(
            cache: try DiskCache(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)),
            bootstrapLoader: { throw APIError.invalidResponse },
            memoriesLoader: { _ in
                try? await Task.sleep(nanoseconds: 100_000_000)
                return fresh
            }
        )
        let model = MemoryViewModel(repository: repository, scope: CacheScope(userID: "user-1", familyID: "family-1"))

        model.start()
        try await Task.sleep(nanoseconds: 20_000_000)
        model.cancelInFlightLoad()
        model.start()
        await waitUntil { model.state.value?.revision == fresh.revision }

        XCTAssertEqual(model.state.value, fresh)
        XCTAssertFalse(model.state.isRefreshing)
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
    func testCancelledFavoriteRollsBackWithoutError() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let original = makeMemory(id: "favorite-cancel", body: "收藏取消")
        let repository = AppRepository(
            cache: try DiskCache(rootURL: root),
            bootstrapLoader: { throw APIError.invalidResponse },
            memoryFavoriteUpdater: { _, _, _ in
                try await Task.sleep(nanoseconds: 5_000_000_000)
                throw APIError.invalidResponse
            }
        )
        let model = MemoryViewModel(
            repository: repository,
            scope: CacheScope(userID: "user-1", familyID: "family-1"),
            seed: FamilyMemoriesResponse(memories: [original], revision: "seed")
        )
        let action = Task { @MainActor in await model.toggleFavorite(original) }

        await waitUntil { model.pendingIDs.contains(original.id) }
        model.cancelInFlightInteractions()
        await action.value

        XCTAssertEqual(model.memories.first, original)
        XCTAssertNil(model.errorMessage)
        XCTAssertFalse(model.pendingIDs.contains(original.id))
    }

    @MainActor
    func testCancelledCommentRollsBackWithoutError() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let original = makeMemory(id: "comment-cancel", body: "评论取消")
        let repository = AppRepository(
            cache: try DiskCache(rootURL: root),
            bootstrapLoader: { throw APIError.invalidResponse },
            memoryCommentCreator: { _, _, _ in
                try await Task.sleep(nanoseconds: 5_000_000_000)
                throw APIError.invalidResponse
            }
        )
        let model = MemoryViewModel(
            repository: repository,
            scope: CacheScope(userID: "user-1", familyID: "family-1"),
            seed: FamilyMemoriesResponse(memories: [original], revision: "seed")
        )
        let action = Task { @MainActor in _ = await model.addComment("取消评论", to: original) }

        await waitUntil { model.pendingIDs.contains(original.id) }
        model.cancelInFlightInteractions()
        await action.value

        XCTAssertEqual(model.memories.first, original)
        XCTAssertNil(model.errorMessage)
        XCTAssertFalse(model.pendingIDs.contains(original.id))
    }

    @MainActor
    func testCancelledDeleteKeepsMemoryWithoutError() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let original = makeMemory(id: "delete-cancel", body: "删除取消")
        let repository = AppRepository(
            cache: try DiskCache(rootURL: root),
            bootstrapLoader: { throw APIError.invalidResponse },
            memoryDeleter: { _, _ in
                try await Task.sleep(nanoseconds: 5_000_000_000)
                throw APIError.invalidResponse
            }
        )
        let model = MemoryViewModel(
            repository: repository,
            scope: CacheScope(userID: "user-1", familyID: "family-1"),
            seed: FamilyMemoriesResponse(memories: [original], revision: "seed")
        )
        let action = Task { @MainActor in _ = await model.delete(original) }

        await waitUntil { model.pendingIDs.contains(original.id) }
        model.cancelInFlightInteractions()
        await action.value

        XCTAssertEqual(model.memories.first, original)
        XCTAssertNil(model.errorMessage)
        XCTAssertFalse(model.pendingIDs.contains(original.id))
    }

    @MainActor
    func testLateFavoriteSuccessCannotOverwriteOrFinishANewerFavorite() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let original = makeMemory(id: "favorite-late", body: "收藏代次")
        let favorited = makeMemory(id: original.id, body: original.body, favoriteCount: 1, isFavorite: true)
        let calls = MemoryInteractionCallCounter()
        let firstResponse = IgnoringCancellationResponseGate<FamilyMemoryEnvelope>()
        let secondResponse = IgnoringCancellationResponseGate<FamilyMemoryEnvelope>()
        let repository = AppRepository(
            cache: try DiskCache(rootURL: root),
            bootstrapLoader: { throw APIError.invalidResponse },
            memoryFavoriteUpdater: { _, _, _ in
                if await calls.next() == 0 {
                    return await firstResponse.wait()
                }
                return await secondResponse.wait()
            }
        )
        let model = MemoryViewModel(
            repository: repository,
            scope: CacheScope(userID: "user-1", familyID: "family-1"),
            seed: FamilyMemoriesResponse(memories: [original], revision: "seed")
        )
        let firstAction = Task { @MainActor in await model.toggleFavorite(original) }

        await waitUntil { model.pendingIDs.contains(original.id) }
        await waitUntilResponse(firstResponse)
        model.cancelInFlightInteractions()
        XCTAssertEqual(model.memories.first, original)
        XCTAssertFalse(model.pendingIDs.contains(original.id))

        let secondAction = Task { @MainActor in await model.toggleFavorite(original) }
        await waitUntilResponse(secondResponse)
        await firstResponse.release(FamilyMemoryEnvelope(memory: favorited))
        await firstAction.value

        XCTAssertTrue(model.pendingIDs.contains(original.id))
        XCTAssertTrue(model.memories.first?.isFavorite == true)
        await secondResponse.release(FamilyMemoryEnvelope(memory: favorited))
        await secondAction.value
        XCTAssertEqual(model.memories.first, favorited)
        XCTAssertFalse(model.pendingIDs.contains(original.id))
        XCTAssertNil(model.errorMessage)
    }

    @MainActor
    func testLateCommentSuccessAfterCancellationIsDiscarded() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let original = makeMemory(id: "comment-late", body: "评论代次")
        let commented = makeMemory(id: original.id, body: original.body, comments: [
            MemoryComment(id: "late", authorUserID: "user-1", body: "迟到评论", createdAt: "2026-07-23T08:00:01Z")
        ])
        let response = IgnoringCancellationResponseGate<FamilyMemoryEnvelope>()
        let repository = AppRepository(
            cache: try DiskCache(rootURL: root),
            bootstrapLoader: { throw APIError.invalidResponse },
            memoryCommentCreator: { _, _, _ in await response.wait() }
        )
        let model = MemoryViewModel(
            repository: repository,
            scope: CacheScope(userID: "user-1", familyID: "family-1"),
            seed: FamilyMemoriesResponse(memories: [original], revision: "seed")
        )
        let action = Task { @MainActor in await model.addComment("迟到评论", to: original) }

        await waitUntilResponse(response)
        model.cancelInFlightInteractions()
        XCTAssertEqual(model.memories.first, original)
        XCTAssertFalse(model.pendingIDs.contains(original.id))
        await response.release(FamilyMemoryEnvelope(memory: commented))

        let didComment = await action.value
        XCTAssertFalse(didComment)
        XCTAssertEqual(model.memories.first, original)
        XCTAssertNil(model.errorMessage)
    }

    @MainActor
    func testLateDeleteSuccessAfterCancellationIsDiscarded() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let original = makeMemory(id: "delete-late", body: "删除代次")
        let response = IgnoringCancellationResponseGate<MemoryDeleteResponse>()
        let repository = AppRepository(
            cache: try DiskCache(rootURL: root),
            bootstrapLoader: { throw APIError.invalidResponse },
            memoryDeleter: { _, memoryID in await response.wait() }
        )
        let model = MemoryViewModel(
            repository: repository,
            scope: CacheScope(userID: "user-1", familyID: "family-1"),
            seed: FamilyMemoriesResponse(memories: [original], revision: "seed")
        )
        let action = Task { @MainActor in await model.delete(original) }

        await waitUntilResponse(response)
        model.cancelInFlightInteractions()
        await response.release(MemoryDeleteResponse(deleted: true, memoryID: original.id))

        let didDelete = await action.value
        XCTAssertFalse(didDelete)
        XCTAssertEqual(model.memories.first, original)
        XCTAssertFalse(model.pendingIDs.contains(original.id))
        XCTAssertNil(model.errorMessage)
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

    @MainActor
    func testCancelledMemoryUploadCannotCreateMemoryOrShowFailure() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let scope = CacheScope(userID: "user-1", familyID: "family-1")
        let recorder = CancelledMemoryPublishRecorder()
        let repository = AppRepository(
            cache: try DiskCache(rootURL: root),
            bootstrapLoader: { throw APIError.invalidResponse },
            memoryCreator: { _, request in
                await recorder.recordCreation(request)
                return FamilyMemoryEnvelope(memory: self.makeMemory(id: "unexpected", body: request.body))
            },
            memoryMediaBatchUploader: { _, media in
                await recorder.recordUploadStarted()
                try? await Task.sleep(nanoseconds: 80_000_000)
                return MemoryMediaBatchUploadResponse(assets: media.map { item in
                    MemoryUploadedAsset(
                        id: "asset-late",
                        contentType: item.contentType,
                        imageURL: "/assets/late",
                        mediaURL: nil,
                        mediaType: "image",
                        sizeBytes: item.data.count
                    )
                })
            }
        )
        let model = MemoryViewModel(repository: repository, scope: scope)
        let saveTask = Task { @MainActor in
            await model.save(
                existing: nil,
                body: "不应发布",
                happenedAt: Date(),
                locationName: "",
                people: [],
                retainedMediaIDs: [],
                newMedia: [memoryUpload(1)]
            )
        }
        for _ in 0..<100 {
            if await recorder.uploadStarted { break }
            try await Task.sleep(nanoseconds: 2_000_000)
        }

        saveTask.cancel()
        let outcome = await saveTask.value

        XCTAssertNil(outcome)
        XCTAssertFalse(model.isPublishing)
        XCTAssertEqual(model.publishPhase, .idle)
        XCTAssertNil(model.errorMessage)
        let creationCount = await recorder.creationCount
        XCTAssertEqual(creationCount, 0)
    }

    @MainActor
    func testCancelledMemorySaveCannotPublishLateCreateResponse() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let created = makeMemory(id: "late-created", body: "不应落入页面")
        let response = IgnoringCancellationResponseGate<FamilyMemoryEnvelope>()
        let repository = AppRepository(
            cache: try DiskCache(rootURL: root),
            bootstrapLoader: { throw APIError.invalidResponse },
            memoryCreator: { _, _ in await response.wait() },
            memoryMediaBatchUploader: { _, _ in throw APIError.invalidResponse }
        )
        let model = MemoryViewModel(repository: repository, scope: CacheScope(userID: "user-1", familyID: "family-1"))
        let saveTask = Task { @MainActor in
            await model.save(
                existing: nil,
                body: "不应落入页面",
                happenedAt: Date(),
                locationName: "",
                people: [],
                retainedMediaIDs: [],
                newMedia: []
            )
        }

        await waitUntilResponse(response)
        saveTask.cancel()
        await response.release(FamilyMemoryEnvelope(memory: created))
        let outcome = await saveTask.value

        XCTAssertNil(outcome)
        XCTAssertTrue(model.memories.isEmpty)
        XCTAssertFalse(model.isPublishing)
        XCTAssertEqual(model.publishPhase, .idle)
        XCTAssertNil(model.errorMessage)
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

    private func makeStagedMediaFile() throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("memory-presentation-test-\(UUID().uuidString)")
        try Data([1, 2, 3]).write(to: url, options: .atomic)
        return url
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

private actor CancelledMemoryPublishRecorder {
    private(set) var uploadStarted = false
    private(set) var creationCount = 0

    func recordUploadStarted() { uploadStarted = true }
    func recordCreation(_ request: MemoryDraftRequest) { creationCount += 1 }
}

private actor MemoryInteractionCallCounter {
    private var count = 0

    func next() -> Int {
        defer { count += 1 }
        return count
    }
}

private actor IgnoringCancellationResponseGate<Value: Sendable> {
    private var continuation: CheckedContinuation<Value, Never>?
    private(set) var isWaiting = false

    func wait() async -> Value {
        isWaiting = true
        return await withCheckedContinuation { continuation = $0 }
    }

    func release(_ value: Value) {
        continuation?.resume(returning: value)
        continuation = nil
    }
}

private func waitUntilResponse<Value: Sendable>(
    _ gate: IgnoringCancellationResponseGate<Value>,
    timeout: TimeInterval = 1
) async {
    let deadline = Date().addingTimeInterval(timeout)
    while !(await gate.isWaiting), Date() < deadline {
        try? await Task.sleep(nanoseconds: 10_000_000)
    }
    let isWaiting = await gate.isWaiting
    XCTAssertTrue(isWaiting, "Timed out waiting for memory response")
}

@MainActor
private func waitUntil(
    timeout: TimeInterval = 1,
    condition: @escaping @MainActor () -> Bool
) async {
    let deadline = Date().addingTimeInterval(timeout)
    while !condition(), Date() < deadline {
        try? await Task.sleep(nanoseconds: 10_000_000)
    }
    XCTAssertTrue(condition(), "Timed out waiting for memory state")
}
