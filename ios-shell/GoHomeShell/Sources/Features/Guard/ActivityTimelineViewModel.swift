import Foundation

@MainActor
final class ActivityTimelineViewModel: ObservableObject {
    @Published private(set) var state = Loadable<ActivityTimelineResponse>()

    private let repository: AppRepository?
    private let scope: CacheScope?
    private var loadTask: Task<Void, Never>?
    private var hasStarted = false

    init(repository: AppRepository?, scope: CacheScope?) {
        self.repository = repository
        self.scope = scope
    }

    func start() {
        guard !hasStarted else { return }
        hasStarted = true
        refresh()
    }

    func refresh() {
        guard let repository, let scope else { return }
        loadTask?.cancel()
        let date = Self.todayKey()
        loadTask = Task { [repository, scope] in
            await repository.activityTimeline(scope: scope, date: date) { next in
                await MainActor.run { self.state = next }
            }
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

    deinit { loadTask?.cancel() }
}
