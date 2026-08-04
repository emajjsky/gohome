import Foundation

struct WHEPICEServer: Equatable, Sendable {
    let urls: [String]
    let username: String
    let credential: String
}

struct WHEPResource: Sendable {
    let answerSDP: String
    let resourceURL: URL
}

struct WHEPSignalingClient: Sendable {
    private let session: URLSession

    init(session: URLSession = .shared) {
        self.session = session
    }

    func discoverICEServers(for playback: CameraPlaybackSession) async throws -> [WHEPICEServer] {
        var request = authorizedRequest(url: playback.whepURL, playback: playback)
        request.httpMethod = "OPTIONS"
        request.timeoutInterval = 10
        let (_, response) = try await session.data(for: request)
        let http = try validatedHTTPResponse(response, allowedStatus: 200..<300)
        return try Self.parseICEServers(http.value(forHTTPHeaderField: "Link"))
    }

    func createResource(playback: CameraPlaybackSession, offerSDP: String) async throws -> WHEPResource {
        var request = authorizedRequest(url: playback.whepURL, playback: playback)
        request.httpMethod = "POST"
        request.timeoutInterval = 12
        request.setValue("application/sdp", forHTTPHeaderField: "Content-Type")
        request.setValue("application/sdp", forHTTPHeaderField: "Accept")
        request.httpBody = Data(offerSDP.utf8)
        let (data, response) = try await session.data(for: request)
        let http = try validatedHTTPResponse(response, allowedStatus: 201..<202)
        guard
            let location = http.value(forHTTPHeaderField: "Location"),
            let resourceURL = URL(string: location, relativeTo: playback.whepURL)?.absoluteURL,
            Self.isSameOrigin(resourceURL, playback.whepURL),
            !data.isEmpty,
            let answerSDP = String(data: data, encoding: .utf8),
            !answerSDP.isEmpty
        else { throw APIError.invalidResponse }
        return WHEPResource(answerSDP: answerSDP, resourceURL: resourceURL)
    }

    func deleteResource(_ resourceURL: URL, playback: CameraPlaybackSession) async {
        var request = authorizedRequest(url: resourceURL, playback: playback)
        request.httpMethod = "DELETE"
        request.timeoutInterval = 5
        _ = try? await session.data(for: request)
    }

    private func authorizedRequest(url: URL, playback: CameraPlaybackSession) -> URLRequest {
        var request = URLRequest(url: url)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue(
            "\(playback.authorization.scheme) \(playback.authorization.token)",
            forHTTPHeaderField: "Authorization"
        )
        return request
    }

    private func validatedHTTPResponse(
        _ response: URLResponse,
        allowedStatus: Range<Int>
    ) throws -> HTTPURLResponse {
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        if http.statusCode == 401 { throw APIError.unauthorized }
        guard allowedStatus.contains(http.statusCode) else {
            throw APIError.server(statusCode: http.statusCode, detail: "实时视频协商失败")
        }
        return http
    }

    static func parseICEServers(_ header: String?) throws -> [WHEPICEServer] {
        guard let header, !header.isEmpty else { return [] }
        let pattern = #"<([^>]+)>\s*;\s*rel="ice-server"(?:\s*;\s*username="((?:\\.|[^"])*)"\s*;\s*credential="((?:\\.|[^"])*)"\s*;\s*credential-type="password")?"#
        let expression = try NSRegularExpression(pattern: pattern, options: [.caseInsensitive])
        let range = NSRange(header.startIndex..<header.endIndex, in: header)
        return try expression.matches(in: header, range: range).map { match in
            guard let urlRange = Range(match.range(at: 1), in: header) else {
                throw APIError.invalidResponse
            }
            return WHEPICEServer(
                urls: [String(header[urlRange])],
                username: try decodedQuotedValue(match.range(at: 2), in: header),
                credential: try decodedQuotedValue(match.range(at: 3), in: header)
            )
        }
    }

    private static func decodedQuotedValue(_ range: NSRange, in source: String) throws -> String {
        guard range.location != NSNotFound, let swiftRange = Range(range, in: source) else { return "" }
        let json = Data("\"\(source[swiftRange])\"".utf8)
        guard let value = try? JSONDecoder().decode(String.self, from: json) else {
            throw APIError.invalidResponse
        }
        return value
    }

    private static func isSameOrigin(_ first: URL, _ second: URL) -> Bool {
        func effectivePort(_ url: URL) -> Int? {
            if let port = url.port { return port }
            if url.scheme?.lowercased() == "https" { return 443 }
            if url.scheme?.lowercased() == "http" { return 80 }
            return nil
        }
        return first.scheme?.lowercased() == second.scheme?.lowercased()
            && first.host?.lowercased() == second.host?.lowercased()
            && effectivePort(first) == effectivePort(second)
    }
}
