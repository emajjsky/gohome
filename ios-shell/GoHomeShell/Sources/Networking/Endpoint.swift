import Foundation

enum HTTPMethod: String, Sendable {
    case get = "GET"
    case post = "POST"
    case put = "PUT"
    case patch = "PATCH"
    case delete = "DELETE"
}

struct Endpoint<Response: Decodable>: @unchecked Sendable {
    let method: HTTPMethod
    let path: String
    let queryItems: [URLQueryItem]
    let body: Data?
    let etag: String?
    let decoder: JSONDecoder

    init(
        method: HTTPMethod = .get,
        path: String,
        queryItems: [URLQueryItem] = [],
        body: Data? = nil,
        etag: String? = nil,
        decoder: JSONDecoder = JSONDecoder()
    ) {
        self.method = method
        self.path = path
        self.queryItems = queryItems
        self.body = body
        self.etag = etag
        self.decoder = decoder
    }

    func request(baseURL: URL) throws -> URLRequest {
        guard var components = URLComponents(
            url: baseURL.appendingPathComponent(path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))),
            resolvingAgainstBaseURL: false
        ) else {
            throw APIError.invalidResponse
        }
        if !queryItems.isEmpty { components.queryItems = queryItems }
        guard let url = components.url else { throw APIError.invalidResponse }
        var request = URLRequest(url: url)
        request.httpMethod = method.rawValue
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if body != nil { request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        if let etag { request.setValue(etag, forHTTPHeaderField: "If-None-Match") }
        return request
    }
}

extension Endpoint {
    static func jsonBody<Body: Encodable>(
        method: HTTPMethod,
        path: String,
        body: Body,
        queryItems: [URLQueryItem] = []
    ) throws -> Endpoint<Response> {
        Endpoint(method: method, path: path, queryItems: queryItems, body: try JSONEncoder().encode(body))
    }
}
