import Foundation

actor WHEPStreamClient: CameraStreamClient {
    private let apiClient: APIClient
    private let signaling: WHEPSignalingClient
    private var generation = 0
    private var activePlayback: CameraPlaybackSession?
    private var activeResourceURL: URL?
    private var activePeer: NativeWebRTCPeer?
    private var activeSurface: WebRTCVideoSurface?
    private var activeOffer: WHEPOffer?
    private var candidateQueue: WHEPCandidateQueue?
    private var candidateDeliveryRunning = false
    private var candidateDeliveryGeneration = 0
    private var connectingGeneration: Int?
    private var connectingError: Error?

    init(apiClient: APIClient, signaling: WHEPSignalingClient = WHEPSignalingClient()) {
        self.apiClient = apiClient
        self.signaling = signaling
    }

    func streams(
        cameraID: String,
        profile: String,
        privacyMode: VideoPrivacyMode
    ) async throws -> CameraDisplayStreams {
        generation += 1
        let requestGeneration = generation
        stopActiveSession()

        let body = try JSONEncoder().encode([
            "resource_type": "stream",
            "camera_id": cameraID,
            "profile": profile,
            "privacy_mode": privacyMode.rawValue,
        ])
        let playback: CameraPlaybackSession = try await apiClient.send(Endpoint(
            method: .post,
            path: "/api/v1/video/sessions",
            body: body
        ))
        try ensureCurrent(requestGeneration)
        guard
            playback.displayTransport == CameraDisplayTransport.whepH264,
            playback.compositionOwner == "edge",
            playback.whepURL.scheme?.lowercased() == "https",
            playback.authorization.scheme.caseInsensitiveCompare("Bearer") == .orderedSame,
            !playback.authorization.token.isEmpty,
            !playback.mediaPath.isEmpty
        else { throw APIError.invalidResponse }

        let iceServers = try await signaling.discoverICEServers(for: playback)
        try ensureCurrent(requestGeneration)
        let queue = WHEPCandidateQueue()
        connectingGeneration = requestGeneration
        connectingError = nil
        let peer = try NativeWebRTCPeer(
            iceServers: iceServers,
            localCandidateHandler: { candidate in queue.append(candidate) },
            terminalHandler: { [weak self] error in
                Task { await self?.peerTerminated(generation: requestGeneration, error: error) }
            }
        )
        var resourceURL: URL?
        do {
            let offer = try await peer.prepareOffer()
            try ensureConnectionCurrent(requestGeneration)
            let resource = try await signaling.createResource(playback: playback, offerSDP: offer.sdp)
            resourceURL = resource.resourceURL
            try ensureConnectionCurrent(requestGeneration)
            let track = try await peer.applyAnswer(resource.answerSDP)
            try ensureConnectionCurrent(requestGeneration)

            let surface = WebRTCVideoSurface(track: track)
            activePlayback = playback
            activeResourceURL = resource.resourceURL
            activePeer = peer
            activeSurface = surface
            activeOffer = offer
            candidateQueue = queue
            candidateDeliveryGeneration = requestGeneration
            candidateDeliveryRunning = false
            connectingGeneration = nil
            connectingError = nil
            queue.activate { [weak self] in
                Task { await self?.deliverCandidates(generation: requestGeneration) }
            }
            return CameraDisplayStreams(surface: surface, renderedFrames: surface.renderedFrames)
        } catch {
            if connectingGeneration == requestGeneration {
                connectingGeneration = nil
                connectingError = nil
            }
            queue.close()
            peer.close()
            if let resourceURL {
                await signaling.deleteResource(resourceURL, playback: playback)
            }
            throw error
        }
    }

    func stop() async {
        generation += 1
        stopActiveSession()
    }

    private func ensureCurrent(_ expectedGeneration: Int) throws {
        guard expectedGeneration == generation, !Task.isCancelled else {
            throw CancellationError()
        }
    }

    private func ensureConnectionCurrent(_ expectedGeneration: Int) throws {
        try ensureCurrent(expectedGeneration)
        if connectingGeneration == expectedGeneration, let connectingError {
            throw connectingError
        }
    }

    private func peerTerminated(generation expectedGeneration: Int, error: Error) async {
        guard expectedGeneration == generation else { return }
        if connectingGeneration == expectedGeneration, activePeer == nil {
            connectingError = error
            return
        }
        stopActiveSession(error: error)
    }

    private func deliverCandidates(generation expectedGeneration: Int) async {
        guard
            expectedGeneration == generation,
            activePlayback != nil,
            activeResourceURL != nil,
            activeOffer != nil,
            candidateQueue != nil
        else { return }
        guard !candidateDeliveryRunning || candidateDeliveryGeneration != expectedGeneration else { return }

        candidateDeliveryRunning = true
        candidateDeliveryGeneration = expectedGeneration
        while expectedGeneration == generation {
            guard
                let playback = activePlayback,
                let resourceURL = activeResourceURL,
                let offer = activeOffer,
                let queue = candidateQueue
            else { break }
            let batch = queue.drain()
            guard !batch.isEmpty else { break }
            do {
                try await signaling.addCandidates(
                    batch,
                    offer: offer,
                    resourceURL: resourceURL,
                    playback: playback
                )
            } catch {
                if expectedGeneration == generation {
                    stopActiveSession(error: error)
                }
                break
            }
        }
        if candidateDeliveryGeneration == expectedGeneration {
            candidateDeliveryRunning = false
        }
    }

    private func stopActiveSession(error: Error? = nil) {
        let surface = activeSurface
        let peer = activePeer
        let playback = activePlayback
        let resourceURL = activeResourceURL
        candidateQueue?.close()
        candidateQueue = nil
        activeSurface = nil
        activePeer = nil
        activePlayback = nil
        activeResourceURL = nil
        activeOffer = nil
        candidateDeliveryRunning = false
        candidateDeliveryGeneration = generation
        connectingGeneration = nil
        connectingError = nil

        surface?.finish(throwing: error)
        peer?.close()
        if let playback, let resourceURL {
            let signaling = signaling
            Task { await signaling.deleteResource(resourceURL, playback: playback) }
        }
    }
}

final class WHEPCandidateQueue: @unchecked Sendable {
    private let lock = NSLock()
    private var pending: [WHEPLocalCandidate] = []
    private var notify: (@Sendable () -> Void)?
    private var notificationPending = false
    private var closed = false

    func append(_ candidate: WHEPLocalCandidate) {
        lock.lock()
        guard !closed else {
            lock.unlock()
            return
        }
        pending.append(candidate)
        let callback = notificationCallbackLocked()
        lock.unlock()
        callback?()
    }

    func activate(_ notify: @escaping @Sendable () -> Void) {
        lock.lock()
        guard !closed else {
            lock.unlock()
            return
        }
        self.notify = notify
        let callback = notificationCallbackLocked()
        lock.unlock()
        callback?()
    }

    func drain() -> [WHEPLocalCandidate] {
        lock.lock()
        guard !closed else {
            lock.unlock()
            return []
        }
        let candidates = pending
        pending.removeAll(keepingCapacity: true)
        notificationPending = false
        lock.unlock()
        return candidates
    }

    func close() {
        lock.lock()
        closed = true
        notify = nil
        notificationPending = false
        pending.removeAll(keepingCapacity: false)
        lock.unlock()
    }

    private func notificationCallbackLocked() -> (@Sendable () -> Void)? {
        guard !pending.isEmpty, !notificationPending, let notify else { return nil }
        notificationPending = true
        return notify
    }
}
