import Foundation
import Network

struct DiscoveredBox: Codable, Equatable, Sendable, Identifiable {
    let id: String
    let name: String
    let deviceID: String
    let serialNumber: String?
    let claimCode: String?
    let host: String?
    let port: UInt16?
    let pairingWindowOpen: Bool

    init(
        id: String,
        name: String,
        deviceID: String,
        serialNumber: String? = nil,
        claimCode: String? = nil,
        host: String? = nil,
        port: UInt16? = nil,
        pairingWindowOpen: Bool = true
    ) {
        self.id = id
        self.name = name
        self.deviceID = deviceID
        self.serialNumber = serialNumber
        self.claimCode = claimCode
        self.host = host
        self.port = port
        self.pairingWindowOpen = pairingWindowOpen
    }
}

@MainActor
final class BoxDiscoveryService: ObservableObject {
    @Published private(set) var boxes: [DiscoveredBox] = []
    @Published private(set) var isSearching = false

    private var browser: NWBrowser?
    private var endpoints: [String: NWEndpoint] = [:]

    func start() {
        guard !isSearching else { return }
        if ProcessInfo.processInfo.arguments.contains("-uiTestState") {
            boxes = [DiscoveredBox(id: "ui-test-box", name: "演示守护盒子", deviceID: "ui-test-box", serialNumber: "UI-TEST-BOX")]
            return
        }
        isSearching = true
        let browser = NWBrowser(for: .bonjour(type: "_gohome._tcp", domain: nil), using: .tcp)
        self.browser = browser
        browser.stateUpdateHandler = { [weak self] state in
            Task { @MainActor in
                if case .failed = state { self?.isSearching = false }
            }
        }
        browser.browseResultsChangedHandler = { [weak self] results, _ in
            Task { @MainActor in
                guard let self else { return }
                let liveEndpoints = Set(results.map { String(describing: $0.endpoint) })
                self.endpoints = self.endpoints.filter { liveEndpoints.contains(String(describing: $0.value)) }
                self.boxes.removeAll { box in
                    guard let endpoint = self.endpoints[box.deviceID] else { return true }
                    return !liveEndpoints.contains(String(describing: endpoint))
                }
                for result in results { self.probe(result) }
            }
        }
        browser.start(queue: .main)
    }

    func stop() {
        browser?.cancel()
        browser = nil
        isSearching = false
        endpoints.removeAll()
        boxes.removeAll()
    }

    func supportsLocalPairing(_ box: DiscoveredBox) -> Bool {
        endpoints[box.deviceID] != nil
    }

    func pair(box: DiscoveredBox, code: String, returnURL: URL) async throws {
        guard box.pairingWindowOpen else { throw BoxDiscoveryError.pairingWindowClosed }
        guard let endpoint = endpoints[box.deviceID] else { throw BoxDiscoveryError.endpointUnavailable }
        var components = URLComponents()
        components.queryItems = [
            URLQueryItem(name: "code", value: code),
            URLQueryItem(name: "return_url", value: returnURL.absoluteString),
        ]
        let query = components.percentEncodedQuery.map { "?\($0)" } ?? ""
        let response = try await LANHTTPClient.get(endpoint: endpoint, path: "/pair\(query)")
        guard response.statusCode == 303 || response.statusCode == 200 else {
            throw BoxDiscoveryError.pairingFailed(response.statusCode)
        }
    }

    deinit { browser?.cancel() }

    private func probe(_ result: NWBrowser.Result) {
        let endpoint = result.endpoint
        Task {
            do {
                let response = try await LANHTTPClient.get(endpoint: endpoint, path: "/api/lan/discovery")
                guard response.statusCode == 200 else { return }
                let payload = try JSONDecoder().decode(LANDiscoveryPayload.self, from: response.body)
                let box = DiscoveredBox(
                    id: payload.deviceID,
                    name: payload.deviceName,
                    deviceID: payload.deviceID,
                    host: payload.lanIP,
                    port: payload.apiPort,
                    pairingWindowOpen: payload.pairingWindowOpen
                )
                endpoints[box.deviceID] = endpoint
                boxes.removeAll { $0.deviceID == box.deviceID }
                boxes.append(box)
                boxes.sort { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
            } catch {
                return
            }
        }
    }
}

private struct LANDiscoveryPayload: Decodable {
    let deviceID: String
    let deviceName: String
    let lanIP: String?
    let apiPort: UInt16?
    let pairingWindowOpen: Bool

