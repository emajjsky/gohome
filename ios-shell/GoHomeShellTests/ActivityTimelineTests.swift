import XCTest
@testable import GoHomeShell

final class ActivityTimelineTests: XCTestCase {
    func testActivityTimelineDecodesOnlyFactualIntervalFields() throws {
        let value = try JSONDecoder().decode(ActivityTimelineResponse.self, from: Data(#"{"date":"2026-07-23","intervals":[{"id":"activity-1","camera_id":"2","room":"客厅","started_at":"2026-07-23T01:00:00Z","ended_at":"2026-07-23T01:08:00Z","person_count_max":1,"postures":["standing","sitting"],"confidence":0.88}],"revision":"r1"}"#.utf8))

        XCTAssertEqual(value.intervals.first?.room, "客厅")
        XCTAssertEqual(value.intervals.first?.postures, ["standing", "sitting"])
        XCTAssertEqual(value.intervals.first?.confidence, 0.88)
    }

    func testActivityTimelineCacheIsDeliveredBeforeRefresh() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let cache = try DiskCache(rootURL: root)
        let scope = CacheScope(userID: "user-1", familyID: "family-1")
        let date = "2026-07-23"
        let cached = ActivityTimelineResponse(date: date, intervals: [], revision: "cached")
        let fresh = ActivityTimelineResponse(date: date, intervals: [], revision: "fresh")
        try await cache.write(cached, key: "activity-timeline-\(date)", scope: scope)
        let repository = AppRepository(
            cache: cache,
            bootstrapLoader: { throw APIError.invalidResponse },
            activityTimelineLoader: { _, _ in fresh }
        )
        let recorder = ActivityTimelineStateRecorder()

        await repository.activityTimeline(scope: scope, date: date) { await recorder.append($0) }

        let states = await recorder.values
        XCTAssertEqual(states.map(\.value?.revision), ["cached", "fresh"])
        XCTAssertTrue(states.first?.isRefreshing == true)
        XCTAssertTrue(states.last?.isRefreshing == false)
    }

    func testActivityOverviewDecodesFactualDailyAndWeeklyMetrics() throws {
        let data = Data(#"{"date":"2026-07-25","today":{"date":"2026-07-25","has_data":true,"active_minutes":20,"interval_count":2,"person_count_max":1,"first_activity_at":"2026-07-25T01:00:00Z","last_activity_at":"2026-07-25T01:20:00Z","observed_postures":["standing"],"rooms":[{"room":"客厅","active_minutes":20,"interval_count":2}]},"seven_day_trend":[],"baseline":{"comparable_days":2,"average_active_minutes":35},"facts":["今日记录 20 分钟可验证活动"],"revision":"overview-r1"}"#.utf8)
        let value = try JSONDecoder().decode(ActivityOverviewResponse.self, from: data)

        XCTAssertEqual(value.today.activeMinutes, 20)
        XCTAssertEqual(value.today.rooms.first?.room, "客厅")
        XCTAssertEqual(value.baseline.averageActiveMinutes, 35)
        XCTAssertFalse(String(data: data, encoding: .utf8)?.contains("吃饭") == true)
    }

    func testActivityOverviewCacheIsDeliveredBeforeRefresh() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let cache = try DiskCache(rootURL: root)
        let scope = CacheScope(userID: "user-1", familyID: "family-1")
        let date = "2026-07-25"
        let day = ActivityDaySummary(
            date: date, hasData: false, activeMinutes: 0, intervalCount: 0, personCountMax: 0,
            firstActivityAt: nil, lastActivityAt: nil, observedPostures: [], rooms: []
        )
        let cached = ActivityOverviewResponse(
            date: date, today: day, sevenDayTrend: [],
            baseline: ActivityBaseline(comparableDays: 0, averageActiveMinutes: nil), facts: [], revision: "cached"
        )
        let fresh = ActivityOverviewResponse(
            date: date, today: day, sevenDayTrend: [],
            baseline: ActivityBaseline(comparableDays: 0, averageActiveMinutes: nil), facts: [], revision: "fresh"
        )
        try await cache.write(cached, key: "activity-overview-\(date)", scope: scope)
        let repository = AppRepository(
            cache: cache,
            bootstrapLoader: { throw APIError.invalidResponse },
            activityOverviewLoader: { _, _ in fresh }
        )
        let recorder = ActivityOverviewStateRecorder()

        await repository.activityOverview(scope: scope, date: date) { await recorder.append($0) }

        let states = await recorder.values
        XCTAssertEqual(states.map(\.value?.revision), ["cached", "fresh"])
        XCTAssertTrue(states.first?.isRefreshing == true)
        XCTAssertTrue(states.last?.isRefreshing == false)
    }

    func testCarePreferencesPreserveActivityHistorySettingsInPatch() throws {
        let preferences = try JSONDecoder().decode(
            CarePreferences.self,
            from: Data(#"{"family_id":"family-1","metadata":{"activity_history":{"tracking_enabled":false,"daily_summary_enabled":true,"weekly_report_enabled":false,"anomaly_reminders_enabled":true,"multimodal_review_enabled":true,"retention_days":14}}}"#.utf8)
        )

        XCTAssertFalse(preferences.metadata.activityHistory.trackingEnabled)
        XCTAssertEqual(preferences.metadata.activityHistory.retentionDays, 14)
        let encoded = try JSONEncoder().encode(preferences.editablePayload)
        XCTAssertTrue(String(data: encoded, encoding: .utf8)?.contains("activity_history") == true)
    }

    func testActivityHistorySettingsRemainCompatibleWithPartialServerMetadata() throws {
        let preferences = try JSONDecoder().decode(
            CarePreferences.self,
            from: Data(#"{"family_id":"family-1","metadata":{"activity_history":{"tracking_enabled":false,"retention_days":14}}}"#.utf8)
        )

        let settings = preferences.metadata.activityHistory
        XCTAssertFalse(settings.trackingEnabled)
        XCTAssertEqual(settings.retentionDays, 14)
        XCTAssertTrue(settings.dailySummaryEnabled)
        XCTAssertTrue(settings.weeklyReportEnabled)
    }

    @MainActor
    func testCancelledHistoryClearKeepsTimelineWithoutError() async throws {
        let cache = try DiskCache(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString))
        let scope = CacheScope(userID: "user-1", familyID: "family-1")
        let interval = ActivityInterval(
            id: "activity-1",
            cameraID: "camera-1",
            room: "客厅",
            startedAt: "2026-07-23T01:00:00Z",
            endedAt: "2026-07-23T01:08:00Z",
            personCountMax: 1,
            postures: ["standing"],
            confidence: 0.9
        )
        let response = ActivityTimelineResponse(date: "2026-07-23", intervals: [interval], revision: "seed")
        let repository = AppRepository(
            cache: cache,
            bootstrapLoader: { throw APIError.invalidResponse },
            activityHistoryDeleter: { _ in
                try await Task.sleep(nanoseconds: 5_000_000_000)
                throw APIError.invalidResponse
            }
        )
        let model = ActivityTimelineViewModel(repository: repository, scope: scope, canManageHistory: true, seed: response)

        model.clearHistory()
        while !model.clearingHistory {
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        model.cancelInFlightClear()
        try await Task.sleep(nanoseconds: 20_000_000)

        XCTAssertEqual(model.state.value, response)
        XCTAssertFalse(model.clearingHistory)
        XCTAssertNil(model.actionError)
    }

    @MainActor
    func testLateSuccessfulHistoryClearCannotCommitAfterCancellation() async throws {
        let cache = try DiskCache(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString))
        let scope = CacheScope(userID: "user-1", familyID: "family-1")
        let interval = ActivityInterval(
            id: "activity-1",
            cameraID: "camera-1",
            room: "客厅",
            startedAt: "2026-07-23T01:00:00Z",
            endedAt: "2026-07-23T01:08:00Z",
            personCountMax: 1,
            postures: ["standing"],
            confidence: 0.9
        )
        let response = ActivityTimelineResponse(date: "2026-07-23", intervals: [interval], revision: "seed")
        let repository = AppRepository(
            cache: cache,
            bootstrapLoader: { throw APIError.invalidResponse },
            activityHistoryDeleter: { _ in
                try? await Task.sleep(nanoseconds: 100_000_000)
                return ActivityHistoryDeleteResponse(deleted: 1)
            }
        )
        let model = ActivityTimelineViewModel(repository: repository, scope: scope, canManageHistory: true, seed: response)

        model.clearHistory()
        while !model.clearingHistory {
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        model.cancelInFlightClear()
        try await Task.sleep(nanoseconds: 150_000_000)

        XCTAssertEqual(model.state.value, response)
        XCTAssertFalse(model.clearingHistory)
        XCTAssertNil(model.actionError)
    }
}

private actor ActivityTimelineStateRecorder {
    private(set) var values: [Loadable<ActivityTimelineResponse>] = []
    func append(_ value: Loadable<ActivityTimelineResponse>) { values.append(value) }
}

private actor ActivityOverviewStateRecorder {
    private(set) var values: [Loadable<ActivityOverviewResponse>] = []
    func append(_ value: Loadable<ActivityOverviewResponse>) { values.append(value) }
}
