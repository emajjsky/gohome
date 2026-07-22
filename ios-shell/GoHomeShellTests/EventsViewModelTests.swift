import XCTest
@testable import GoHomeShell

final class EventsViewModelTests: XCTestCase {
    @MainActor
    func testRejectedActionRollsBackOptimisticState() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let cache = try DiskCache(rootURL: root)
        let original = fixtureEvent()
        let repository = AppRepository(
            cache: cache,
            bootstrapLoader: { throw APIError.invalidResponse },
            eventsLoader: { _ in [original] },
            eventActionLoader: { _, _ in
                try await Task.sleep(nanoseconds: 80_000_000)
                throw APIError.server(statusCode: 500, detail: "rejected")
            }
        )
        let model = EventsViewModel(
            repository: repository,
            scope: CacheScope(userID: "user", familyID: "family")
        )

        model.start()
        try await waitUntil { model.state.value?.count == 1 }
        model.resolve(original.id, as: "handled")
        XCTAssertEqual(model.state.value?.first?.resolution, "handled")
        XCTAssertTrue(model.pendingActions.contains(original.id))

        try await waitUntil { model.actionErrors[original.id] != nil }
        XCTAssertFalse(model.state.value?.first?.acknowledged ?? true)
        XCTAssertEqual(model.state.value?.first?.resolution, "")
        XCTAssertFalse(model.pendingActions.contains(original.id))
    }

    @MainActor
    private func waitUntil(
        timeout: TimeInterval = 2,
        condition: @escaping @MainActor () -> Bool
    ) async throws {
        let deadline = Date().addingTimeInterval(timeout)
        while !condition() {
            if Date() >= deadline { XCTFail("Timed out waiting for state"); return }
            try await Task.sleep(nanoseconds: 20_000_000)
        }
    }

    private func fixtureEvent() -> AppEvent {
        AppEvent(
            id: "event-1",
            type: "fall_candidate",
            level: "critical",
            room: "客厅",
            cameraID: "2",
            cameraName: "客厅摄像头",
            occurredAt: "2026-07-22T09:30:00+08:00",
            createdAt: "2026-07-22T09:30:00+08:00",
            updatedAt: "2026-07-22T09:30:00+08:00"
        )
    }
}
