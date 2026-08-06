import XCTest
@testable import GoHomeShell

final class NativeWebRTCPeerTests: XCTestCase {
    func testPrepareOfferReturnsInitialSDPForTrickleICE() async throws {
        let peer = try NativeWebRTCPeer(
            iceServers: [],
            localCandidateHandler: { _ in },
            terminalHandler: { _ in }
        )
        defer { peer.close() }

        let offer = try await peer.prepareOffer()

        XCTAssertFalse(offer.sdp.isEmpty)
        XCTAssertFalse(offer.iceUfrag.isEmpty)
        XCTAssertFalse(offer.icePassword.isEmpty)
        XCTAssertTrue(offer.mediaSections.contains { $0.hasPrefix("video ") })
    }

    func testCandidateQueuePreservesOrderAcrossActivationAndDrain() {
        let queue = WHEPCandidateQueue()
        let first = WHEPLocalCandidate(sdp: "candidate:1 1 UDP 1 192.0.2.1 1000 typ host", mediaLineIndex: 0)
        let second = WHEPLocalCandidate(sdp: "candidate:2 1 UDP 2 192.0.2.2 2000 typ host", mediaLineIndex: 0)
        let notification = expectation(description: "candidate queue notification")

        queue.append(first)
        queue.activate { notification.fulfill() }
        queue.append(second)

        wait(for: [notification], timeout: 1)
        XCTAssertEqual(queue.drain(), [first, second])
        XCTAssertTrue(queue.drain().isEmpty)
    }

    func testClosedCandidateQueueRejectsLateCandidates() {
        let queue = WHEPCandidateQueue()
        queue.close()
        queue.append(WHEPLocalCandidate(
            sdp: "candidate:1 1 UDP 1 192.0.2.1 1000 typ host",
            mediaLineIndex: 0
        ))
        XCTAssertTrue(queue.drain().isEmpty)
    }
}
