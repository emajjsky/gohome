import Foundation

protocol CameraStreamClient: Sendable {
    func frames(cameraID: String, profile: String) async throws -> AsyncThrowingStream<Data, Error>
    func stop() async
}

struct CameraPlaybackSession: Decodable, Sendable {
    let ticket: String
    let expiresAt: String?
    let streamURL: String?
    let streamPath: String?

    enum CodingKeys: String, CodingKey {
        case ticket
        case expiresAt = "expires_at"
        case streamURL = "stream_url"
        case streamPath = "stream_path"
    }
}
