import Foundation

protocol CameraStreamClient: Sendable {
    func frames(
        cameraID: String,
        profile: String,
        privacyMode: VideoPrivacyMode
    ) async throws -> AsyncThrowingStream<Data, Error>
    func stop() async
}

struct CameraPlaybackSession: Decodable, Sendable {
    let ticket: String
    let expiresAt: String?
    let streamURL: String?
    let streamPath: String?
    let privacyMode: VideoPrivacyMode?
    let minimumPrivacyMode: VideoPrivacyMode?

    enum CodingKeys: String, CodingKey {
        case ticket
        case expiresAt = "expires_at"
        case streamURL = "stream_url"
        case streamPath = "stream_path"
        case privacyMode = "privacy_mode"
        case minimumPrivacyMode = "minimum_privacy_mode"
    }
}
