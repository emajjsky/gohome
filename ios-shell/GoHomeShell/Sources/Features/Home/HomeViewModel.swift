import Foundation

struct HomeCalendarDay: Equatable, Identifiable {
    let date: Date
    let weekday: String
    let day: String
    let isToday: Bool

    var id: Date { date }
}

struct HomeMapPoint: Equatable {
    let latitude: Double
    let longitude: Double
}

enum HomeDistanceState: Equatable {
    case value(kilometers: Double, travelMinutes: Int?, user: HomeMapPoint?, home: HomeMapPoint?)
    case permissionRequired
    case homeRequired
}

enum HomePresentation {
    static func contextualTopic(_ home: HomeResponse?) -> HomeTopicSuggestion {
        if let event = home?.calendar.first {
            return HomeTopicSuggestion(
                title: "聊聊接下来的安排",
                body: event.title,
                topics: ["时间安排", "一起吃饭", "最近想做的事"],
                message: "看到接下来有“\(event.title)”，你们那天怎么安排？我也想听听。"
            )
        }
        if let weather = home?.weather, let text = weatherText(weather) {
            return HomeTopicSuggestion(
                title: "从今天的天气聊起",
                body: text,
                topics: ["出门走走", "今天吃什么", "最近睡得好吗"],
                message: "今天\(weather.city)是\(weather.condition)，你们那边体感怎么样？"
            )
        }
        return HomeTopicSuggestion(
            title: "今天想聊点什么",
            body: "一句自然的问候就够了",
            topics: ["今天吃什么", "最近在看什么", "周末安排"],
            message: "今天过得怎么样？最近有没有什么新鲜事想和我说说？"
        )
    }

    static func calendarDays(reference: Date, calendar: Calendar = .current) -> [HomeCalendarDay] {
        let start = calendar.startOfDay(for: reference)
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.dateFormat = "E"

        return (0..<7).compactMap { offset in
            guard let date = calendar.date(byAdding: .day, value: offset, to: start) else { return nil }
            return HomeCalendarDay(
                date: date,
                weekday: formatter.string(from: date).replacingOccurrences(of: "星期", with: "周"),
                day: String(calendar.component(.day, from: date)),
                isToday: calendar.isDate(date, inSameDayAs: reference)
            )
        }
    }

    static func weatherText(_ weather: HomeWeather?) -> String? {
        guard let weather else { return nil }
        let city = weather.city.trimmingCharacters(in: .whitespacesAndNewlines)
        let condition = weather.condition.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !city.isEmpty || !condition.isEmpty else { return nil }
        let temperature = weather.temperature.formatted(.number.precision(.fractionLength(0)))
        return [city, condition, "\(temperature)°"].filter { !$0.isEmpty }.joined(separator: " · ")
    }

    static func distanceState(_ distance: HomeDistance?) -> HomeDistanceState {
        guard let distance, distance.meters >= 0 else { return .permissionRequired }
        let user = point(latitude: distance.userLatitude, longitude: distance.userLongitude)
        let home = point(latitude: distance.homeLatitude, longitude: distance.homeLongitude)
        return .value(
            kilometers: distance.meters / 1_000,
            travelMinutes: distance.travelMinutes,
            user: user,
            home: home
        )
    }

    static func activeAlert(_ alert: HomeCriticalAlert?) -> HomeCriticalAlert? {
        guard let alert, !alert.acknowledged else { return nil }
        return alert
    }

    private static func point(latitude: Double?, longitude: Double?) -> HomeMapPoint? {
        guard let latitude, let longitude, (-90...90).contains(latitude), (-180...180).contains(longitude) else { return nil }
        return HomeMapPoint(latitude: latitude, longitude: longitude)
    }
}

struct HomeTopicSuggestion: Equatable {
    let title: String
    let body: String
    let topics: [String]
    let message: String
}

@MainActor
final class HomeViewModel: ObservableObject {
    @Published private(set) var state = Loadable<HomeResponse>()
    @Published private(set) var careMessage: CareMessage?
    @Published private(set) var pendingCareAction: String?
    @Published private(set) var careActionError: String?

