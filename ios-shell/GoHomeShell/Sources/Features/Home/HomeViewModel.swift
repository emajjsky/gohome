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
}

enum HomePresentation {
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

@MainActor
final class HomeViewModel: ObservableObject {
    @Published private(set) var state = Loadable<HomeResponse>()

    private let repository: AppRepository?
    private let scope: CacheScope?
    private var loadTask: Task<Void, Never>?
    private var hasStarted = false

    init(repository: AppRepository?, scope: CacheScope?) {
        self.repository = repository
        self.scope = scope
    }

    func start() {
        guard !hasStarted, let repository, let scope else { return }
        hasStarted = true
        loadTask = Task { [repository, scope] in
            await repository.home(scope: scope) { next in
                await MainActor.run { self.state = next }
            }
        }
    }

    deinit { loadTask?.cancel() }
}
