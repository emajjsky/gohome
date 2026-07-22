import Foundation

actor AppRepository {
    typealias BootstrapLoader = @Sendable () async throws -> BootstrapResponse
    typealias BootstrapUpdate = @Sendable (Loadable<BootstrapResponse>) async -> Void
    typealias HomeLoader = @Sendable (String) async throws -> HomeResponse
    typealias HomeUpdate = @Sendable (Loadable<HomeResponse>) async -> Void

    private let cache: DiskCache
    private let bootstrapLoader: BootstrapLoader
    private let homeLoader: HomeLoader
    private var bootstrapTasks: [CacheScope: Task<BootstrapResponse, Error>] = [:]
    private var homeTasks: [CacheScope: Task<HomeResponse, Error>] = [:]

    init(
        cache: DiskCache,
        bootstrapLoader: @escaping BootstrapLoader,
        homeLoader: @escaping HomeLoader = { _ in throw APIError.invalidResponse }
    ) {
        self.cache = cache
        self.bootstrapLoader = bootstrapLoader
        self.homeLoader = homeLoader
    }

    func fetchBootstrap() async throws -> BootstrapResponse {
        try await bootstrapLoader()
    }

    func cacheBootstrap(_ value: BootstrapResponse, scope: CacheScope) async {
        try? await cache.write(value, key: "bootstrap", scope: scope, ttl: 24 * 60 * 60)
    }

    func bootstrap(scope: CacheScope, onUpdate: @escaping BootstrapUpdate) async {
        let cached = try? await cache.read(BootstrapResponse.self, key: "bootstrap", scope: scope)
        await onUpdate(Loadable(value: cached, isRefreshing: true, staleReason: nil))

        do {
            let refreshed = try await refreshBootstrap(scope: scope)
            try await cache.write(refreshed, key: "bootstrap", scope: scope, ttl: 24 * 60 * 60)
            await onUpdate(Loadable(value: refreshed, isRefreshing: false, staleReason: nil))
        } catch is CancellationError {
            await onUpdate(Loadable(value: cached, isRefreshing: false, staleReason: nil))
        } catch {
            await onUpdate(Loadable(
                value: cached,
                isRefreshing: false,
                staleReason: cached == nil ? error.localizedDescription : "暂时无法刷新，正在显示上次内容"
            ))
        }
    }

    func home(scope: CacheScope, onUpdate: @escaping HomeUpdate) async {
        let cached = try? await cache.read(HomeResponse.self, key: "home", scope: scope)
        await onUpdate(Loadable(value: cached, isRefreshing: true, staleReason: nil))

        do {
            let refreshed = try await refreshHome(scope: scope)
            try await cache.write(refreshed, key: "home", scope: scope, ttl: 6 * 60 * 60)
            await onUpdate(Loadable(value: refreshed, isRefreshing: false, staleReason: nil))
        } catch is CancellationError {
            await onUpdate(Loadable(value: cached, isRefreshing: false, staleReason: nil))
        } catch {
            await onUpdate(Loadable(
                value: cached,
                isRefreshing: false,
                staleReason: cached == nil ? error.localizedDescription : "暂时无法更新"
            ))
        }
    }

    private func refreshBootstrap(scope: CacheScope) async throws -> BootstrapResponse {
        if let task = bootstrapTasks[scope] { return try await task.value }
        let task = Task { try await bootstrapLoader() }
        bootstrapTasks[scope] = task
        defer { bootstrapTasks[scope] = nil }
        return try await task.value
    }

    private func refreshHome(scope: CacheScope) async throws -> HomeResponse {
        if let task = homeTasks[scope] { return try await task.value }
        let task = Task { try await homeLoader(scope.familyID) }
        homeTasks[scope] = task
        defer { homeTasks[scope] = nil }
        return try await task.value
    }
}
