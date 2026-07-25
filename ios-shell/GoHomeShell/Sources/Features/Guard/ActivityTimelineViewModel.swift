import Foundation

@MainActor
final class ActivityTimelineViewModel: ObservableObject {
    @Published private(set) var state = Loadable<ActivityTimelineResponse>()
    @Published private(set) var overviewState = Loadable<ActivityOverviewResponse>()
    @Published private(set) var clearingHistory = false
    @Published private(set) var actionError: String?

    private let repository: AppRepository?
    private let scope: CacheScope?
    let canManageHistory: Bool
    private var loadTask: Task<Void, Never>?
    private var overviewTask: Task<Void, Never>?
    private var hasStarted = false

    init(repository: AppRepository?, scope: CacheScope?, canManageHistory: Bool = false) {
        self.repository = repository
        self.scope = scope
        self.canManageHistory = canManageHistory
    }

    func start() {
        guard !hasStarted else { return }
        hasStarted = true
        refresh()
    }

    func refresh() {
        guard let repository, let scope else { return }
        loadTask?.cancel()
        overviewTask?.cancel()
        let date = Self.todayKey()
        loadTask = Task { [repository, scope] in
            await repository.activityTimeline(scope: scope, date: date) { next in
                await MainActor.run { self.state = next }
            }
        }
        overviewTask = Task { [repository, scope] in
            await repository.activityOverview(scope: scope, date: date) { next in
                await MainActor.run { self.overviewState = next }
            }
        }
    }

    func clearHistory() {
        guard canManageHistory, !clearingHistory, let repository, let scope else { return }
        clearingHistory = true
        actionError = nil
        let date = Self.todayKey()
        Task { [repository, scope] in
            do {
                _ = try await repository.deleteActivityHistory(scope: scope, date: date)
                state = Loadable(value: ActivityTimelineResponse(date: date, intervals: [], revision: "cleared"))
                overviewState = Loadable()
                refresh()
            } catch {
                actionError = "活动记录未能清空，请重试"
            }
            clearingHistory = false
        }
    }

    private static func todayKey() -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "Asia/Shanghai")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: Date())
    }

    deinit {
        loadTask?.cancel()
        overviewTask?.cancel()
    }
}
