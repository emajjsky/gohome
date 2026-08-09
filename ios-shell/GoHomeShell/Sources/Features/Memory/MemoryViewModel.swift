import Foundation

enum MemoryPublishPhase: Equatable, Sendable {
    case idle
    case uploading(itemCount: Int)
    case saving

    var toolbarTitle: String {
        switch self {
        case .idle: "发布"
        case .uploading: "上传中"
        case .saving: "保存中"
        }
    }

    var statusText: String {
        switch self {
        case .idle: ""
        case let .uploading(itemCount): itemCount == 1 ? "正在上传内容" : "正在上传 \(itemCount) 项内容"
        case .saving: "正在保存记忆"
        }
    }
}

@MainActor
final class MemoryViewModel: ObservableObject {
    struct SaveOutcome: Sendable {
        let memory: FamilyMemory
        let uploadedAssets: [MemoryUploadedAsset]
    }

    @Published private(set) var state = Loadable<FamilyMemoriesResponse>()
    @Published private(set) var pendingIDs: Set<String> = []
    @Published private(set) var isPublishing = false
    @Published private(set) var publishPhase: MemoryPublishPhase = .idle
    @Published var errorMessage: String?

    private let repository: AppRepository?
    private let scope: CacheScope?
    private var loadTask: Task<Void, Never>?
    private var interactionCancellations: [String: () -> Void] = [:]
    private var hasStarted = false

    init(repository: AppRepository?, scope: CacheScope?, seed: FamilyMemoriesResponse? = nil) {
        self.repository = repository
        self.scope = scope
        state = Loadable(value: seed, isRefreshing: false, staleReason: nil)
    }

    var memories: [FamilyMemory] { state.value?.memories ?? [] }

    func start() {
        guard !hasStarted, let repository, let scope else { return }
        hasStarted = true
        loadTask = Task { [repository, scope] in
            await repository.memories(scope: scope) { next in
                await MainActor.run { self.state = next }
            }
        }
    }

    func save(
        existing: FamilyMemory?,
        body: String,
        happenedAt: Date,
        locationName: String,
        people: [String],
        retainedMediaIDs: [String],
        newMedia: [MemoryUploadAsset]
    ) async -> SaveOutcome? {
        guard !isPublishing, let repository, let scope else { return nil }
        isPublishing = true
        publishPhase = .idle
        errorMessage = nil
        defer {
            isPublishing = false
            publishPhase = .idle
        }
        do {
            let retainedIDs = Array(retainedMediaIDs.prefix(9))
            let containsVideo = newMedia.contains(where: \.isVideo)
            guard !containsVideo || (newMedia.count == 1 && retainedIDs.isEmpty) else {
                throw APIError.invalidResponse
            }
            let uploadCandidates = containsVideo
                ? Array(newMedia.prefix(1))
                : Array(newMedia.prefix(max(0, 9 - retainedIDs.count)))
            let uploadedAssets: [MemoryUploadedAsset]
            if uploadCandidates.isEmpty {
                publishPhase = .saving
                uploadedAssets = []
            } else {
                publishPhase = .uploading(itemCount: uploadCandidates.count)
                uploadedAssets = try await repository.uploadMemoryMediaBatch(
                    familyID: scope.familyID,
                    media: uploadCandidates
                )
            }
            try Task.checkCancellation()
            publishPhase = .saving
            let assetIDs = retainedIDs + uploadedAssets.map(\.id)
            let request = MemoryDraftRequest(
                body: body.trimmingCharacters(in: .whitespacesAndNewlines),
                happenedAt: ISO8601DateFormatter().string(from: happenedAt),
                locationName: locationName.trimmingCharacters(in: .whitespacesAndNewlines),
                people: people,
                assetIDs: assetIDs
            )
            let saved = if let existing {
                try await repository.updateMemory(familyID: scope.familyID, memoryID: existing.id, request: request)
            } else {
                try await repository.createMemory(familyID: scope.familyID, request: request)
            }
            replace(saved, prependIfMissing: existing == nil)
            await persist()
            return SaveOutcome(memory: saved, uploadedAssets: uploadedAssets)
        } catch is CancellationError {
            return nil
        } catch {
            errorMessage = "这条记忆没有保存，请检查网络后重试"
            return nil
        }
    }

    func toggleFavorite(_ memory: FamilyMemory) async {
        guard let repository, let scope, !pendingIDs.contains(memory.id) else { return }
        let task = Task { @MainActor [weak self, repository, scope] in
            guard let self else { return }
            defer { self.finishInteraction(memory.id) }
            await self.performFavorite(memory, repository: repository, scope: scope)
        }
        interactionCancellations[memory.id] = { task.cancel() }
        await task.value
    }

    func addComment(_ body: String, to memory: FamilyMemory) async -> Bool {
        guard let repository, let scope, !pendingIDs.contains(memory.id) else { return false }
        let trimmedBody = body.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedBody.isEmpty else { return false }
        let task = Task { @MainActor [weak self, repository, scope] in
            guard let self else { return false }
            defer { self.finishInteraction(memory.id) }
            return await self.performComment(trimmedBody, to: memory, repository: repository, scope: scope)
        }
        interactionCancellations[memory.id] = { task.cancel() }
        return await task.value
    }

