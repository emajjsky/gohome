import Foundation

@MainActor
final class MemoryViewModel: ObservableObject {
    @Published private(set) var state = Loadable<FamilyMemoriesResponse>()
    @Published private(set) var pendingIDs: Set<String> = []
    @Published private(set) var isPublishing = false
    @Published var errorMessage: String?

    private let repository: AppRepository?
    private let scope: CacheScope?
    private var loadTask: Task<Void, Never>?
    private var hasStarted = false

    init(repository: AppRepository?, scope: CacheScope?) {
        self.repository = repository
        self.scope = scope
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
        newImages: [(data: Data, contentType: String)]
    ) async -> Bool {
        guard !isPublishing, let repository, let scope else { return false }
        isPublishing = true
        errorMessage = nil
        do {
            var assetIDs = retainedMediaIDs
            for image in newImages {
                let uploaded = try await repository.uploadMemoryMedia(
                    familyID: scope.familyID,
                    data: image.data,
                    contentType: image.contentType
                )
                assetIDs.append(uploaded.id)
            }
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
            isPublishing = false
            return true
        } catch {
            isPublishing = false
            errorMessage = "这条记忆没有保存，请检查网络后重试"
            return false
        }
    }

    func toggleFavorite(_ memory: FamilyMemory) async {
        guard let repository, let scope, !pendingIDs.contains(memory.id) else { return }
        pendingIDs.insert(memory.id)
        do {
            let updated = try await repository.setMemoryFavorite(
                familyID: scope.familyID,
                memoryID: memory.id,
                favorite: !memory.isFavorite
            )
            replace(updated)
            await persist()
        } catch {
            errorMessage = "收藏状态没有保存"
        }
        pendingIDs.remove(memory.id)
    }

    func addComment(_ body: String, to memory: FamilyMemory) async -> Bool {
        guard let repository, let scope, !pendingIDs.contains(memory.id) else { return false }
        pendingIDs.insert(memory.id)
        defer { pendingIDs.remove(memory.id) }
        do {
            let updated = try await repository.addMemoryComment(familyID: scope.familyID, memoryID: memory.id, body: body)
            replace(updated)
            await persist()
            return true
        } catch {
            errorMessage = "评论没有发布"
            return false
        }
    }

    func delete(_ memory: FamilyMemory) async -> Bool {
        guard let repository, let scope, !pendingIDs.contains(memory.id) else { return false }
        pendingIDs.insert(memory.id)
        do {
            try await repository.deleteMemory(familyID: scope.familyID, memoryID: memory.id)
            var value = currentResponse()
            value = FamilyMemoriesResponse(memories: value.memories.filter { $0.id != memory.id }, revision: UUID().uuidString)
            state.value = value
            await repository.cacheMemories(value, scope: scope)
            pendingIDs.remove(memory.id)
            return true
        } catch {
            pendingIDs.remove(memory.id)
            errorMessage = "删除失败，请稍后重试"
            return false
        }
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

    deinit { loadTask?.cancel() }
}
