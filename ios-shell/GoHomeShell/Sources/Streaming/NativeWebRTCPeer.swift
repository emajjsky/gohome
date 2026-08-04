import Foundation
import WebRTC

final class NativeWebRTCPeer: NSObject, @unchecked Sendable {
    private static let factory: RTCPeerConnectionFactory = {
        _ = RTCInitializeSSL()
        return RTCPeerConnectionFactory()
    }()

    private let terminalHandler: @Sendable (Error) -> Void
    private var connection: RTCPeerConnection!
    private let lock = NSLock()
    private var closed = false

    init(
        iceServers: [WHEPICEServer],
        terminalHandler: @escaping @Sendable (Error) -> Void
    ) throws {
        self.terminalHandler = terminalHandler
        super.init()

        let configuration = RTCConfiguration()
        configuration.sdpSemantics = .unifiedPlan
        configuration.iceServers = iceServers.map {
            RTCIceServer(
                urlStrings: $0.urls,
                username: $0.username,
                credential: $0.credential
            )
        }
        configuration.continualGatheringPolicy = .gatherOnce
        let constraints = RTCMediaConstraints(mandatoryConstraints: nil, optionalConstraints: nil)
        guard let connection = Self.factory.peerConnection(
            with: configuration,
            constraints: constraints,
            delegate: self
        ) else {
            throw APIError.invalidResponse
        }
        self.connection = connection

        let transceiver = RTCRtpTransceiverInit()
        transceiver.direction = .recvOnly
        guard connection.addTransceiver(of: .video, init: transceiver) != nil else {
            connection.close()
            throw APIError.invalidResponse
        }
    }

    func completeOffer(timeoutNanoseconds: UInt64 = 8_000_000_000) async throws -> String {
        let constraints = RTCMediaConstraints(mandatoryConstraints: nil, optionalConstraints: nil)
        let offer: RTCSessionDescription = try await withCheckedThrowingContinuation {
            (continuation: CheckedContinuation<RTCSessionDescription, Error>) in
            connection.offer(for: constraints) { description, error in
                if let error {
                    continuation.resume(throwing: error)
                } else if let description {
                    continuation.resume(returning: description)
                } else {
                    continuation.resume(throwing: APIError.invalidResponse)
                }
            }
        }
        try Task.checkCancellation()
        try await setLocalDescription(offer)

        let deadline = ProcessInfo.processInfo.systemUptime
            + TimeInterval(timeoutNanoseconds) / 1_000_000_000
        while connection.iceGatheringState != .complete {
            try Task.checkCancellation()
            guard ProcessInfo.processInfo.systemUptime < deadline else {
                throw URLError(.timedOut)
            }
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        guard let sdp = connection.localDescription?.sdp, !sdp.isEmpty else {
            throw APIError.invalidResponse
        }
        return sdp
    }

    func applyAnswer(
        _ answerSDP: String,
        timeoutNanoseconds: UInt64 = 5_000_000_000
    ) async throws -> RTCVideoTrack {
        try await setRemoteDescription(RTCSessionDescription(type: .answer, sdp: answerSDP))
        let deadline = ProcessInfo.processInfo.systemUptime
            + TimeInterval(timeoutNanoseconds) / 1_000_000_000
        while ProcessInfo.processInfo.systemUptime < deadline {
            try Task.checkCancellation()
            if let track = remoteVideoTrack() { return track }
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        throw URLError(.timedOut)
    }

    func close() {
        lock.lock()
        guard !closed else {
            lock.unlock()
            return
        }
        closed = true
        lock.unlock()
        connection.close()
    }

    private func setLocalDescription(_ description: RTCSessionDescription) async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            connection.setLocalDescription(description) { error in
                if let error {
                    continuation.resume(throwing: error)
                } else {
                    continuation.resume()
                }
            }
        }
    }

    private func setRemoteDescription(_ description: RTCSessionDescription) async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            connection.setRemoteDescription(description) { error in
                if let error {
                    continuation.resume(throwing: error)
                } else {
                    continuation.resume()
                }
            }
        }
    }

    private func remoteVideoTrack() -> RTCVideoTrack? {
        connection.transceivers
            .lazy
            .compactMap { $0.receiver.track as? RTCVideoTrack }
            .first
    }

    private func reportTerminal(_ error: Error) {
        lock.lock()
        let shouldReport = !closed
        lock.unlock()
        if shouldReport { terminalHandler(error) }
    }
}

extension NativeWebRTCPeer: RTCPeerConnectionDelegate {
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange stateChanged: RTCSignalingState) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didAdd stream: RTCMediaStream) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didRemove stream: RTCMediaStream) {}
    func peerConnectionShouldNegotiate(_ peerConnection: RTCPeerConnection) {}

    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceConnectionState) {
        if newState == .failed || newState == .closed {
            reportTerminal(URLError(.networkConnectionLost))
        }
    }

    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceGatheringState) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didGenerate candidate: RTCIceCandidate) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didRemove candidates: [RTCIceCandidate]) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didOpen dataChannel: RTCDataChannel) {}

    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCPeerConnectionState) {
        if newState == .failed || newState == .closed {
            reportTerminal(URLError(.networkConnectionLost))
        }
    }
}