    func delete(_ memory: FamilyMemory) async -> Bool {
        guard let repository, let scope, !pendingIDs.contains(memory.id) else { return false }
        let task = Task { @MainActor [weak self, repository, scope] in
            guard let self else { return false }
            defer { self.finishInteraction(memory.id) }
            return await self.performDelete(memory, repository: repository, scope: scope)
        }
        interactionCancellations[memory.id] = { task.cancel() }
        return await task.value
    }

    func cancelInFlightInteractions() {
        interactionCancellations.values.forEach { $0() }
    }

    private func performFavorite(
        _ memory: FamilyMemory,
        repository: AppRepository,
        scope: CacheScope
    ) async {
        pendingIDs.insert(memory.id)
        let nextFavorite = !memory.isFavorite
        replace(memory.withInteractions(
            favoriteCount: max(0, memory.favoriteCount + (nextFavorite ? 1 : -1)),
            isFavorite: nextFavorite
        ))
        do {
            let updated = try await repository.setMemoryFavorite(
                familyID: scope.familyID,
                memoryID: memory.id,
                favorite: nextFavorite
            )
            try Task.checkCancellation()
            replace(updated)
            await persist()
            try Task.checkCancellation()
        } catch is CancellationError {
            replace(memory)
            await persist()
        } catch {
            replace(memory)
            errorMessage = "喜欢状态没有保存，请稍后重试"
        }
    }

    private func performComment(
        _ body: String,
        to memory: FamilyMemory,
        repository: AppRepository,
        scope: CacheScope
    ) async -> Bool {
        pendingIDs.insert(memory.id)
        let optimisticComment = MemoryComment(
            id: "local-\(UUID().uuidString)",
            authorUserID: scope.userID,
            body: body,
            createdAt: ISO8601DateFormatter().string(from: Date())
        )
        replace(memory.withInteractions(comments: memory.comments + [optimisticComment]))
        do {
            let updated = try await repository.addMemoryComment(
                familyID: scope.familyID,
                memoryID: memory.id,
                body: body
            )
            try Task.checkCancellation()
            replace(updated)
            await persist()
            try Task.checkCancellation()
            return true
        } catch is CancellationError {
            replace(memory)
            await persist()
            return false
        } catch {
            replace(memory)
            errorMessage = "评论没有发布，请稍后重试"
            return false
        }
    }

    private func performDelete(
        _ memory: FamilyMemory,
        repository: AppRepository,
        scope: CacheScope
    ) async -> Bool {
        pendingIDs.insert(memory.id)
        let original = currentResponse()
        do {
            try await repository.deleteMemory(familyID: scope.familyID, memoryID: memory.id)
            try Task.checkCancellation()
            var value = original
            value = FamilyMemoriesResponse(memories: value.memories.filter { $0.id != memory.id }, revision: UUID().uuidString)
            state.value = value
            await repository.cacheMemories(value, scope: scope)
            try Task.checkCancellation()
            return true
        } catch is CancellationError {
            state.value = original
            await repository.cacheMemories(original, scope: scope)
            return false
        } catch {
            errorMessage = "删除失败，请稍后重试"
            return false
        }
    }

    private func finishInteraction(_ memoryID: String) {
        interactionCancellations[memoryID] = nil
        pendingIDs.remove(memoryID)
    }

    private func replace(_ memory: FamilyMemory, prependIfMissing: Bool = false) {
        var items = memories
        if let index = items.firstIndex(where: { $0.id == memory.id }) {
            items[index] = memory
        } else if prependIfMissing {
            items.insert(memory, at: 0)
        }
        items.sort { ($0.happenedAt, $0.createdAt ?? "") > ($1.happenedAt, $1.createdAt ?? "") }
        state.value = FamilyMemoriesResponse(memories: items, revision: UUID().uuidString)
    }

    private func currentResponse() -> FamilyMemoriesResponse {
        state.value ?? FamilyMemoriesResponse(memories: [], revision: UUID().uuidString)
    }

    private func persist() async {
        guard let repository, let scope, let value = state.value else { return }
        await repository.cacheMemories(value, scope: scope)
    }

    deinit {
        loadTask?.cancel()
        interactionCancellations.values.forEach { $0() }
    }
}

private extension FamilyMemory {
    func withInteractions(
        comments: [MemoryComment]? = nil,
        favoriteCount: Int? = nil,
        isFavorite: Bool? = nil
    ) -> FamilyMemory {
        FamilyMemory(
            id: id,
            familyID: familyID,
            author: author,
            body: body,
            happenedAt: happenedAt,
            locationName: locationName,
            people: people,
            media: media,
            comments: comments ?? self.comments,
            favoriteCount: favoriteCount ?? self.favoriteCount,
            isFavorite: isFavorite ?? self.isFavorite,
            createdAt: createdAt,
            updatedAt: updatedAt
        )
    }
}
