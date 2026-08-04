import Foundation

actor WHEPStreamClient: CameraStreamClient {
    private let apiClient: APIClient
    private let signaling: WHEPSignalingClient
    private var generation = 0
    private var activePlayback: CameraPlaybackSession?
    private var activeResourceURL: URL?
    private var activePeer: NativeWebRTCPeer?
    private var activeSurface: WebRTCVideoSurface?

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
        let peer = try NativeWebRTCPeer(iceServers: iceServers) { [weak self] error in
            Task { await self?.peerTerminated(generation: requestGeneration, error: error) }
        }
        var resourceURL: URL?
        do {
            let offer = try await peer.completeOffer()
            try ensureCurrent(requestGeneration)
            let resource = try await signaling.createResource(playback: playback, offerSDP: offer)
            resourceURL = resource.resourceURL
            try ensureCurrent(requestGeneration)
            let track = try await peer.applyAnswer(resource.answerSDP)
            try ensureCurrent(requestGeneration)

            let surface = WebRTCVideoSurface(track: track)
            activePlayback = playback
            activeResourceURL = resource.resourceURL
            activePeer = peer
            activeSurface = surface
            return CameraDisplayStreams(surface: surface, renderedFrames: surface.renderedFrames)
        } catch {
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

    private func peerTerminated(generation expectedGeneration: Int, error: Error) async {
        guard expectedGeneration == generation else { return }
        activeSurface?.finish(throwing: error)
    }

    private func stopActiveSession() {
        let surface = activeSurface
        let peer = activePeer
        let playback = activePlayback
        let resourceURL = activeResourceURL
        activeSurface = nil
        activePeer = nil
        activePlayback = nil
        activeResourceURL = nil

        surface?.finish()
        peer?.close()
        if let playback, let resourceURL {
            let signaling = signaling
            Task { await signaling.deleteResource(resourceURL, playback: playback) }
        }
    }
}
