import Foundation

enum APIError: Error, Equatable, LocalizedError {
    case invalidResponse
    case unauthorized
    case notModified(etag: String?)
    case server(statusCode: Int, detail: String)
    case decoding(String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "服务器返回了无法识别的响应。"
        case .unauthorized:
            return "登录状态已失效，请重新登录。"
        case .notModified:
            return "内容没有变化。"
        case let .server(_, detail):
            return detail
        case .decoding:
            return "服务器数据格式暂时无法读取。"
        }
    }
}
