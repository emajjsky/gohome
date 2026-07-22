import Foundation

@MainActor
final class EventsViewModel: ObservableObject {
    @Published private(set) var state = Loadable<[AppEvent]>()
    @Published var segment: EventSegment = .pending
    @Published private(set) var details: [String: AppEvent] = [:]
    @Published private(set) var pendingActions: Set<String> = []
    @Published private(set) var actionErrors: [String: String] = [:]

    private let repository: AppRepository?
    private let scope: CacheScope?
    private var loadTask: Task<Void, Never>?
    private var detailTasks: [String: Task<Void, Never>] = [:]
    private var hasStarted = false

    init(repository: AppRepository?, scope: CacheScope?, seedEvents: [AppEvent] = []) {
        self.repository = repository
        self.scope = scope
        if !seedEvents.isEmpty {
            state = Loadable(value: seedEvents, isRefreshing: false, staleReason: nil)
        }
    }

    var groups: [EventGroup] {
        EventPresentation.groups(state.value ?? [], segment: segment)
    }

    var pendingCount: Int {
        (state.value ?? []).filter { EventPresentation.segment($0) == .pending }.count
    }

    func start() {
        guard !hasStarted else { return }
        hasStarted = true
        refresh()
    }

    func refresh() {
        guard let repository, let scope else { return }
        loadTask?.cancel()
        loadTask = Task { [repository, scope] in
            await repository.events(scope: scope) { next in
                await MainActor.run {
                    self.state = self.mergingPendingActions(into: next)
                }
            }
        }
    }

    func event(id: String, fallback: AppEvent) -> AppEvent {
        details[id] ?? (state.value ?? []).first(where: { $0.id == id }) ?? fallback
    }

    func loadDetail(id: String) {
        guard details[id] == nil, detailTasks[id] == nil, let repository else { return }
        detailTasks[id] = Task { [repository] in
            defer { detailTasks[id] = nil }
            do {
                let event = try await repository.fetchEvent(id)
                guard !Task.isCancelled else { return }
                details[id] = event
                replace(event)
            } catch is CancellationError {
                return
            } catch {
                guard details[id] == nil else { return }
                actionErrors[id] = "详情暂时无法更新，当前显示已缓存内容"
            }
        }
    }

    func resolve(_ eventID: String, as resolution: String) {
        guard !pendingActions.contains(eventID) else { return }
        guard let original = event(id: eventID) else { return }
        if original.acknowledged && original.resolution == resolution { return }

        let optimistic = resolvedCopy(original, resolution: resolution)
        pendingActions.insert(eventID)
        actionErrors[eventID] = nil
        replace(optimistic)
        details[eventID] = optimistic
        persistCurrentEvents()

        guard let repository else {
            pendingActions.remove(eventID)
            return
        }
        Task { [repository] in
            do {
                let updated = try await repository.updateEvent(original, resolution: resolution)
                replace(updated)
                details[eventID] = updated
                persistCurrentEvents()
            } catch is CancellationError {
                replace(original)
                details[eventID] = original
            } catch {
                replace(original)
                details[eventID] = original
                actionErrors[eventID] = "未能保存处理结果，请重试"
                persistCurrentEvents()
            }
            pendingActions.remove(eventID)
        }
    }

    func clearError(for eventID: String) {
        actionErrors[eventID] = nil
    }

    private func event(id: String) -> AppEvent? {
        details[id] ?? state.value?.first(where: { $0.id == id })
    }

    private func replace(_ event: AppEvent) {
        var events = state.value ?? []
        if let index = events.firstIndex(where: { $0.id == event.id }) {
            events[index] = event
        } else {
            events.insert(event, at: 0)
        }
        state.value = events
    }

    private func persistCurrentEvents() {
        guard let repository, let scope, let events = state.value else { return }
        Task { await repository.cacheEvents(events, scope: scope) }
    }

    private func mergingPendingActions(into next: Loadable<[AppEvent]>) -> Loadable<[AppEvent]> {
        guard !pendingActions.isEmpty, var incoming = next.value else { return next }
        let local = state.value ?? []
        for id in pendingActions {
            guard let pending = local.first(where: { $0.id == id }) else { continue }
            if let index = incoming.firstIndex(where: { $0.id == id }) {
                incoming[index] = pending
            }
        }
        return Loadable(value: incoming, isRefreshing: next.isRefreshing, staleReason: next.staleReason)
    }

    private func resolvedCopy(_ event: AppEvent, resolution: String) -> AppEvent {
        AppEvent(
            id: event.id,
            type: event.type,
            level: event.level,
            summary: event.summary,
            room: event.room,
            cameraID: event.cameraID,
            cameraName: event.cameraName,
            occurredAt: event.occurredAt,
            createdAt: event.createdAt,
            updatedAt: ISO8601DateFormatter().string(from: Date()),
            acknowledged: true,
            resolution: resolution,
            snapshotURL: event.snapshotURL,
            mediaAssetID: event.mediaAssetID,
            evidenceMedia: event.evidenceMedia,
            payload: event.payload
        )
    }

    deinit {
        loadTask?.cancel()
        detailTasks.values.forEach { $0.cancel() }
    }
}
