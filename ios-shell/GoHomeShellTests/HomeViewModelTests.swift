import XCTest
@testable import GoHomeShell

final class HomeViewModelTests: XCTestCase {
    func testWeatherFormattingUsesOnlyServerValues() {
        XCTAssertEqual(
            HomePresentation.weatherText(HomeWeather(city: "上海", temperature: 28, condition: "晴")),
            "上海 · 晴 · 28°"
        )
        XCTAssertNil(HomePresentation.weatherText(nil))
    }

    func testCalendarAlwaysBuildsSevenDaysFromReferenceDate() throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "Asia/Shanghai"))
        let reference = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-07-22T04:00:00Z"))
        let days = HomePresentation.calendarDays(reference: reference, calendar: calendar)

        XCTAssertEqual(days.count, 7)
        XCTAssertEqual(days.first?.day, "22")
        XCTAssertEqual(days.filter(\.isToday).count, 1)
    }

    func testDistanceNeverInventsAValue() {
        XCTAssertEqual(HomePresentation.distanceState(nil), .permissionRequired)
        XCTAssertEqual(
            HomePresentation.distanceState(HomeDistance(meters: 12_800, travelMinutes: 35)),
            .value(kilometers: 12.8, travelMinutes: 35, user: nil, home: nil)
        )
    }

    func testAcknowledgedCriticalAlertIsHidden() {
        XCTAssertNil(HomePresentation.activeAlert(HomeCriticalAlert(id: "1", title: "已处理", level: "critical", acknowledged: true)))
        XCTAssertNotNil(HomePresentation.activeAlert(HomeCriticalAlert(id: "2", title: "待处理", level: "critical", acknowledged: false)))
    }
}
