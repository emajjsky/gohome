import Foundation

enum CameraDisplayTransport {
    static let edgeComposedMJPEG = "edge-composed-mjpeg-v1"
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
    let frames: AsyncThrowingStream<Data, Error>
}

struct CameraPlaybackSession: Decodable, Sendable {
    let ticket: String
    let expiresAt: String?
    let streamURL: String?
    let streamPath: String?
    let privacyMode: VideoPrivacyMode?
    let minimumPrivacyMode: VideoPrivacyMode?
    let displayTransport: String?

    enum CodingKeys: String, CodingKey {
        case ticket
        case expiresAt = "expires_at"
        case streamURL = "stream_url"
        case streamPath = "stream_path"
        case privacyMode = "privacy_mode"
        case minimumPrivacyMode = "minimum_privacy_mode"
        case displayTransport = "display_transport"
    }
}
