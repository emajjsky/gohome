import Foundation

actor APIClient {
    typealias TokenProvider = @Sendable () async -> String?

    nonisolated let baseURL: URL
    private let session: URLSession
    private let tokenProvider: TokenProvider

    init(baseURL: URL, session: URLSession = .shared, token: @escaping TokenProvider = { nil }) {
        self.baseURL = baseURL
        self.session = session
        self.tokenProvider = token
    }

    func send<Response: Decodable>(_ endpoint: Endpoint<Response>) async throws -> Response {
        var request = try endpoint.request(baseURL: baseURL)
        if let token = await tokenProvider(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (data, response) = try await perform(request)
        guard let httpResponse = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        if httpResponse.statusCode == 304 {
            throw APIError.notModified(etag: httpResponse.value(forHTTPHeaderField: "ETag"))
        }
        if httpResponse.statusCode == 401 { throw APIError.unauthorized }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw APIError.server(
                statusCode: httpResponse.statusCode,
                detail: Self.serverDetail(from: data, fallback: HTTPURLResponse.localizedString(forStatusCode: httpResponse.statusCode))
            )
        }
        do {
            return try endpoint.decoder.decode(Response.self, from: data)
        } catch {
            throw APIError.decoding(error.localizedDescription)
        }
    }

    func data(path: String, queryItems: [URLQueryItem] = []) async throws -> Data {
        let endpoint = Endpoint<EmptyResponse>(path: path, queryItems: queryItems)
        var request = try endpoint.request(baseURL: baseURL)
        if let token = await tokenProvider(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (data, response) = try await perform(request)
        guard let httpResponse = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        if httpResponse.statusCode == 401 { throw APIError.unauthorized }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw APIError.server(
                statusCode: httpResponse.statusCode,
                detail: Self.serverDetail(from: data, fallback: HTTPURLResponse.localizedString(forStatusCode: httpResponse.statusCode))
            )
        }
        return data
    }

    func upload<Response: Decodable>(
        path: String,
        queryItems: [URLQueryItem],
        data: Data,
        contentType: String,
        response: Response.Type
    ) async throws -> Response {
        var request = try Endpoint<EmptyResponse>(
            method: .post,
            path: path,
            queryItems: queryItems,
            body: data
        ).request(baseURL: baseURL)
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        if let token = await tokenProvider(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (responseData, urlResponse) = try await perform(request)
        guard let httpResponse = urlResponse as? HTTPURLResponse else { throw APIError.invalidResponse }
        if httpResponse.statusCode == 401 { throw APIError.unauthorized }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw APIError.server(
                statusCode: httpResponse.statusCode,
                detail: Self.serverDetail(from: responseData, fallback: HTTPURLResponse.localizedString(forStatusCode: httpResponse.statusCode))
            )
        }
        do {
            return try JSONDecoder().decode(Response.self, from: responseData)
        } catch {
            throw APIError.decoding(error.localizedDescription)
        }
    }

    func uploadDirectly(to rawURL: String, data: Data, contentType: String) async throws {
        guard let url = URL(string: rawURL), url.scheme == "https" else { throw APIError.invalidResponse }
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.httpBody = data
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        let (responseData, response) = try await perform(request)
        guard let httpResponse = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw APIError.server(
                statusCode: httpResponse.statusCode,
                detail: Self.serverDetail(
                    from: responseData,
                    fallback: HTTPURLResponse.localizedString(forStatusCode: httpResponse.statusCode)
                )
            )
        }
    }

    private func perform(_ request: URLRequest) async throws -> (Data, URLResponse) {
        do {
            return try await session.data(for: request)
        } catch is CancellationError {
            throw CancellationError()
        } catch let error as URLError where error.code == .cancelled {
            throw CancellationError()
        }
    }

    private static func serverDetail(from data: Data, fallback: String) -> String {
        guard
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let detail = (object["detail"] as? String) ?? (object["message"] as? String),
            !detail.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else { return fallback }
        return detail
    }
}

private struct EmptyResponse: Decodable {}
