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
}

private actor ActivityTimelineStateRecorder {
    private(set) var values: [Loadable<ActivityTimelineResponse>] = []
    func append(_ value: Loadable<ActivityTimelineResponse>) { values.append(value) }
}
