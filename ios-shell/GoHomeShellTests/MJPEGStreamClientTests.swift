import XCTest
@testable import GoHomeShell

final class MJPEGStreamClientTests: XCTestCase {
    func testPlaybackSessionDecodesScheduledVideoNode() throws {
        let payload = Data(#"""
        {
            "ticket":"play-1",
            "expires_at":"2026-07-22T12:00:00Z",
            "stream_url":"https://video.example.com/api/v1/video/cameras/2/stream.mjpg",
            "stream_path":"/api/v1/video/cameras/2/stream.mjpg"
        }
        """#.utf8)

        let session = try JSONDecoder().decode(CameraPlaybackSession.self, from: payload)

        XCTAssertEqual(session.ticket, "play-1")
        XCTAssertEqual(session.streamURL, "https://video.example.com/api/v1/video/cameras/2/stream.mjpg")
        XCTAssertEqual(session.streamPath, "/api/v1/video/cameras/2/stream.mjpg")
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
}
