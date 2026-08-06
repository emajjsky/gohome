import Foundation

struct WHEPLocalCandidate: Equatable, Sendable {
    let sdp: String
    let mediaLineIndex: Int32
}

struct WHEPOffer: Equatable, Sendable {
    let sdp: String
    let iceUfrag: String
    let icePassword: String
    let mediaSections: [String]

    init(sdp: String) throws {
        let lines = sdp
            .replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\r", with: "\n")
            .split(separator: "\n", omittingEmptySubsequences: true)
            .map(String.init)
        guard
            let iceUfrag = lines.first(where: { $0.hasPrefix("a=ice-ufrag:") })?.dropFirst(12),
            let icePassword = lines.first(where: { $0.hasPrefix("a=ice-pwd:") })?.dropFirst(10)
        else { throw APIError.invalidResponse }

        let mediaSections = lines.compactMap { line -> String? in
            guard line.hasPrefix("m=") else { return nil }
            return String(line.dropFirst(2))
        }
        guard
            Self.isSDPAttributeValue(String(iceUfrag)),
            Self.isSDPAttributeValue(String(icePassword)),
            !mediaSections.isEmpty,
            mediaSections.allSatisfy(Self.isSDPLineValue)
        else { throw APIError.invalidResponse }

        self.sdp = sdp
        self.iceUfrag = String(iceUfrag)
        self.icePassword = String(icePassword)
        self.mediaSections = mediaSections
    }

    func candidateFragment(_ candidates: [WHEPLocalCandidate]) throws -> String {
        guard !candidates.isEmpty else { throw APIError.invalidResponse }
        var grouped: [Int: [String]] = [:]
        for candidate in candidates {
            let index = Int(candidate.mediaLineIndex)
            guard
                mediaSections.indices.contains(index),
                Self.isCandidateLine(candidate.sdp)
            else { throw APIError.invalidResponse }
            grouped[index, default: []].append(candidate.sdp)
        }

        var fragment = "a=ice-ufrag:\(iceUfrag)\r\na=ice-pwd:\(icePassword)\r\n"
        for index in mediaSections.indices {
            guard let mediaCandidates = grouped[index] else { continue }
            fragment += "m=\(mediaSections[index])\r\na=mid:\(index)\r\n"
            for candidate in mediaCandidates {
                fragment += "a=\(candidate)\r\n"
            }
        }
        return fragment
    }

    private static func isCandidateLine(_ value: String) -> Bool {
        guard value.hasPrefix("candidate:"), isSDPLineValue(value) else { return false }
        let fields = value.split(separator: " ", omittingEmptySubsequences: true)
        guard
            fields.count >= 8,
            !fields[0].dropFirst("candidate:".count).isEmpty,
            UInt16(fields[1]) != nil,
            !fields[2].isEmpty,
            UInt32(fields[3]) != nil,
            !fields[4].isEmpty,
            UInt16(fields[5]) != nil,
            fields[6] == "typ",
            ["host", "srflx", "prflx", "relay"].contains(String(fields[7]))
        else { return false }
        return true
    }

    private static func isSDPAttributeValue(_ value: String) -> Bool {
        !value.isEmpty && !value.contains(" ") && isSDPLineValue(value)
    }

    private static func isSDPLineValue(_ value: String) -> Bool {
        !value.isEmpty && value.unicodeScalars.allSatisfy { $0.value >= 0x20 && $0.value != 0x7F }
    }
}

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

    func addCandidates(
        _ candidates: [WHEPLocalCandidate],
        offer: WHEPOffer,
        resourceURL: URL,
        playback: CameraPlaybackSession
    ) async throws {
        var request = authorizedRequest(url: resourceURL, playback: playback)
        request.httpMethod = "PATCH"
        request.timeoutInterval = 5
        request.setValue("application/trickle-ice-sdpfrag", forHTTPHeaderField: "Content-Type")
        request.setValue("*", forHTTPHeaderField: "If-Match")
        request.httpBody = Data(try offer.candidateFragment(candidates).utf8)
        let (_, response) = try await session.data(for: request)
        _ = try validatedHTTPResponse(response, allowedStatus: 204..<205)
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
