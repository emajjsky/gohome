import XCTest
@testable import GoHomeShell

final class AppRepositoryTests: XCTestCase {
    func testCachedBootstrapIsDeliveredBeforeNetworkRefresh() async throws {
        let fixture = try Fixture()
        try await fixture.cache.write(fixture.cached, key: "bootstrap", scope: fixture.scope)
        let loader = CountingLoader(result: .success(fixture.fresh), delayNanoseconds: 80_000_000)
        let repository = AppRepository(cache: fixture.cache) { try await loader.load() }
        let recorder = StateRecorder()

        try await repository.bootstrap(scope: fixture.scope) { await recorder.append($0) }

        let states = await recorder.values
        XCTAssertEqual(states.count, 2)
        XCTAssertEqual(states[0], Loadable(value: fixture.cached, isRefreshing: true, staleReason: nil))
        XCTAssertEqual(states[1], Loadable(value: fixture.fresh, isRefreshing: false, staleReason: nil))
    }

    func testRefreshFailurePreservesCachedContent() async throws {
        let fixture = try Fixture()
        try await fixture.cache.write(fixture.cached, key: "bootstrap", scope: fixture.scope)
        let loader = CountingLoader(result: .failure(URLError(.notConnectedToInternet)))
        let repository = AppRepository(cache: fixture.cache) { try await loader.load() }
        let recorder = StateRecorder()

        try await repository.bootstrap(scope: fixture.scope) { await recorder.append($0) }

        let recordedStates = await recorder.values
        let state = try XCTUnwrap(recordedStates.last)
        XCTAssertEqual(state.value, fixture.cached)
        XCTAssertFalse(state.isRefreshing)
        XCTAssertNotNil(state.staleReason)
    }

    func testConcurrentBootstrapCallsShareOneNetworkTask() async throws {
        let fixture = try Fixture()
        let loader = CountingLoader(result: .success(fixture.fresh), delayNanoseconds: 80_000_000)
        let repository = AppRepository(cache: fixture.cache) { try await loader.load() }
        let first = StateRecorder()
        let second = StateRecorder()

        async let firstCall: Void = repository.bootstrap(scope: fixture.scope) { await first.append($0) }
        async let secondCall: Void = repository.bootstrap(scope: fixture.scope) { await second.append($0) }
        _ = try await (firstCall, secondCall)

        let callCount = await loader.callCount
        let firstStates = await first.values
        let secondStates = await second.values
        XCTAssertEqual(callCount, 1)
        XCTAssertEqual(firstStates.last?.value, fixture.fresh)
        XCTAssertEqual(secondStates.last?.value, fixture.fresh)
    }

    func testCancelledMemoryRefreshDoesNotCommitFreshCache() async throws {
        let fixture = try Fixture()
        let cached = FamilyMemoriesResponse(memories: [], revision: "cached")
        let fresh = FamilyMemoriesResponse(memories: [], revision: "fresh")
        try await fixture.cache.write(cached, key: "memories", scope: fixture.scope)
        let loader = CancellationIgnoringMemoryLoader(result: fresh)
        let repository = AppRepository(
            cache: fixture.cache,
            bootstrapLoader: { throw APIError.invalidResponse },
            memoriesLoader: { _ in try await loader.load() }
        )
        let recorder = MemoryLoadableRecorder()
        let task = Task {
            await repository.memories(scope: fixture.scope) { await recorder.append($0) }
        }
        for _ in 0..<100 {
            if await loader.started { break }
            try await Task.sleep(nanoseconds: 2_000_000)
        }

        task.cancel()
        await task.value

        let cachedAfterCancellation = try await fixture.cache.read(
            FamilyMemoriesResponse.self,
            key: "memories",
            scope: fixture.scope
        )
        XCTAssertEqual(cachedAfterCancellation?.revision, "cached")
        let states = await recorder.values
        XCTAssertEqual(states.map(\.value?.revision), ["cached", "cached"])
        XCTAssertEqual(states.map(\.isRefreshing), [true, false])
    }

    func testUnauthorizedRefreshIsPropagatedInsteadOfPresentedAsStaleContent() async throws {
        let fixture = try Fixture()
        try await fixture.cache.write(fixture.cached, key: "bootstrap", scope: fixture.scope)
        let repository = AppRepository(cache: fixture.cache) { throw APIError.unauthorized }
        let recorder = StateRecorder()

        do {
            try await repository.bootstrap(scope: fixture.scope) { await recorder.append($0) }
            XCTFail("Expected unauthorized refresh to fail")
        } catch {
            XCTAssertEqual(error as? APIError, .unauthorized)
        }

        let states = await recorder.values
        XCTAssertEqual(states, [Loadable(value: fixture.cached, isRefreshing: true, staleReason: nil)])
    }
}

private struct Fixture {
    let root: URL
    let cache: DiskCache
    let scope = CacheScope(userID: "user-1", familyID: "family-1")
    let cached = BootstrapResponse(
        user: AppUser(id: "user-1", phone: "13800000000", displayName: "Test"),
        families: [AppFamily(id: "family-1", name: "Home", role: "creator")],
        activeFamilyID: "family-1",
        onboarding: OnboardingState(nextStep: .camera, complete: false),
        unreadCount: 1,
        revision: "cached"
    )
    let fresh = BootstrapResponse(
        user: AppUser(id: "user-1", phone: "13800000000", displayName: "Test"),
        families: [AppFamily(id: "family-1", name: "Home", role: "creator")],
        activeFamilyID: "family-1",
        onboarding: OnboardingState(nextStep: .complete, complete: true),
        unreadCount: 2,
        revision: "fresh"
    )

    init() throws {
        root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        cache = try DiskCache(rootURL: root)
    }
}

private actor CountingLoader {
    let result: Result<BootstrapResponse, Error>
    let delayNanoseconds: UInt64
    private(set) var callCount = 0

    init(result: Result<BootstrapResponse, Error>, delayNanoseconds: UInt64 = 0) {
        self.result = result
        self.delayNanoseconds = delayNanoseconds
    }

    func load() async throws -> BootstrapResponse {
        callCount += 1
        if delayNanoseconds > 0 { try await Task.sleep(nanoseconds: delayNanoseconds) }
        return try result.get()
    }
}

private actor StateRecorder {
    private(set) var values: [Loadable<BootstrapResponse>] = []
    func append(_ value: Loadable<BootstrapResponse>) { values.append(value) }
}

private actor CancellationIgnoringMemoryLoader {
    let result: FamilyMemoriesResponse
    private(set) var started = false

    init(result: FamilyMemoriesResponse) {
        self.result = result
    }

    func load() async throws -> FamilyMemoriesResponse {
        started = true
        try? await Task.sleep(nanoseconds: 80_000_000)
        return result
    }
}

private actor MemoryLoadableRecorder {
    private(set) var values: [Loadable<FamilyMemoriesResponse>] = []

    func append(_ value: Loadable<FamilyMemoriesResponse>) {
        values.append(value)
    }
}
