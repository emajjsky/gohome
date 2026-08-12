import Foundation

enum CameraDisplayTransport {
    static let whepH264 = "whep-h264-v1"
}

protocol CameraStreamClient: Sendable {
    func streams(
        cameraID: String,
        profile: String,
        privacyMode: VideoPrivacyMode
    ) async throws -> CameraDisplayStreams
    func stop() async
}

struct CameraDisplayStreams: Sendable {
    let surface: WebRTCVideoSurface?
    let renderedFrames: AsyncThrowingStream<TimeInterval, Error>
}

struct CameraPlaybackSession: Decodable, Sendable {
    struct Authorization: Decodable, Sendable {
        let scheme: String
        let token: String
    }

    let sessionID: String
    let expiresAt: String?
    let whepURL: URL
    let authorization: Authorization
    let mediaPath: String
    let privacyMode: VideoPrivacyMode?
    let minimumPrivacyMode: VideoPrivacyMode?
    let displayTransport: String?
    let compositionOwner: String?
    let privacyStatus: String?
    let privacyReady: Bool?
    let deliveredMode: String?

    init(
        sessionID: String,
        expiresAt: String?,
        whepURL: URL,
        authorization: Authorization,
        mediaPath: String,
        privacyMode: VideoPrivacyMode?,
        minimumPrivacyMode: VideoPrivacyMode?,
        displayTransport: String?,
        compositionOwner: String?,
        privacyStatus: String? = nil,
        privacyReady: Bool? = nil,
        deliveredMode: String? = nil
    ) {
        self.sessionID = sessionID
        self.expiresAt = expiresAt
        self.whepURL = whepURL
        self.authorization = authorization
        self.mediaPath = mediaPath
        self.privacyMode = privacyMode
        self.minimumPrivacyMode = minimumPrivacyMode
        self.displayTransport = displayTransport
        self.compositionOwner = compositionOwner
        self.privacyStatus = privacyStatus
        self.privacyReady = privacyReady
        self.deliveredMode = deliveredMode
    }

    enum CodingKeys: String, CodingKey {
        case sessionID = "session_id"
        case expiresAt = "expires_at"
        case whepURL = "whep_url"
        case authorization
        case mediaPath = "media_path"
        case privacyMode = "privacy_mode"
        case minimumPrivacyMode = "minimum_privacy_mode"
        case displayTransport = "display_transport"
        case compositionOwner = "composition_owner"
        case privacyStatus = "privacy_status"
        case privacyReady = "privacy_ready"
        case deliveredMode = "delivered_mode"
    }
}
