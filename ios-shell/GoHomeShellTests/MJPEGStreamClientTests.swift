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
            "display_transport":"edge-composed-mjpeg-v1",
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
        XCTAssertEqual(session.displayTransport, CameraDisplayTransport.edgeComposedMJPEG)
    }

    func testPlaybackSessionAcceptsCloudProxyResponseWithoutNodeFields() throws {
        let payload = Data(#"{"ticket":"play-1","expires_at":null}"#.utf8)

        let session = try JSONDecoder().decode(CameraPlaybackSession.self, from: payload)

        XCTAssertNil(session.streamURL)
        XCTAssertNil(session.streamPath)
    }

    func testPlaybackSessionDecodesEdgeComposedSkeletonTransport() throws {
        let payload = Data(#"{"ticket":"play-2","display_transport":"edge-composed-mjpeg-v1","privacy_mode":"skeleton","minimum_privacy_mode":"skeleton"}"#.utf8)

        let session = try JSONDecoder().decode(CameraPlaybackSession.self, from: payload)

        XCTAssertEqual(session.privacyMode, .skeleton)
        XCTAssertEqual(session.displayTransport, CameraDisplayTransport.edgeComposedMJPEG)
    }

    func testFrameDelegateAcceptsExactEdgeCompositionContract() {
        let delegate = MJPEGFrameDelegate(
            expectedDisplayTransport: CameraDisplayTransport.edgeComposedMJPEG,
            expectedCompositionOwner: "edge"
        )
        let url = URL(string: "https://example.com/stream.mjpg")!
        let response = HTTPURLResponse(
            url: url,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: [
                "X-GoHome-Display-Transport": CameraDisplayTransport.edgeComposedMJPEG,
                "X-GoHome-Composition-Owner": "edge",
            ]
        )!
        let task = URLSession.shared.dataTask(with: url)
        var disposition: URLSession.ResponseDisposition?

        delegate.urlSession(URLSession.shared, dataTask: task, didReceive: response) {
            disposition = $0
        }

        XCTAssertEqual(disposition, .allow)
        delegate.finish(nil)
    }

    func testFrameDelegateRejectsMismatchedCompositionContract() {
        let delegate = MJPEGFrameDelegate(
            expectedDisplayTransport: CameraDisplayTransport.edgeComposedMJPEG,
            expectedCompositionOwner: "edge"
        )
        let url = URL(string: "https://example.com/stream.mjpg")!
        let response = HTTPURLResponse(
            url: url,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: [
                "X-GoHome-Display-Transport": "obsolete-overlay-v1",
                "X-GoHome-Composition-Owner": "client",
            ]
        )!
        let task = URLSession.shared.dataTask(with: url)
        var disposition: URLSession.ResponseDisposition?

        delegate.urlSession(URLSession.shared, dataTask: task, didReceive: response) {
            disposition = $0
        }

        XCTAssertEqual(disposition, .cancel)
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

}

private enum TestStreamError: Error, Equatable {
    case closed
}
