import XCTest
@testable import GoHomeShell

final class HomeViewModelTests: XCTestCase {
    func testHomeDecodesCareMessageAndRemainsCompatibleWhenItIsAbsent() throws {
        let withCare = try decodeHome(careFragment: """
        ,"care_message":{
          "message_id":"message-1","message_type":"return_home","title":"聊聊周末","subtitle":"联系建议",
          "body":"最近天气不错。","facts":[],"actions":[{"key":"shared","label":"分享"}],"status":"open",
          "metadata":{"trigger_reason":"days_since_last_visit","topics":["周末安排"],"message_variants":["周末有空一起吃饭吗？"],"snoozed_until":null},
          "created_at":"2026-07-23T08:00:00Z","updated_at":null
        }
        """)
        XCTAssertEqual(withCare.careMessage?.messageID, "message-1")
        XCTAssertEqual(withCare.careMessage?.metadata.topics, ["周末安排"])
        XCTAssertEqual(withCare.careMessage?.actions.first?.type, "shared")

        XCTAssertNil(try decodeHome().careMessage)
    }

    @MainActor
    func testContactedActionRemovesCareMessageWithoutReloadingHome() async throws {
        let fixture = try HomeCareFixture(actionResult: .success("closed"))
        let model = HomeViewModel(repository: fixture.repository, scope: fixture.scope)
        model.start()
        try await waitUntil { model.careMessage != nil }

        let succeeded = await model.recordCareAction(type: "contacted", payload: ["selected_text": "周末聊聊"])
        let callCount = await fixture.calls.value
        XCTAssertTrue(succeeded)
        XCTAssertNil(model.careMessage)
        XCTAssertNil(model.careActionError)
        XCTAssertEqual(callCount, 1)
    }

    @MainActor
    func testFailedCareActionPreservesMessageAndShowsContextualError() async throws {
        let fixture = try HomeCareFixture(actionResult: .failure(APIError.invalidResponse))
        let model = HomeViewModel(repository: fixture.repository, scope: fixture.scope)
        model.start()
        try await waitUntil { model.careMessage != nil }

        let succeeded = await model.recordCareAction(type: "dismissed")
        XCTAssertFalse(succeeded)
        XCTAssertEqual(model.careMessage?.messageID, "message-1")
        XCTAssertEqual(model.careActionError, "操作没有保存，请稍后重试")
    }

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

    private func decodeHome(careFragment: String = "") throws -> HomeResponse {
        let data = Data("""
        {"family":null,"weather":null,"calendar":[],"distance":null,"critical_alert":null,
         "articles":[],"cameras":[],"revision":"r1"\(careFragment)}
        """.utf8)
        return try JSONDecoder().decode(HomeResponse.self, from: data)
    }
}

private struct HomeCareFixture {
    let scope = CacheScope(userID: "user-1", familyID: "family-1")
    let repository: AppRepository
    let calls = CareActionCounter()

    init(actionResult: Result<String, Error>) throws {
        let cache = try DiskCache(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString))
        let home = try JSONDecoder().decode(HomeResponse.self, from: Data("""
        {"family":null,"weather":null,"calendar":[],"distance":null,"critical_alert":null,
         "care_message":{"message_id":"message-1","message_type":"return_home","title":"聊聊周末","subtitle":"联系建议",
         "body":"最近天气不错。","facts":[],"actions":[],"status":"open",
         "metadata":{"trigger_reason":"days_since_last_visit","topics":["周末安排"],"message_variants":["周末有空一起吃饭吗？"],"snoozed_until":null},
         "created_at":"2026-07-23T08:00:00Z","updated_at":null},"articles":[],"cameras":[],"revision":"r1"}
        """.utf8))
        let calls = self.calls
        repository = AppRepository(
            cache: cache,
            bootstrapLoader: { throw APIError.invalidResponse },
            homeLoader: { _ in home },
            messageActionLoader: { _, _, _ in
                await calls.increment()
                let status = try actionResult.get()
                let responseData = Data("""
                {"message":{"message_id":"message-1","message_type":"return_home","title":"聊聊周末","subtitle":"联系建议",
                "body":"最近天气不错。","facts":[],"actions":[],"status":"\(status)",
                "metadata":{"trigger_reason":"days_since_last_visit","topics":["周末安排"],"message_variants":["周末有空一起吃饭吗？"],"snoozed_until":null},
                "created_at":"2026-07-23T08:00:00Z","updated_at":null}}
                """.utf8)
                return try JSONDecoder().decode(CareMessageActionResponse.self, from: responseData)
            }
        )
    }
}

private actor CareActionCounter {
    private(set) var value = 0
    func increment() { value += 1 }
}

@MainActor
private func waitUntil(
    timeout: TimeInterval = 1,
    condition: @escaping @MainActor () -> Bool
) async throws {
    let deadline = Date().addingTimeInterval(timeout)
    while !condition() {
        if Date() >= deadline { throw APIError.invalidResponse }
        try await Task.sleep(nanoseconds: 10_000_000)
    }
}
