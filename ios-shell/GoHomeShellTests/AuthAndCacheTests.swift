import XCTest
@testable import GoHomeShell

final class AuthAndCacheTests: XCTestCase {
    private struct CachedValue: Codable, Equatable {
        let title: String
    }

    func testDemoChallengeDecodesExplicitTestCode() throws {
        let data = Data(#"{"challenge_id":"otp_test","expires_at":"2026-07-22T12:00:00.000Z","delivery":"demo","demo_code":"246810"}"#.utf8)
        let challenge = try JSONDecoder().decode(AuthChallengeResponse.self, from: data)
        XCTAssertEqual(challenge.challengeID, "otp_test")
        XCTAssertEqual(challenge.delivery, "demo")
        XCTAssertEqual(challenge.demoCode, "246810")
    }

    @MainActor
    func testAuthValidationExplainsInvalidActionsInsteadOfSilentlyReturning() {
        let client = APIClient(baseURL: URL(string: "https://example.invalid")!)
        let store = KeychainAuthStore(service: "com.gohome.family.tests.\(UUID().uuidString)")
        let viewModel = AuthViewModel(client: client, authStore: store) {}

        viewModel.phone = "138"
        viewModel.requestCode()
        XCTAssertEqual(viewModel.errorMessage, "请输入完整的 11 位手机号")

        viewModel.phone = "13800138000"
        viewModel.submit()
        XCTAssertEqual(viewModel.errorMessage, "请先获取验证码")
        XCTAssertTrue(viewModel.canRequestCode)
        XCTAssertTrue(viewModel.canSubmit)
    }

    func testKeychainTokenRoundTripAndLogoutDeletion() async throws {
        let store = KeychainAuthStore(service: "com.gohome.family.tests.\(UUID().uuidString)")
        let emptyToken = try await store.token()
        XCTAssertNil(emptyToken)
        try await store.save(token: "secret-session-token")
        let savedToken = try await store.token()
        XCTAssertEqual(savedToken, "secret-session-token")
        try await store.clear()
        let clearedToken = try await store.token()
        XCTAssertNil(clearedToken)
    }

    func testCacheSeparatesAccountsAndFamilies() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let cache = try DiskCache(rootURL: root)
        let first = CacheScope(userID: "user-a", familyID: "family-a")
        let secondAccount = CacheScope(userID: "user-b", familyID: "family-a")
        let secondFamily = CacheScope(userID: "user-a", familyID: "family-b")
        try await cache.write(CachedValue(title: "first"), key: "home", scope: first)
        let firstValue = try await cache.read(CachedValue.self, key: "home", scope: first)
        let secondAccountValue = try await cache.read(CachedValue.self, key: "home", scope: secondAccount)
        let secondFamilyValue = try await cache.read(CachedValue.self, key: "home", scope: secondFamily)
        XCTAssertEqual(firstValue, CachedValue(title: "first"))
        XCTAssertNil(secondAccountValue)
        XCTAssertNil(secondFamilyValue)
        try await cache.clear(scope: first)
        let clearedValue = try await cache.read(CachedValue.self, key: "home", scope: first)
        XCTAssertNil(clearedValue)
    }

    func testExpiredEntryIsRejectedAndRemoved() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let clock = LockedClock(Date(timeIntervalSince1970: 1_000))
        let cache = try DiskCache(rootURL: root) { clock.value() }
        let scope = CacheScope(userID: "user", familyID: "family")
        try await cache.write(CachedValue(title: "temporary"), key: "home", scope: scope, ttl: 10)
        clock.advance(by: 11)
        let expiredValue = try await cache.read(CachedValue.self, key: "home", scope: scope)
        XCTAssertNil(expiredValue)
    }

    func testDiskCacheDoesNotContainAuthenticationToken() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let cache = try DiskCache(rootURL: root)
        try await cache.write(CachedValue(title: "cached home"), key: "home", scope: CacheScope(userID: "user", familyID: "family"))
        let enumerator = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil)
        let contents = (enumerator?.allObjects as? [URL] ?? [])
            .filter { $0.pathExtension == "json" }
            .compactMap { try? String(contentsOf: $0, encoding: .utf8) }
            .joined()
        XCTAssertFalse(contents.contains("secret-session-token"))
        let cacheFile = (FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil)?.allObjects as? [URL] ?? [])
            .first { $0.pathExtension == "json" }
        XCTAssertNotNil(cacheFile)
        XCTAssertEqual(DiskCache.fileProtection, .completeUnlessOpen)
        if let cacheFile {
            let attributes = try FileManager.default.attributesOfItem(atPath: cacheFile.path)
#if targetEnvironment(simulator)
            XCTAssertNil(attributes[.protectionKey])
#else
            XCTAssertEqual(attributes[.protectionKey] as? FileProtectionType, .completeUnlessOpen)
#endif
        }
    }
}

private final class LockedClock: @unchecked Sendable {
    private let lock = NSLock()
    private var current: Date

    init(_ date: Date) {
        current = date
    }

    func value() -> Date {
        lock.lock()
        defer { lock.unlock() }
        return current
    }

    func advance(by interval: TimeInterval) {
        lock.lock()
        current = current.addingTimeInterval(interval)
        lock.unlock()
    }
}
