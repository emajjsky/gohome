import XCTest
@testable import GoHomeShell

@MainActor
final class MemoryVideoPlaybackStoreTests: XCTestCase {
    override func tearDown() {
        MemoryPlaybackURLProtocolStub.handler = nil
        super.tearDown()
    }

    func testPosterAndPlayerReuseSignedPlaybackURLAndPersistPoster() async throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let recorder = MemoryPlaybackRequestRecorder()
        MemoryPlaybackURLProtocolStub.handler = { request in
            await recorder.record(request)
            let body = Data(#"{"url":"https://bucket.cos.ap-shanghai.myqcloud.com/video.mp4?q-sign=temporary","expires_at":"2099-07-24T12:05:00.000Z"}"#.utf8)
            return (
                HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!,
                body
            )
        }
        let client = makeClient()
        let posterData = try XCTUnwrap(
            UIGraphicsImageRenderer(size: CGSize(width: 8, height: 8)).image { context in
                UIColor.systemYellow.setFill()
                context.fill(CGRect(x: 0, y: 0, width: 8, height: 8))
            }.jpegData(compressionQuality: 0.8)
        )
        let store = MemoryVideoPlaybackStore(cacheDirectory: root) { _ in posterData }

        let poster = await store.poster(assetID: "asset-video", apiClient: client)
        let playbackURL = try await store.playbackURL(assetID: "asset-video", apiClient: client)

        XCTAssertNotNil(poster)
        XCTAssertEqual(playbackURL.host, "bucket.cos.ap-shanghai.myqcloud.com")
        let firstRequestCount = await recorder.count
        XCTAssertEqual(firstRequestCount, 1)

        let restoredStore = MemoryVideoPlaybackStore(cacheDirectory: root) { _ in nil }
        let restoredPoster = await restoredStore.poster(assetID: "asset-video", apiClient: nil)

        XCTAssertNotNil(restoredPoster)
        let finalRequestCount = await recorder.count
        XCTAssertEqual(finalRequestCount, 1)
    }

    private func makeClient() -> APIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MemoryPlaybackURLProtocolStub.self]
        return APIClient(
            baseURL: URL(string: "https://gohome.example")!,
            session: URLSession(configuration: configuration),
            token: { "app-token" }
        )
    }
}

private actor MemoryPlaybackRequestRecorder {
    private(set) var requests: [URLRequest] = []
    var count: Int { requests.count }

    func record(_ request: URLRequest) {
        requests.append(request)
    }
}

private final class MemoryPlaybackURLProtocolStub: URLProtocol, @unchecked Sendable {
    static var handler: (@Sendable (URLRequest) async throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Task {
            do {
                guard let handler = Self.handler else { throw URLError(.badServerResponse) }
                let (response, data) = try await handler(request)
                client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
                client?.urlProtocol(self, didLoad: data)
                client?.urlProtocolDidFinishLoading(self)
            } catch {
                client?.urlProtocol(self, didFailWithError: error)
            }
        }
    }

    override func stopLoading() {}
}
