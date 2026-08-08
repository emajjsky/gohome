import XCTest
@testable import GoHomeShell

final class MemoryMediaUploadTransactionTests: XCTestCase {
    override func tearDown() {
        MemoryUploadURLProtocolStub.handler = nil
        super.tearDown()
    }

    func testCancellationAfterIntentCreationStillAbortsUpload() async throws {
        let recorder = MemoryUploadRequestRecorder()
        MemoryUploadURLProtocolStub.handler = { request in
            await recorder.record(request)
            switch (request.httpMethod, request.url?.path) {
            case ("POST", "/api/v2/memory-media-upload-intents"):
                return Self.response(
                    request,
                    statusCode: 201,
                    body: #"{"uploads":[{"asset_id":"asset-1","upload_url":"https://example.com/cos/object-1","upload_token":"token-1","content_type":"image/jpeg","expires_at":"2026-08-08T22:00:00Z"}]}"#
                )
            case ("PUT", "/cos/object-1"):
                await recorder.markDirectUploadStarted()
                try await Task.sleep(nanoseconds: 5_000_000_000)
                return Self.response(request, statusCode: 200, body: "")
            case ("POST", "/api/v2/memory-media-upload-abort"):
                return Self.response(request, statusCode: 200, body: #"{"deleted":1}"#)
            default:
                throw URLError(.badServerResponse)
            }
        }
        let task = Task {
            try await MemoryMediaUploadTransaction.execute(
                client: makeClient(),
                familyID: "family-1",
                media: [makeUpload()]
            )
        }
        for _ in 0..<100 {
            if await recorder.directUploadStarted { break }
            try await Task.sleep(nanoseconds: 2_000_000)
        }

        task.cancel()

        do {
            _ = try await task.value
            XCTFail("Expected cancellation")
        } catch {
            XCTAssertTrue(error is CancellationError)
        }
        let requests = await recorder.requests
        XCTAssertEqual(requests.map(\.path), [
            "/api/v2/memory-media-upload-intents",
            "/cos/object-1",
            "/api/v2/memory-media-upload-abort",
        ])
        XCTAssertEqual(requests.last?.authorization, "Bearer app-token")
        XCTAssertEqual(requests.last?.bodyItems, ["asset-1"])
    }

    func testInvalidIntentCountAbortsEveryCreatedIntent() async throws {
        let recorder = MemoryUploadRequestRecorder()
        MemoryUploadURLProtocolStub.handler = { request in
            await recorder.record(request)
            switch (request.httpMethod, request.url?.path) {
            case ("POST", "/api/v2/memory-media-upload-intents"):
                return Self.response(
                    request,
                    statusCode: 201,
                    body: #"{"uploads":[{"asset_id":"asset-1","upload_url":"https://example.com/cos/object-1","upload_token":"token-1","content_type":"image/jpeg","expires_at":"2026-08-08T22:00:00Z"},{"asset_id":"asset-2","upload_url":"https://example.com/cos/object-2","upload_token":"token-2","content_type":"image/jpeg","expires_at":"2026-08-08T22:00:00Z"}]}"#
                )
            case ("POST", "/api/v2/memory-media-upload-abort"):
                return Self.response(request, statusCode: 200, body: #"{"deleted":2}"#)
            default:
                throw URLError(.badServerResponse)
            }
        }

        do {
            _ = try await MemoryMediaUploadTransaction.execute(
                client: makeClient(),
                familyID: "family-1",
                media: [makeUpload()]
            )
            XCTFail("Expected invalid response")
        } catch {
            XCTAssertEqual(error as? APIError, .invalidResponse)
        }

        let requests = await recorder.requests
        XCTAssertEqual(requests.map(\.path), [
            "/api/v2/memory-media-upload-intents",
            "/api/v2/memory-media-upload-abort",
        ])
        XCTAssertEqual(requests.last?.bodyItems, ["asset-1", "asset-2"])
    }

    private func makeClient() -> APIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MemoryUploadURLProtocolStub.self]
        return APIClient(
            baseURL: URL(string: "https://example.com")!,
            session: URLSession(configuration: configuration)
        ) { "app-token" }
    }

    private func makeUpload() -> MemoryUploadAsset {
        MemoryUploadAsset(
            data: Data([1, 2, 3]),
            contentType: "image/jpeg",
            pixelWidth: 1280,
            pixelHeight: 960,
            durationSeconds: nil
        )
    }

    private static func response(
        _ request: URLRequest,
        statusCode: Int,
        body: String
    ) -> (HTTPURLResponse, Data) {
        (
            HTTPURLResponse(url: request.url!, statusCode: statusCode, httpVersion: nil, headerFields: nil)!,
            Data(body.utf8)
        )
    }
}

private struct RecordedMemoryUploadRequest: Sendable {
    let path: String
    let authorization: String?
    let bodyItems: [String]
}

private actor MemoryUploadRequestRecorder {
    private(set) var requests: [RecordedMemoryUploadRequest] = []
    private(set) var directUploadStarted = false

    func record(_ request: URLRequest) {
        let bodyItems: [String]
        if
            let body = memoryUploadRequestBody(request),
            let object = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
            let items = object["items"] as? [[String: Any]]
        {
            bodyItems = items.compactMap { $0["asset_id"] as? String }
        } else {
            bodyItems = []
        }
        requests.append(RecordedMemoryUploadRequest(
            path: request.url?.path ?? "",
            authorization: request.value(forHTTPHeaderField: "Authorization"),
            bodyItems: bodyItems
        ))
    }

    func markDirectUploadStarted() {
        directUploadStarted = true
    }
}

private func memoryUploadRequestBody(_ request: URLRequest) -> Data? {
    if let body = request.httpBody { return body }
    guard let stream = request.httpBodyStream else { return nil }
    stream.open()
    defer { stream.close() }
    var data = Data()
    var buffer = [UInt8](repeating: 0, count: 4096)
    while stream.hasBytesAvailable {
        let count = stream.read(&buffer, maxLength: buffer.count)
        if count <= 0 { break }
        data.append(buffer, count: count)
    }
    return data
}

private final class MemoryUploadURLProtocolStub: URLProtocol, @unchecked Sendable {
    static var handler: (@Sendable (URLRequest) async throws -> (HTTPURLResponse, Data))?
    private var loadingTask: Task<Void, Never>?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        loadingTask = Task {
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

    override func stopLoading() {
        loadingTask?.cancel()
        loadingTask = nil
    }
}
