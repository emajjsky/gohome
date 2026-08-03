import XCTest
@testable import GoHomeShell

final class GuardViewModelTests: XCTestCase {
    func testFrameRateMeterReportsRollingPresentedFrames() {
        var meter = FrameRateMeter(windowSeconds: 2)

        XCTAssertEqual(meter.record(at: 10), 0)
        XCTAssertEqual(meter.record(at: 10.1), 10, accuracy: 0.001)
        XCTAssertEqual(meter.record(at: 10.2), 10, accuracy: 0.001)
        XCTAssertEqual(meter.record(at: 12.3), 0)
        XCTAssertEqual(meter.record(at: 12.4), 10, accuracy: 0.001)

        meter.reset()
        XCTAssertEqual(meter.record(at: 20), 0)
    }

    func testSkeletonRateLabelUsesDecodedVideoFPS() {
        let stage = CameraStageView(
            image: nil,
            state: .playing,
            displayFPS: 12.4,
            privacyMode: .skeleton
        )

        XCTAssertTrue(stage.shouldShowRate)
        XCTAssertEqual(stage.rateText, "12.4 FPS")
    }

    func testSkeletonRateLabelUsesDecodedFPSImmediately() {
        let stage = CameraStageView(
            image: nil,
            state: .playing,
            displayFPS: 11.7,
            privacyMode: .skeleton
        )

        XCTAssertTrue(stage.shouldShowRate)
        XCTAssertEqual(stage.rateText, "11.7 FPS")
    }

    func testGuardCameraCatalogUsesCanonicalProfileCameras() {
        let profile = ProfileData(
            elder: nil,
            bindings: [],
            cameras: [
                CameraConfig(
                    id: "3",
                    familyID: "family-1",
                    deviceID: "box-1",
                    name: "冰箱上面",
                    room: "厨房",
                    status: "online",
                    syncStatus: "synced",
                    enabled: true
                ),
                CameraConfig(
                    id: "4",
                    familyID: "family-1",
                    deviceID: "box-1",
                    name: "电视柜",
                    room: "客厅",
                    status: "online",
                    syncStatus: "synced",
                    enabled: false
                ),
            ],
            rules: FamilyRules(
                canEdit: true,
                offlineEnabled: true,
                blackScreenEnabled: true,
                noMotionEnabled: true,
                personDetectionEnabled: true,
                fallDetectionEnabled: true,
                activityDetectionEnabled: true,
                fireDetectionEnabled: true,
                notificationEnabled: true
            ),
            carePreferences: CarePreferences(familyID: "family-1"),
            productPreferences: ProductPreferences(categories: [], needs: [])
        )
        let stale = [HomeCamera(id: "2", name: "旧摄像头", status: "offline")]

        XCTAssertEqual(
            GuardCameraCatalog.resolve(profile: profile, fallback: stale),
            [HomeCamera(id: "3", name: "冰箱上面", status: "online")]
        )
    }

    func testGuardCameraCatalogUsesHomeCacheUntilProfileLoads() {
        let cached = [HomeCamera(id: "3", name: "冰箱上面", status: "online")]
        XCTAssertEqual(GuardCameraCatalog.resolve(profile: nil, fallback: cached), cached)
    }

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
    func testStreamFailureReconnectsTheSelectedCamera() async throws {
        let client = RecordingStreamClient()
        let model = GuardViewModel(
            streamClient: client,
            reconnectDelayNanoseconds: 1_000_000
        )

        model.select(cameraID: "camera-a")
        try await waitUntil { await client.startCount(cameraID: "camera-a") == 1 }
        await client.fail(cameraID: "camera-a")
        try await waitUntil { await client.startCount(cameraID: "camera-a") == 2 }

        XCTAssertEqual(model.selectedCameraID, "camera-a")
        XCTAssertEqual(model.streamState, .connecting)
    }

    @MainActor
    func testFrameWatchdogReconnectsAStalledStream() async throws {
        let client = RecordingStreamClient()
        let model = GuardViewModel(
            streamClient: client,
            frameTimeoutNanoseconds: 20_000_000,
            reconnectDelayNanoseconds: 1_000_000
        )

        model.select(cameraID: "camera-a")
        try await waitUntil { await client.startCount(cameraID: "camera-a") == 1 }
        try await waitUntil { await client.startCount(cameraID: "camera-a") == 2 }

        let stopCount = await client.stopCount
        XCTAssertGreaterThanOrEqual(stopCount, 2)
    }