    private let repository: AppRepository?
    private let scope: CacheScope?
    private var loadTask: Task<Void, Never>?
    private var loadGeneration = 0
    private var reconciliationTask: Task<Void, Never>?
    private var careActionCancellation: (() -> Void)?
    private var careActionGeneration = 0
    private var activeCareActionGeneration: Int?
    private var hasStarted = false

    init(repository: AppRepository?, scope: CacheScope?, seed: HomeResponse? = nil) {
        self.repository = repository
        self.scope = scope
        state = Loadable(value: seed, isRefreshing: false, staleReason: nil)
        careMessage = seed?.careMessage
    }

    func start() {
        guard let repository, let scope else { return }
        if hasStarted {
            guard loadTask == nil else { return }
        } else {
            hasStarted = true
        }
        refresh(repository: repository, scope: scope)
    }

    func refresh() {
        guard let repository, let scope else { return }
        refresh(repository: repository, scope: scope)
    }

    func reconcileDeviceConfiguration() {
        refresh()
        reconciliationTask?.cancel()
        reconciliationTask = Task { [weak self] in
            for delay in [1, 2, 3, 5, 8] {
                do {
                    try await Task.sleep(nanoseconds: UInt64(delay) * 1_000_000_000)
                } catch {
                    return
                }
                guard !Task.isCancelled else { return }
                self?.refresh()
            }
        }
    }

    private func refresh(repository: AppRepository, scope: CacheScope) {
        loadTask?.cancel()
        loadGeneration += 1
        let generation = loadGeneration
        let task = Task { @MainActor [weak self, repository, scope, generation] in
            await repository.home(scope: scope) { [weak self] next in
                guard !Task.isCancelled else { return }
                await self?.applyLoadedState(next, generation: generation)
            }
            guard let self, self.loadGeneration == generation else { return }
            self.loadTask = nil
        }
        loadTask = task
    }

    private func applyLoadedState(_ next: Loadable<HomeResponse>, generation: Int) {
        guard loadGeneration == generation else { return }
        var nextState = next
        if nextState.value == nil, let currentValue = state.value {
            nextState.value = currentValue
        }
        state = nextState
        if pendingCareAction == nil { careMessage = nextState.value?.careMessage }
    }

    func cancelInFlightLoad() {
        loadGeneration += 1
        loadTask?.cancel()
        loadTask = nil
        state.isRefreshing = false
    }

    func recordCareAction(type: String, payload: [String: String] = [:]) async -> Bool {
        guard pendingCareAction == nil, let repository, let scope, let message = careMessage else { return false }
        pendingCareAction = type
        careActionError = nil
        careActionGeneration += 1
        let generation = careActionGeneration
        activeCareActionGeneration = generation
        let request = CareMessageActionRequest(
            actionType: type,
            payload: payload,
            idempotencyKey: "ios-\(message.messageID)-\(type)-\(UUID().uuidString.lowercased())"
        )
        let task = Task { @MainActor [weak self, repository, scope, message, generation] in
            guard let self else { return false }
            defer {
                self.finishCareAction(generation: generation)
            }
            do {
                let response = try await repository.recordMessageAction(
                    familyID: scope.familyID,
                    messageID: message.messageID,
                    request: request
                )
                try Task.checkCancellation()
                guard self.activeCareActionGeneration == generation else { return false }
                if ["closed", "dismissed"].contains(response.message.status) || type == "snoozed" {
                    self.careMessage = nil
                } else {
                    self.careMessage = response.message
                }
                return true
            } catch is CancellationError {
                return false
            } catch {
                guard self.activeCareActionGeneration == generation, !Task.isCancelled else { return false }
                self.careActionError = "操作没有保存，请稍后重试"
                return false
            }
        }
        careActionCancellation = { task.cancel() }
        return await task.value
    }

    func cancelInFlightCareAction() {
        guard activeCareActionGeneration != nil else { return }
        careActionGeneration += 1
        activeCareActionGeneration = nil
        careActionCancellation?()
        careActionCancellation = nil
        pendingCareAction = nil
    }

    func clearCareActionError() {
        careActionError = nil
    }

    private func finishCareAction(generation: Int) {
        guard activeCareActionGeneration == generation else { return }
        activeCareActionGeneration = nil
        careActionCancellation = nil
        pendingCareAction = nil
    }

    deinit {
        loadTask?.cancel()
        reconciliationTask?.cancel()
        careActionCancellation?()
    }
}
