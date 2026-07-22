import XCTest
@testable import GoHomeShell

final class GuardViewModelTests: XCTestCase {
    @MainActor
    func testSelectingAnotherCameraStopsCurrentStreamBeforeStartingNext() async throws {
        let client = RecordingStreamClient()
        let model = GuardViewModel(streamClient: client)

        model.select(cameraID: "camera-a")
        try await waitUntil { await client.hasStarted(cameraID: "camera-a") }
        model.select(cameraID: "camera-b")
        try await waitUntil { await client.hasStarted(cameraID: "camera-b") }

        let events = await client.events
        let stopBeforeB = try XCTUnwrap(events.lastIndex(of: "stop"))
        let startB = try XCTUnwrap(events.lastIndex(of: "start:camera-b"))
        XCTAssertLessThan(stopBeforeB, startB)
        XCTAssertEqual(model.selectedCameraID, "camera-b")
    }

    @MainActor
    func testOnlySelectedCameraCanPublishFrames() async throws {
        let client = RecordingStreamClient()
        let model = GuardViewModel(streamClient: client)

        model.select(cameraID: "camera-a")
        try await waitUntil { await client.hasStarted(cameraID: "camera-a") }
        model.select(cameraID: "camera-b")
        try await waitUntil { await client.hasStarted(cameraID: "camera-b") }

        await client.yield(Data([0x01]), cameraID: "camera-a")
        await client.yield(Data([0x02]), cameraID: "camera-b")
        try await waitUntil { await MainActor.run { model.latestFrame == Data([0x02]) } }

        XCTAssertEqual(model.latestFrame, Data([0x02]))
        XCTAssertEqual(model.streamState, .playing)
    }

    @MainActor
    func testStopReturnsToIdleAndStopsClient() async throws {
        let client = RecordingStreamClient()
        let model = GuardViewModel(streamClient: client)

        model.select(cameraID: "camera-a")
        try await waitUntil { await client.hasStarted(cameraID: "camera-a") }
        let stopsBefore = await client.stopCount
        model.stop()
        try await waitUntil { await client.stopCount > stopsBefore }

        XCTAssertEqual(model.streamState, .idle)
    }

    @MainActor
    func testRetryStartsTheSelectedCameraAgainAfterFailure() async throws {
        let client = RecordingStreamClient()
        let model = GuardViewModel(streamClient: client)

        model.select(cameraID: "camera-a")
        try await waitUntil { await client.startCount(cameraID: "camera-a") == 1 }
        await client.fail(cameraID: "camera-a")
        try await waitUntil {
            await MainActor.run {
                if case .failed = model.streamState { return true }
                return false
            }
        }

        model.retry()
        try await waitUntil { await client.startCount(cameraID: "camera-a") == 2 }

        XCTAssertEqual(model.selectedCameraID, "camera-a")
    }
}

private actor RecordingStreamClient: CameraStreamClient {
    private(set) var events: [String] = []
    private var continuations: [String: AsyncThrowingStream<Data, Error>.Continuation] = [:]

    var stopCount: Int { events.filter { $0 == "stop" }.count }

    func frames(cameraID: String, profile: String) async throws -> AsyncThrowingStream<Data, Error> {
        events.append("start:\(cameraID)")
        return AsyncThrowingStream(bufferingPolicy: .bufferingNewest(1)) { continuation in
            continuations[cameraID] = continuation
        }
    }

    func stop() async {
        events.append("stop")
        continuations.values.forEach { $0.finish() }
        continuations.removeAll()
    }

    func hasStarted(cameraID: String) -> Bool {
        events.contains("start:\(cameraID)")
    }

    func startCount(cameraID: String) -> Int {
        events.filter { $0 == "start:\(cameraID)" }.count
    }

    func yield(_ data: Data, cameraID: String) {
        continuations[cameraID]?.yield(data)
    }

    func fail(cameraID: String) {
        continuations[cameraID]?.finish(throwing: URLError(.networkConnectionLost))
        continuations[cameraID] = nil
    }
}

private func waitUntil(
    timeout: TimeInterval = 2,
    condition: @escaping () async -> Bool
) async throws {
    let deadline = Date().addingTimeInterval(timeout)
    while Date() < deadline {
        if await condition() { return }
        try await Task.sleep(nanoseconds: 10_000_000)
    }
    XCTFail("Timed out waiting for condition")
}