    enum CodingKeys: String, CodingKey {
        case deviceID = "device_id"
        case deviceName = "device_name"
        case lanIP = "lan_ip"
        case apiPort = "api_port"
        case pairingWindowOpen = "pairing_window_open"
    }
}

private struct LANHTTPResponse: Sendable {
    let statusCode: Int
    let body: Data
}

private enum LANHTTPClient {
    static func get(endpoint: NWEndpoint, path: String) async throws -> LANHTTPResponse {
        try await withCheckedThrowingContinuation { continuation in
            let connection = NWConnection(to: endpoint, using: .tcp)
            let request = LANRequestState(connection: connection, continuation: continuation)
            connection.stateUpdateHandler = { state in
                switch state {
                case .ready:
                    let message = "GET \(path) HTTP/1.1\r\nHost: gohome.local\r\nAccept: application/json\r\nConnection: close\r\n\r\n"
                    connection.send(content: Data(message.utf8), completion: .contentProcessed { error in
                        if let error { request.finish(.failure(error)) } else { request.receive() }
                    })
                case let .failed(error):
                    request.finish(.failure(error))
                case .cancelled:
                    request.finish(.failure(CancellationError()))
                default:
                    break
                }
            }
            connection.start(queue: .global(qos: .userInitiated))
            DispatchQueue.global().asyncAfter(deadline: .now() + 8) {
                request.finish(.failure(BoxDiscoveryError.timeout))
            }
        }
    }
}

private final class LANRequestState: @unchecked Sendable {
    private let lock = NSLock()
    private let connection: NWConnection
    private let continuation: CheckedContinuation<LANHTTPResponse, Error>
    private var buffer = Data()
    private var completed = false

    init(connection: NWConnection, continuation: CheckedContinuation<LANHTTPResponse, Error>) {
        self.connection = connection
        self.continuation = continuation
    }

    func receive() {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 64 * 1024) { [weak self] data, _, isComplete, error in
            guard let self else { return }
            if let data { self.append(data) }
            if let error {
                self.finish(.failure(error))
            } else if isComplete {
                self.finish(Result { try Self.parse(self.snapshot()) })
            } else {
                self.receive()
            }
        }
    }

    func finish(_ result: Result<LANHTTPResponse, Error>) {
        lock.lock()
        guard !completed else { lock.unlock(); return }
        completed = true
        lock.unlock()
        connection.cancel()
        continuation.resume(with: result)
    }

    private func append(_ data: Data) {
        lock.lock()
        buffer.append(data)
        lock.unlock()
    }

    private func snapshot() -> Data {
        lock.lock()
        defer { lock.unlock() }
        return buffer
    }

    private static func parse(_ data: Data) throws -> LANHTTPResponse {
        let separator = Data("\r\n\r\n".utf8)
        guard let range = data.range(of: separator),
              let header = String(data: data[..<range.lowerBound], encoding: .utf8),
              let statusLine = header.split(separator: "\r\n").first,
              let statusCode = Int(statusLine.split(separator: " ").dropFirst().first ?? "")
        else { throw BoxDiscoveryError.invalidResponse }
        return LANHTTPResponse(statusCode: statusCode, body: Data(data[range.upperBound...]))
    }
}

enum BoxDiscoveryError: LocalizedError {
    case endpointUnavailable
    case pairingWindowClosed
    case pairingFailed(Int)
    case invalidResponse
    case timeout

    var errorDescription: String? {
        switch self {
        case .endpointUnavailable: return "盒子已离开局域网，请重新搜索。"
        case .pairingWindowClosed: return "安全配对时间已结束，请重启盒子后重试。"
        case let .pairingFailed(status): return "盒子绑定失败（\(status)），请检查网络后重试。"
        case .invalidResponse: return "盒子返回了无法识别的数据。"
        case .timeout: return "连接盒子超时，请确认手机和盒子在同一 Wi-Fi。"
        }
    }
}
