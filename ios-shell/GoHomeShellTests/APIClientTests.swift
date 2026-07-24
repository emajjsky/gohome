import XCTest
@testable import GoHomeShell

final class APIClientTests: XCTestCase {
    private struct Response: Codable, Equatable {
        let value: String
    }

    override func tearDown() {
        URLProtocolStub.handler = nil
        URLProtocolStub.lastRequest = nil
        super.tearDown()
    }

    func testAddsAuthorizationAndDecodesJSON() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.url?.absoluteString, "https://example.com/api/v2/app/bootstrap")
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data(#"{"value":"ok"}"#.utf8))
        }
        let value: Response = try await makeClient(token: "token").send(Endpoint(path: "/api/v2/app/bootstrap"))
        XCTAssertEqual(value, Response(value: "ok"))
        XCTAssertEqual(URLProtocolStub.lastRequest?.value(forHTTPHeaderField: "Authorization"), "Bearer token")
    }

    func testMapsUnauthorizedAndServerDetail() async {
        URLProtocolStub.handler = { request in
            (HTTPURLResponse(url: request.url!, statusCode: 401, httpVersion: nil, headerFields: nil)!, Data())
        }
        await XCTAssertThrowsErrorAsync(try await makeClient().send(Endpoint<Response>(path: "/private"))) { error in
            XCTAssertEqual(error as? APIError, .unauthorized)
        }

        URLProtocolStub.handler = { request in
            (HTTPURLResponse(url: request.url!, statusCode: 422, httpVersion: nil, headerFields: nil)!, Data(#"{"detail":"family_id required"}"#.utf8))
        }
        await XCTAssertThrowsErrorAsync(try await makeClient().send(Endpoint<Response>(path: "/invalid"))) { error in
            XCTAssertEqual(error as? APIError, .server(statusCode: 422, detail: "family_id required"))
        }
    }

    func testMapsNotModifiedWithETag() async {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.value(forHTTPHeaderField: "If-None-Match"), #""revision-1""#)
            return (HTTPURLResponse(url: request.url!, statusCode: 304, httpVersion: nil, headerFields: ["ETag": #""revision-1""#])!, Data())
        }
        await XCTAssertThrowsErrorAsync(
            try await makeClient().send(Endpoint<Response>(path: "/cached", etag: #""revision-1""#))
        ) { error in
            XCTAssertEqual(error as? APIError, .notModified(etag: #""revision-1""#))
        }
    }

    func testBinaryDataKeepsQueryItemsOutOfTheAssetPath() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(
                request.url?.absoluteString,
                "https://example.com/api/v1/video/assets/asset-1?variant=grid"
            )
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data([1]))
        }

        let data = try await makeClient().data(
            path: "/api/v1/video/assets/asset-1",
            queryItems: [URLQueryItem(name: "variant", value: "grid")]
        )

        XCTAssertEqual(data, Data([1]))
    }

    func testDirectUploadUsesSignedURLWithoutAppAuthorization() async throws {
        let payload = Data([1, 2, 3, 4])
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.url?.absoluteString, "https://bucket.cos.ap-shanghai.myqcloud.com/object.jpg?q-sign=temporary")
            XCTAssertEqual(request.httpMethod, "PUT")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "image/jpeg")
            XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"))
            XCTAssertEqual(requestBodyData(request), payload)
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data())
        }

        try await makeClient(token: "app-token").uploadDirectly(
            to: "https://bucket.cos.ap-shanghai.myqcloud.com/object.jpg?q-sign=temporary",
            data: payload,
            contentType: "image/jpeg"
        )
    }

    func testCancellationIsPreserved() async {
        URLProtocolStub.handler = { _ in
            try await Task.sleep(nanoseconds: 5_000_000_000)
            throw URLError(.timedOut)
        }
        let task = Task { try await makeClient().send(Endpoint<Response>(path: "/slow")) }
        task.cancel()
        do {
            _ = try await task.value
            XCTFail("Expected cancellation")
        } catch {
            XCTAssertTrue(error is CancellationError)
        }
    }

    private func makeClient(token: String? = nil) -> APIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [URLProtocolStub.self]
        return APIClient(baseURL: URL(string: "https://example.com")!, session: URLSession(configuration: configuration)) { token }
    }
}

private func requestBodyData(_ request: URLRequest) -> Data? {
    if let body = request.httpBody { return body }
    guard let stream = request.httpBodyStream else { return nil }
    stream.open()
    defer { stream.close() }
    var data = Data()
    var buffer = [UInt8](repeating: 0, count: 4096)
    while stream.hasBytesAvailable {
        let count = stream.read(&buffer, maxLength: buffer.count)
        if count < 0 { return nil }
        if count == 0 { break }
        data.append(buffer, count: count)
    }
    return data
}

private final class URLProtocolStub: URLProtocol, @unchecked Sendable {
    static var handler: (@Sendable (URLRequest) async throws -> (HTTPURLResponse, Data))?
    static var lastRequest: URLRequest?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.lastRequest = request
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

private func XCTAssertThrowsErrorAsync<T>(
    _ expression: @autoclosure () async throws -> T,
    _ handler: (Error) -> Void,
    file: StaticString = #filePath,
    line: UInt = #line
) async {
    do {
        _ = try await expression()
        XCTFail("Expected error", file: file, line: line)
    } catch {
        handler(error)
    }
}
