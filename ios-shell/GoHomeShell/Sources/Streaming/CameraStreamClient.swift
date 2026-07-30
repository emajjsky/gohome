import Foundation

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
    let poses: AsyncThrowingStream<PosePacket, Error>?
}

struct CameraPlaybackSession: Decodable, Sendable {
    let ticket: String
    let expiresAt: String?
    let streamURL: String?
    let streamPath: String?
    let privacyMode: VideoPrivacyMode?
    let minimumPrivacyMode: VideoPrivacyMode?
    let poseStreamURL: String?
    let poseStreamPath: String?
    let sceneStreamURL: String?
    let sceneStreamPath: String?
    let displayTransport: String?

    enum CodingKeys: String, CodingKey {
        case ticket
        case expiresAt = "expires_at"
        case streamURL = "stream_url"
        case streamPath = "stream_path"
        case privacyMode = "privacy_mode"
        case minimumPrivacyMode = "minimum_privacy_mode"
        case poseStreamURL = "pose_stream_url"
        case poseStreamPath = "pose_stream_path"
        case sceneStreamURL = "scene_stream_url"
        case sceneStreamPath = "scene_stream_path"
        case displayTransport = "display_transport"
    }
}
