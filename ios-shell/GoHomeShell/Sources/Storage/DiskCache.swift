import Foundation

struct CacheScope: Hashable, Codable, Sendable {
    let userID: String
    let familyID: String
}

actor DiskCache {
    nonisolated static let fileProtection = FileProtectionType.completeUnlessOpen

    private struct Entry<Value: Codable>: Codable {
        let writtenAt: Date
        let expiresAt: Date
        let value: Value
    }

    private let rootURL: URL
    private let clock: @Sendable () -> Date
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    init(rootURL: URL? = nil, clock: @escaping @Sendable () -> Date = Date.init) throws {
        let baseURL = rootURL ?? FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        self.rootURL = baseURL.appendingPathComponent("GoHomeNativeCache", isDirectory: true)
        self.clock = clock
        encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        try FileManager.default.createDirectory(
            at: self.rootURL,
            withIntermediateDirectories: true,
            attributes: [.protectionKey: Self.fileProtection]
        )
    }

    func read<Value: Codable>(_ type: Value.Type, key: String, scope: CacheScope) throws -> Value? {
        let url = fileURL(key: key, scope: scope)
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        let entry = try decoder.decode(Entry<Value>.self, from: Data(contentsOf: url))
        guard entry.expiresAt > clock() else {
            try? FileManager.default.removeItem(at: url)
            return nil
        }
        return entry.value
    }

    func write<Value: Codable>(
        _ value: Value,
        key: String,
        scope: CacheScope,
        ttl: TimeInterval = 24 * 60 * 60
    ) throws {
        let directory = scopeURL(scope)
        try FileManager.default.createDirectory(
            at: directory,
            withIntermediateDirectories: true,
            attributes: [.protectionKey: Self.fileProtection]
        )
        let now = clock()
        let data = try encoder.encode(Entry(writtenAt: now, expiresAt: now.addingTimeInterval(max(1, ttl)), value: value))
        try data.write(to: fileURL(key: key, scope: scope), options: [.atomic, .completeFileProtectionUnlessOpen])
    }

    func clear(scope: CacheScope) throws {
        let url = scopeURL(scope)
        if FileManager.default.fileExists(atPath: url.path) { try FileManager.default.removeItem(at: url) }
    }

    func clearAll() throws {
        if FileManager.default.fileExists(atPath: rootURL.path) { try FileManager.default.removeItem(at: rootURL) }
        try FileManager.default.createDirectory(
            at: rootURL,
            withIntermediateDirectories: true,
            attributes: [.protectionKey: Self.fileProtection]
        )
    }

    private func scopeURL(_ scope: CacheScope) -> URL {
        rootURL
            .appendingPathComponent(component(scope.userID), isDirectory: true)
            .appendingPathComponent(component(scope.familyID), isDirectory: true)
    }

    private func fileURL(key: String, scope: CacheScope) -> URL {
        scopeURL(scope).appendingPathComponent("\(component(key)).json")
    }

    private func component(_ value: String) -> String {
        Data(value.utf8).base64EncodedString()
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "=", with: "")
    }
}
