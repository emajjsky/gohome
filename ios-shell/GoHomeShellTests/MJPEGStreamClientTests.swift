import XCTest
@testable import GoHomeShell

final class MJPEGStreamClientTests: XCTestCase {
    func testPlaybackSessionDecodesScheduledVideoNode() throws {
        let payload = Data(#"""
        {
            "ticket":"play-1",
            "expires_at":"2026-07-22T12:00:00Z",
            "stream_url":"https://video.example.com/api/v1/video/cameras/2/stream.mjpg",
            "stream_path":"/api/v1/video/cameras/2/stream.mjpg",
            "pose_stream_path":"/api/v1/video/cameras/2/pose-stream",
            "scene_stream_path":"/api/v1/video/cameras/2/scene.mjpg",
            "display_transport":"safe-scene-pose-v1",
            "privacy_mode":"person_blur",
            "minimum_privacy_mode":"person_blur"
        }
        """#.utf8)

        let session = try JSONDecoder().decode(CameraPlaybackSession.self, from: payload)

        XCTAssertEqual(session.ticket, "play-1")
        XCTAssertEqual(session.streamURL, "https://video.example.com/api/v1/video/cameras/2/stream.mjpg")
        XCTAssertEqual(session.streamPath, "/api/v1/video/cameras/2/stream.mjpg")
        XCTAssertEqual(session.privacyMode, .personBlur)
        XCTAssertEqual(session.minimumPrivacyMode, .personBlur)
        XCTAssertEqual(session.poseStreamPath, "/api/v1/video/cameras/2/pose-stream")
        XCTAssertEqual(session.sceneStreamPath, "/api/v1/video/cameras/2/scene.mjpg")
        XCTAssertEqual(session.displayTransport, "safe-scene-pose-v1")
    }

    func testPlaybackSessionAcceptsCloudProxyResponseWithoutNodeFields() throws {
        let payload = Data(#"{"ticket":"play-1","expires_at":null}"#.utf8)

        let session = try JSONDecoder().decode(CameraPlaybackSession.self, from: payload)

        XCTAssertNil(session.streamURL)
        XCTAssertNil(session.streamPath)
    }

    func testParserReassemblesFragmentedJPEGAndDropsHeaders() {
        var parser = MJPEGFrameParser()
        let bytes = Data("--frame\r\nContent-Type: image/jpeg\r\n\r\n".utf8)
            + Data([0xff, 0xd8, 0x01, 0x02, 0xff, 0xd9])
            + Data("\r\n--frame\r\n".utf8)

        var output: Data?
        for byte in bytes { output = parser.append(byte) ?? output }

        XCTAssertEqual(output, Data([0xff, 0xd8, 0x01, 0x02, 0xff, 0xd9]))
    }

    func testParserKeepsSecondFrameAfterFirstFrame() {
        var parser = MJPEGFrameParser()
        let first = Data([0xff, 0xd8, 0x01, 0xff, 0xd9])
        let second = Data([0xff, 0xd8, 0x02, 0xff, 0xd9])
        var frames: [Data] = []

        for byte in first + second {
            if let frame = parser.append(byte) { frames.append(frame) }
        }

        XCTAssertEqual(frames, [first, second])
    }

    func testParserExtractsMultipleFramesFromNetworkSizedChunks() {
        var parser = MJPEGFrameParser()
        let first = Data([0xff, 0xd8, 0x01, 0xff, 0xd9])
        let second = Data([0xff, 0xd8, 0x02, 0xff, 0xd9])
        let payload = Data(repeating: 0x2d, count: 200) + first + Data(repeating: 0x0d, count: 40) + second

        let frames = parser.append(payload)

        XCTAssertEqual(frames, [first, second])
    }

    func testFrameDelegateDropsStaleCompleteFrames() async throws {
        let delegate = MJPEGFrameDelegate()
        let first = Data([0xff, 0xd8, 0x01, 0xff, 0xd9])
        let second = Data([0xff, 0xd8, 0x02, 0xff, 0xd9])

        delegate.receiveForTesting(first)
        delegate.receiveForTesting(second)
        delegate.finish(nil)

        var received: [Data] = []
        for try await frame in delegate.frames {
            received.append(frame)
        }
        XCTAssertEqual(received, [second])
    }

    func testFrameDelegateReassemblesJPEGWithoutByteLoss() async throws {
        let delegate = MJPEGFrameDelegate()
        let frame = Data([0xff, 0xd8, 0x10, 0x20, 0x30, 0xff, 0xd9])
        let chunks = [
            Data("--frame\r\nContent-Type: image/jpeg\r\n\r\n".utf8) + frame.prefix(1),
            frame.subdata(in: 1..<5),
            frame.suffix(2) + Data("\r\n--frame\r\n".utf8),
        ]

        for chunk in chunks {
            delegate.receiveForTesting(chunk)
        }
        delegate.finish(nil)

        var frames: [Data] = []
        for try await parsedFrame in delegate.frames {
            frames.append(parsedFrame)
        }
        XCTAssertEqual(frames, [frame])
    }

    func testFrameDelegateNormalCompletionFinishesFrameStream() async throws {
        let delegate = MJPEGFrameDelegate()
        var iterator = delegate.frames.makeAsyncIterator()

        delegate.finish(nil)

        let frame = try await iterator.next()
        XCTAssertNil(frame)
    }

    func testFrameDelegateErrorCompletionThrowsFromFrameStream() async {
        let delegate = MJPEGFrameDelegate()
        var iterator = delegate.frames.makeAsyncIterator()

        delegate.finish(TestStreamError.closed)

        do {
            _ = try await iterator.next()
            XCTFail("Expected stream error")
        } catch {
            XCTAssertEqual(error as? TestStreamError, .closed)
        }
    }

    func testPoseDelegateReassemblesFragmentedEventsAndKeepsNewestPackets() async throws {
        let delegate = PosePacketDelegate()
        let first = #"{"schema_version":"eacp-pose-relay-v1","camera_id":2,"frame_id":"f1","captured_at":"2026-07-28T08:00:00Z","state":"observed","image_width":640,"image_height":360,"poses":[],"display_only":true,"formal_evidence_eligible":false}"#
        let second = #"{"schema_version":"eacp-pose-relay-v1","camera_id":2,"frame_id":"f2","captured_at":"2026-07-28T08:00:01Z","state":"observed","image_width":640,"image_height":360,"poses":[],"display_only":true,"formal_evidence_eligible":false}"#
        let third = #"{"schema_version":"eacp-pose-relay-v1","camera_id":2,"frame_id":"f3","captured_at":"2026-07-28T08:00:02Z","state":"observed","image_width":640,"image_height":360,"poses":[],"display_only":true,"formal_evidence_eligible":false}"#
        let payload = Data("data: \(first)\n\ndata: \(second)\n\ndata: \(third)\n\n".utf8)

        delegate.receiveForTesting(Data(payload.prefix(37)))
        delegate.receiveForTesting(Data(payload.dropFirst(37)))
        delegate.finish(nil)

        var packets: [PosePacket] = []
        for try await packet in delegate.packets {
            packets.append(packet)
        }
        XCTAssertEqual(packets.map(\.frameID), ["f2", "f3"])
    }

    func testPoseParserReassemblesFragmentedSSEAndRejectsEvidencePackets() {
        let safe = #"{"schema_version":"eacp-pose-relay-v1","camera_id":2,"frame_id":"f1","captured_at":"2026-07-28T08:00:00Z","state":"observed","image_width":640,"image_height":360,"poses":[],"display_only":true,"formal_evidence_eligible":false}"#
        let unsafe = #"{"schema_version":"eacp-pose-relay-v1","camera_id":2,"frame_id":"f2","captured_at":"2026-07-28T08:00:01Z","state":"observed","image_width":640,"image_height":360,"poses":[],"display_only":true,"formal_evidence_eligible":true}"#
        let payload = Data("event: pose\ndata: \(safe)\n\nevent: pose\ndata: \(unsafe)\n\n".utf8)
        var parser = PoseSSEParser()

        let first = parser.append(Data(payload.prefix(31)))
        let second = parser.append(Data(payload.dropFirst(31)))

        XCTAssertTrue(first.isEmpty)
        XCTAssertEqual(second.map(\.frameID), ["f1"])
    }

    func testPoseTimelineInterpolatesMatchingTracks() {
        let previous = posePacket(frameID: "f1", x: 100)
        let current = posePacket(frameID: "f2", x: 200)
        let start = Date(timeIntervalSince1970: 100)
        let timeline = PoseTimeline(
            previous: TimedPosePacket(packet: previous, receivedAt: start),
            current: TimedPosePacket(packet: current, receivedAt: start.addingTimeInterval(0.1))
        )

        let rendered = timeline.interpolated(at: start.addingTimeInterval(0.117), delay: 0.067)

        XCTAssertEqual(rendered?.poses.first?.keypoints.first?.x ?? 0, 150, accuracy: 0.001)
    }

    func testPoseTimelineUsesCaptureClockWhenNetworkArrivalJitters() {
        let previous = posePacket(frameID: "f1", capturedAt: "2026-07-28T08:00:00.000Z", x: 100)
        let current = posePacket(frameID: "f2", capturedAt: "2026-07-28T08:00:00.100Z", x: 200)
        let sourceCurrent = ISO8601DateFormatter().date(from: "2026-07-28T08:00:00Z")!.addingTimeInterval(0.1)
        let receivedCurrent = sourceCurrent.addingTimeInterval(0.24)
        let timeline = PoseTimeline(
            previous: TimedPosePacket(packet: previous, receivedAt: receivedCurrent.addingTimeInterval(-0.02)),
            current: TimedPosePacket(packet: current, receivedAt: receivedCurrent)
        )

        let rendered = timeline.interpolated(at: receivedCurrent.addingTimeInterval(0.017), delay: 0.067)

        XCTAssertEqual(rendered?.poses.first?.keypoints.first?.x ?? 0, 150, accuracy: 0.001)
    }
}

private func posePacket(
    frameID: String,
    capturedAt: String = "2026-07-28T08:00:00Z",
    x: Double
) -> PosePacket {
    PosePacket(
        schemaVersion: "eacp-pose-relay-v1",
        cameraID: 2,
        frameID: frameID,
        capturedAt: capturedAt,
        state: "observed",
        imageWidth: 640,
        imageHeight: 360,
        poses: [PoseTrack(
            trackID: "person-1",
            confidence: 0.9,
            bbox: [90, 20, 220, 350],
            keypoints: [PoseKeypoint(name: "nose", x: x, y: 60, confidence: 0.9, visible: true)]
        )],
        displayOnly: true,
        formalEvidenceEligible: false
    )
}

private enum TestStreamError: Error, Equatable {
    case closed
}