    @MainActor
    func testRepeatedConnectionFailuresStopAfterTheRetryLimit() async throws {
        let client = FailingStreamClient()
        let model = GuardViewModel(
            streamClient: client,
            reconnectDelayNanoseconds: 1_000_000,
            maxReconnectAttempts: 2
        )

        model.select(cameraID: "camera-a")
        try await waitUntil {
            await MainActor.run {
                if case .failed = model.streamState { return true }
                return false
            }
        }

        let startCount = await client.startCount
        XCTAssertEqual(startCount, 3)
    }

    @MainActor
    func testSharedPrivacyPolicyRestartsTheSameCameraWithoutClearingTheCurrentFrame() async throws {
        let client = RecordingStreamClient()
        let privacy = RecordingPrivacyService(policy: VideoPrivacyPolicy(
            familyID: "family-1",
            minimumMode: .skeleton,
            canManage: true
        ))
        let model = GuardViewModel(
            streamClient: client,
            privacyService: privacy,
            familyID: "family-1"
        )

        model.select(cameraID: "camera-a")
        try await waitUntil { await client.hasStarted(cameraID: "camera-a") }
        await client.yield(Data([0x01]), cameraID: "camera-a")
        try await waitUntil { await MainActor.run { model.latestFrame == Data([0x01]) } }

        model.startPrivacySync()
        try await waitUntil {
            let selectedSkeleton = await MainActor.run { model.selectedPrivacyMode == .skeleton }
            let streamedMode = await client.lastPrivacyMode(cameraID: "camera-a")
            return selectedSkeleton && streamedMode == .skeleton
        }

        XCTAssertEqual(model.latestFrame, Data([0x01]))
        model.stop()
    }

    @MainActor
    func testCreatorPrivacyChangePersistsTheFamilyMode() async throws {
        let client = RecordingStreamClient()
        let privacy = RecordingPrivacyService(policy: VideoPrivacyPolicy(
            familyID: "family-1",
            minimumMode: .original,
            canManage: true
        ))
        let model = GuardViewModel(
            streamClient: client,
            privacyService: privacy,
            familyID: "family-1"
        )

        model.startPrivacySync()
        try await waitUntil { await MainActor.run { model.privacyPolicy != nil } }
        model.setPrivacyMode(.personBlur)
        try await waitUntil { await MainActor.run { model.selectedPrivacyMode == .personBlur } }

        let currentPolicy = await privacy.currentPolicy()
        XCTAssertEqual(currentPolicy.minimumMode, .personBlur)
        model.stop()
    }

}

private actor FailingStreamClient: CameraStreamClient {
    private(set) var startCount = 0

    func streams(
        cameraID: String,
        profile: String,
        privacyMode: VideoPrivacyMode
    ) async throws -> CameraDisplayStreams {
        startCount += 1
        throw URLError(.cannotConnectToHost)
    }

    func stop() async {}
}

private actor RecordingStreamClient: CameraStreamClient {
    private(set) var events: [String] = []
    private var continuations: [String: AsyncThrowingStream<Data, Error>.Continuation] = [:]
    private var privacyModes: [String: VideoPrivacyMode] = [:]

    var stopCount: Int { events.filter { $0 == "stop" }.count }

    func streams(
        cameraID: String,
        profile: String,
        privacyMode: VideoPrivacyMode
    ) async throws -> CameraDisplayStreams {
        events.append("start:\(cameraID)")
        privacyModes[cameraID] = privacyMode
        let frames = AsyncThrowingStream<Data, Error>(bufferingPolicy: .bufferingNewest(1)) { continuation in
            continuations[cameraID] = continuation
        }
        return CameraDisplayStreams(frames: frames)
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

    func lastPrivacyMode(cameraID: String) -> VideoPrivacyMode? {
        privacyModes[cameraID]
    }

    func yield(_ data: Data, cameraID: String) {
        continuations[cameraID]?.yield(data)
    }

    func fail(cameraID: String) {
        continuations[cameraID]?.finish(throwing: URLError(.networkConnectionLost))
        continuations[cameraID] = nil
    }
}

private actor RecordingPrivacyService: VideoPrivacyServicing {
    private var policy: VideoPrivacyPolicy

    init(policy: VideoPrivacyPolicy) {
        self.policy = policy
    }

    func fetch(familyID: String) async throws -> VideoPrivacyPolicy {
        policy
    }

    func update(familyID: String, minimumMode: VideoPrivacyMode) async throws -> VideoPrivacyPolicy {
        policy = VideoPrivacyPolicy(
            familyID: familyID,
            minimumMode: minimumMode,
            updatedAt: "2026-07-26T12:00:00Z",
            canManage: policy.canManage
        )
        return policy
    }

    func currentPolicy() -> VideoPrivacyPolicy {
        policy
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
