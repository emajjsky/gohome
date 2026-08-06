import XCTest
@testable import GoHomeShell

final class WHEPSignalingClientTests: XCTestCase {
    override func tearDown() {
        WHEPURLProtocolStub.handler = nil
        WHEPURLProtocolStub.requests = []
        super.tearDown()
    }

    func testPlaybackSessionDecodesAuthenticatedWHEPContract() throws {
        let payload = Data(#"""
        {
            "session_id":"media-session-1",
            "expires_at":"2026-08-04T12:00:00Z",
            "whep_url":"https://media.example.com/media/live/box-1/2/whep",
            "authorization":{"scheme":"Bearer","token":"m1.signed"},
            "media_path":"live/box-1/2",
            "display_transport":"whep-h264-v1",
            "composition_owner":"edge",
            "privacy_mode":"skeleton",
            "minimum_privacy_mode":"skeleton"
        }
        """#.utf8)

        let session = try JSONDecoder().decode(CameraPlaybackSession.self, from: payload)

        XCTAssertEqual(session.sessionID, "media-session-1")
        XCTAssertEqual(session.whepURL.absoluteString, "https://media.example.com/media/live/box-1/2/whep")
        XCTAssertEqual(session.authorization.scheme, "Bearer")
        XCTAssertEqual(session.authorization.token, "m1.signed")
        XCTAssertEqual(session.mediaPath, "live/box-1/2")
        XCTAssertEqual(session.privacyMode, .skeleton)
        XCTAssertEqual(session.minimumPrivacyMode, .skeleton)
        XCTAssertEqual(session.displayTransport, CameraDisplayTransport.whepH264)
        XCTAssertEqual(session.compositionOwner, "edge")
    }

    func testPlaybackSessionDecodesProductionShapeWithoutOptionalMinimumMode() throws {
        let payload = Data(#"""
        {
            "session_id":"b733fb03-6288-48a9-a1b4-e57fd1859b13",
            "expires_at":"2026-08-06T00:52:54.000Z",
            "display_transport":"whep-h264-v1",
            "composition_owner":"edge",
            "privacy_mode":"skeleton",
            "media_path":"live/edge-042714be475b91da/28",
            "whep_url":"https://gohome.ai2shx.club/media/live/edge-042714be475b91da/28/whep",
            "authorization":{
                "scheme":"Bearer",
                "token":"m1.production-shaped-base64url-payload.production-shaped-signature"
            }
        }
        """#.utf8)

        let session = try JSONDecoder().decode(CameraPlaybackSession.self, from: payload)

        XCTAssertEqual(session.sessionID, "b733fb03-6288-48a9-a1b4-e57fd1859b13")
        XCTAssertEqual(session.mediaPath, "live/edge-042714be475b91da/28")
        XCTAssertEqual(session.privacyMode, .skeleton)
        XCTAssertNil(session.minimumPrivacyMode)
        XCTAssertEqual(session.displayTransport, CameraDisplayTransport.whepH264)
        XCTAssertEqual(session.compositionOwner, "edge")
    }

    func testParsesMediaMTXICEServerLinks() throws {
        let header = #"<stun:stun.example.com:3478>; rel="ice-server", <turn:turn.example.com:3478?transport=udp>; rel="ice-server"; username="family\"1"; credential="secret\\value"; credential-type="password""#

        let servers = try WHEPSignalingClient.parseICEServers(header)

        XCTAssertEqual(servers, [
            WHEPICEServer(urls: ["stun:stun.example.com:3478"], username: "", credential: ""),
            WHEPICEServer(
                urls: ["turn:turn.example.com:3478?transport=udp"],
                username: "family\"1",
                credential: "secret\\value"
            ),
        ])
    }

    func testDiscoversICEWithBearerAuthorization() async throws {
        WHEPURLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "OPTIONS")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer m1.signed")
            return (
                HTTPURLResponse(
                    url: request.url!,
                    statusCode: 204,
                    httpVersion: nil,
                    headerFields: ["Link": #"<stun:stun.example.com:3478>; rel="ice-server""#]
                )!,
                Data()
            )
        }
        let client = WHEPSignalingClient(session: makeSession())

        let servers = try await client.discoverICEServers(for: playback())

        XCTAssertEqual(servers.first?.urls, ["stun:stun.example.com:3478"])
    }

    func testCreatesAndDeletesWHEPResource() async throws {
        WHEPURLProtocolStub.handler = { request in
            switch request.httpMethod {
            case "POST":
                XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer m1.signed")
                XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/sdp")
                XCTAssertEqual(String(data: try XCTUnwrap(requestBody(request)), encoding: .utf8), "v=0\r\n")
                return (
                    HTTPURLResponse(
                        url: request.url!,
                        statusCode: 201,
                        httpVersion: nil,
                        headerFields: ["Location": "session/reader-1"]
                    )!,
                    Data("v=0\r\na=answer\r\n".utf8)
                )
            case "DELETE":
                XCTAssertEqual(request.url?.absoluteString, "https://media.example.com/media/live/box-1/2/session/reader-1")
                XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer m1.signed")
                return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data())
            default:
                throw URLError(.badServerResponse)
            }
        }
        let client = WHEPSignalingClient(session: makeSession())

        let resource = try await client.createResource(playback: playback(), offerSDP: "v=0\r\n")
        XCTAssertEqual(resource.answerSDP, "v=0\r\na=answer\r\n")
        XCTAssertEqual(
            resource.resourceURL.absoluteString,
            "https://media.example.com/media/live/box-1/2/session/reader-1"
        )
        await client.deleteResource(resource.resourceURL, playback: playback())
        XCTAssertEqual(WHEPURLProtocolStub.requests.map(\.httpMethod), ["POST", "DELETE"])
    }

    func testPatchesMediaMTXWithAuthenticatedTrickleICECandidates() async throws {
        let offer = try WHEPOffer(sdp: """
        v=0\r
        a=ice-ufrag:localUfrag\r
        a=ice-pwd:localPassword\r
        m=video 9 UDP/TLS/RTP/SAVPF 96\r
        a=mid:video0\r
        """)
        let candidate = WHEPLocalCandidate(
            sdp: "candidate:1 1 UDP 2130706431 192.0.2.10 50000 typ host",
            mediaLineIndex: 0
        )
        WHEPURLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "PATCH")
            XCTAssertEqual(request.url?.absoluteString, "https://media.example.com/media/live/box-1/2/whep/reader-1")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer m1.signed")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/trickle-ice-sdpfrag")
            XCTAssertEqual(request.value(forHTTPHeaderField: "If-Match"), "*")
            XCTAssertEqual(
                String(data: try XCTUnwrap(requestBody(request)), encoding: .utf8),
                "a=ice-ufrag:localUfrag\r\na=ice-pwd:localPassword\r\n"
                    + "m=video 9 UDP/TLS/RTP/SAVPF 96\r\na=mid:0\r\n"
                    + "a=candidate:1 1 UDP 2130706431 192.0.2.10 50000 typ host\r\n"
            )
            return (HTTPURLResponse(url: request.url!, statusCode: 204, httpVersion: nil, headerFields: nil)!, Data())
        }
        let client = WHEPSignalingClient(session: makeSession())

        try await client.addCandidates(
            [candidate],
            offer: offer,
            resourceURL: URL(string: "https://media.example.com/media/live/box-1/2/whep/reader-1")!,
            playback: playback()
        )

        XCTAssertEqual(WHEPURLProtocolStub.requests.map(\.httpMethod), ["PATCH"])
    }

    func testCandidateFragmentRejectsCrossMediaAndInjectedCandidates() throws {
        let offer = try WHEPOffer(sdp: """
        v=0\r
        a=ice-ufrag:localUfrag\r
        a=ice-pwd:localPassword\r
        m=video 9 UDP/TLS/RTP/SAVPF 96\r
        """)

        XCTAssertThrowsError(try offer.candidateFragment([
            WHEPLocalCandidate(sdp: "candidate:1 1 UDP 1 192.0.2.1 9 typ host", mediaLineIndex: 1),
        ]))
        XCTAssertThrowsError(try offer.candidateFragment([
            WHEPLocalCandidate(sdp: "candidate:1 1 UDP 1 192.0.2.1 9 typ host\r\na=sendrecv", mediaLineIndex: 0),
        ]))
    }

    func testCandidateFragmentKeepsMediaOrderAndCandidateOrder() throws {
        let offer = try WHEPOffer(sdp: """
        v=0\r
        a=ice-ufrag:u1\r
        a=ice-pwd:p1\r
        m=video 9 UDP/TLS/RTP/SAVPF 96\r
        m=audio 9 UDP/TLS/RTP/SAVPF 111\r
        """)
        let fragment = try offer.candidateFragment([
            WHEPLocalCandidate(sdp: "candidate:v1 1 UDP 3 192.0.2.1 1000 typ host", mediaLineIndex: 0),
            WHEPLocalCandidate(sdp: "candidate:a1 1 UDP 2 192.0.2.2 2000 typ host", mediaLineIndex: 1),
            WHEPLocalCandidate(sdp: "candidate:v2 1 TCP 1 192.0.2.3 3000 typ relay", mediaLineIndex: 0),
        ])

        XCTAssertEqual(
            fragment,
            "a=ice-ufrag:u1\r\na=ice-pwd:p1\r\n"
                + "m=video 9 UDP/TLS/RTP/SAVPF 96\r\na=mid:0\r\n"
                + "a=candidate:v1 1 UDP 3 192.0.2.1 1000 typ host\r\n"
                + "a=candidate:v2 1 TCP 1 192.0.2.3 3000 typ relay\r\n"
                + "m=audio 9 UDP/TLS/RTP/SAVPF 111\r\na=mid:1\r\n"
                + "a=candidate:a1 1 UDP 2 192.0.2.2 2000 typ host\r\n"
        )
    }

    func testRejectsNonCreatedWHEPResponse() async {
        WHEPURLProtocolStub.handler = { request in
            (
                HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!,
                Data("v=0\r\n".utf8)
            )
        }
        let client = WHEPSignalingClient(session: makeSession())

        do {
            _ = try await client.createResource(playback: playback(), offerSDP: "v=0\r\n")
            XCTFail("Expected non-201 response to fail")
        } catch let APIError.server(statusCode, _) {
            XCTAssertEqual(statusCode, 200)
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }

    func testRejectsCrossOriginResourceLocation() async {
        WHEPURLProtocolStub.handler = { request in
            (
                HTTPURLResponse(
                    url: request.url!,
                    statusCode: 201,
                    httpVersion: nil,
                    headerFields: ["Location": "https://other.example.com/session/reader-1"]
                )!,
                Data("v=0\r\n".utf8)
            )
        }
        let client = WHEPSignalingClient(session: makeSession())

        do {
            _ = try await client.createResource(playback: playback(), offerSDP: "v=0\r\n")
            XCTFail("Expected cross-origin resource to fail")
        } catch let error as APIError {
            XCTAssertEqual(error, .invalidResponse)
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }

    private func playback() -> CameraPlaybackSession {
        CameraPlaybackSession(
            sessionID: "media-session-1",
            expiresAt: "2026-08-04T12:00:00Z",
            whepURL: URL(string: "https://media.example.com/media/live/box-1/2/whep")!,
            authorization: .init(scheme: "Bearer", token: "m1.signed"),
            mediaPath: "live/box-1/2",
            privacyMode: .skeleton,
            minimumPrivacyMode: .skeleton,
            displayTransport: CameraDisplayTransport.whepH264,
            compositionOwner: "edge"
        )
    }

    private func makeSession() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [WHEPURLProtocolStub.self]
        return URLSession(configuration: configuration)
    }
}

private func requestBody(_ request: URLRequest) -> Data? {
    if let body = request.httpBody { return body }
    guard let stream = request.httpBodyStream else { return nil }
    stream.open()
    defer { stream.close() }
    var output = Data()
    var buffer = [UInt8](repeating: 0, count: 4096)
    while stream.hasBytesAvailable {
        let count = stream.read(&buffer, maxLength: buffer.count)
        if count <= 0 { break }
        output.append(buffer, count: count)
    }
    return output
}

private final class WHEPURLProtocolStub: URLProtocol, @unchecked Sendable {
    static var handler: (@Sendable (URLRequest) async throws -> (HTTPURLResponse, Data))?
    static var requests: [URLRequest] = []

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.requests.append(request)
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
