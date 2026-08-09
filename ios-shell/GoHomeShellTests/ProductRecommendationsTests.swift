import XCTest
@testable import GoHomeShell

final class ProductRecommendationsTests: XCTestCase {
    func testProductResponseDecodesOnlyRecommendationFields() throws {
        let data = Data(#"{"products":[{"id":"light-1","category":"照明与视野","brand":"品牌","name":"感应灯","summary":"夜间起身时提供柔和照明。","image_url":"https://example.com/light.jpg","source_name":"品牌官网","source_url":"https://example.com/light","suitability":["夜间照明"],"recommendation_reason":"符合夜间照明需求","disclosure":"无赞助或返佣关系","verified_at":"2026-07-22T00:00:00.000Z"}],"revision":"rev-1"}"#.utf8)

        let response = try JSONDecoder().decode(ProductRecommendationsResponse.self, from: data)

        XCTAssertEqual(response.products.first?.name, "感应灯")
        XCTAssertEqual(response.products.first?.sourceURL, "https://example.com/light")
        XCTAssertEqual(response.revision, "rev-1")
    }

    func testProductCacheIsShownBeforeRefresh() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let cache = try DiskCache(rootURL: root)
        let scope = CacheScope(userID: "user-1", familyID: "family-1")
        let cached = response(id: "cached")
        let refreshed = response(id: "fresh")
        try await cache.write(cached, key: "products", scope: scope)
        let repository = AppRepository(
            cache: cache,
            bootstrapLoader: { throw APIError.invalidResponse },
            productsLoader: { _ in refreshed }
        )
        let recorder = ProductStateRecorder()

        await repository.products(scope: scope) { await recorder.append($0) }

        let states = await recorder.values
        XCTAssertEqual(states.count, 2)
        XCTAssertEqual(states[0], Loadable(value: cached, isRefreshing: true, staleReason: nil))
        XCTAssertEqual(states[1], Loadable(value: refreshed, isRefreshing: false, staleReason: nil))
    }

    func testRecommendationPresentationSeparatesLoadingEmptyFailureAndContent() {
        let value = response(id: "content")

        XCTAssertEqual(
            ProductRecommendationsPresentationState.resolve(Loadable(value: nil, isRefreshing: true, staleReason: nil)),
            .loading
        )
        XCTAssertEqual(
            ProductRecommendationsPresentationState.resolve(Loadable(value: nil, isRefreshing: false, staleReason: "推荐暂时无法更新")),
            .failure("推荐暂时无法更新")
        )
        XCTAssertEqual(
            ProductRecommendationsPresentationState.resolve(
                Loadable(value: ProductRecommendationsResponse(products: [], revision: "empty"), isRefreshing: false, staleReason: nil)
            ),
            .empty
        )
        XCTAssertEqual(
            ProductRecommendationsPresentationState.resolve(Loadable(value: value, isRefreshing: true, staleReason: nil)),
            .content
        )
    }

    @MainActor
    func testFailedRecommendationLoadCanRetryAndPublishFreshContent() async throws {
        let fresh = response(id: "retry-success")
        let calls = ProductLoadCounter()
        let repository = AppRepository(
            cache: try DiskCache(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)),
            bootstrapLoader: { throw APIError.invalidResponse },
            productsLoader: { _ in
                if await calls.increment() == 1 { throw APIError.invalidResponse }
                return fresh
            }
        )
        let model = ProductRecommendationsViewModel(
            repository: repository,
            scope: CacheScope(userID: "user-1", familyID: "family-1")
        )

        model.start()
        try await waitUntil { model.state.staleReason != nil && !model.state.isRefreshing }
        XCTAssertEqual(ProductRecommendationsPresentationState.resolve(model.state), .failure("推荐暂时无法更新"))

        model.retry()
        try await waitUntil { model.state.value?.revision == "retry-success" }

        XCTAssertEqual(ProductRecommendationsPresentationState.resolve(model.state), .content)
        let callCount = await calls.value
        XCTAssertEqual(callCount, 2)
    }

    func testCommunityServicesResolveToRealSystemActions() throws {
        let home = HomeLocation(
            latitude: 30.2741,
            longitude: 120.1551,
            label: "拱墅区 · 杭州市",
            city: "杭州市",
            district: "拱墅区",
            source: "family_setup_phone",
            updatedAt: nil
        )
        let mealURL = try XCTUnwrap(CommunityService.meals.destinationURL(homeLocation: home))
        let mealComponents = try XCTUnwrap(URLComponents(url: mealURL, resolvingAgainstBaseURL: false))
        XCTAssertEqual(mealComponents.host, "maps.apple.com")
        XCTAssertEqual(mealComponents.queryItems?.first(where: { $0.name == "q" })?.value, "社区助餐")
        XCTAssertEqual(mealComponents.queryItems?.first(where: { $0.name == "ll" })?.value, "30.2741,120.1551")
        XCTAssertEqual(CommunityService.emergency.destinationURL(homeLocation: home)?.absoluteString, "tel://120")
        XCTAssertNil(CommunityService.meals.destinationURL(homeLocation: nil))
    }

    @MainActor
    func testCancelledRecommendationLoadCannotPublishLateResponse() async throws {
        let original = response(id: "original")
        let late = response(id: "late")
        let repository = AppRepository(
            cache: try DiskCache(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)),
            bootstrapLoader: { throw APIError.invalidResponse },
            productsLoader: { _ in
                try? await Task.sleep(nanoseconds: 100_000_000)
                return late
            }
        )
        let model = ProductRecommendationsViewModel(
            repository: repository,
            scope: CacheScope(userID: "user-1", familyID: "family-1"),
            seed: original
        )

        model.start()
        try await waitUntil { model.state.isRefreshing }
        model.cancelInFlightLoad()
        try await Task.sleep(nanoseconds: 150_000_000)

        XCTAssertEqual(model.state.value, original)
        XCTAssertFalse(model.state.isRefreshing)
        XCTAssertNil(model.state.staleReason)
    }

    @MainActor
    func testRecommendationLoadRestartsAfterLifecycleCancellation() async throws {
        let fresh = response(id: "fresh")
        let cancelled = response(id: "cancelled")
        let calls = ProductLoadCounter()
        let repository = AppRepository(
            cache: try DiskCache(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)),
            bootstrapLoader: { throw APIError.invalidResponse },
            productsLoader: { _ in
                let count = await calls.increment()
                try? await Task.sleep(nanoseconds: 80_000_000)
                return count == 1 ? cancelled : fresh
            }
        )
        let model = ProductRecommendationsViewModel(
            repository: repository,
            scope: CacheScope(userID: "user-1", familyID: "family-1")
        )

        model.start()
        try await waitUntil { model.state.isRefreshing }
        model.cancelInFlightLoad()
        try await Task.sleep(nanoseconds: 120_000_000)
        model.start()
        try await waitUntil { model.state.value?.revision == "fresh" }

        let callCount = await calls.value
        XCTAssertEqual(callCount, 2)
        XCTAssertEqual(model.state.value, fresh)
        XCTAssertFalse(model.state.isRefreshing)
    }

    func testCommunityLocationUsesProfileFixedHomeWithoutHomePageData() throws {
        let elder = try elderProfile(latitude: 30.2146, longitude: 120.1573)

        let location = try XCTUnwrap(CommunityHomeLocation.resolve(elder: elder))

        XCTAssertEqual(location.latitude, 30.2146)
        XCTAssertEqual(location.longitude, 120.1573)
        XCTAssertEqual(location.label, "西湖区 · 杭州市")
        XCTAssertEqual(location.source, "profile")
    }

    func testCommunityLookupCannotUsePhoneDistanceCoordinates() throws {
        let elder = try elderProfile(latitude: 30.2146, longitude: 120.1573)
        let phoneDistance = HomeDistance(
            meters: 8_600,
            travelMinutes: 24,
            userLatitude: 31.2304,
            userLongitude: 121.4737,
            homeLatitude: 30.2146,
            homeLongitude: 120.1573
        )

        let location = try XCTUnwrap(CommunityHomeLocation.resolve(elder: elder))
        let url = try XCTUnwrap(CommunityService.clinic.destinationURL(homeLocation: location))
        let coordinates = try XCTUnwrap(URLComponents(url: url, resolvingAgainstBaseURL: false))
            .queryItems?.first(where: { $0.name == "ll" })?.value

        XCTAssertEqual(coordinates, "30.2146,120.1573")
        XCTAssertNotEqual(coordinates, "\(phoneDistance.userLatitude!),\(phoneDistance.userLongitude!)")
    }

    private func response(id: String) -> ProductRecommendationsResponse {
        ProductRecommendationsResponse(
            products: [ProductRecommendation(
                id: id,
                category: "照明与视野",
                brand: "品牌",
                name: "感应灯",
                summary: "夜间起身时提供柔和照明。",
                imageURL: "https://example.com/light.jpg",
                sourceName: "品牌官网",
                sourceURL: "https://example.com/light",
                suitability: ["夜间照明"],
                recommendationReason: "符合夜间照明需求",
                disclosure: "无赞助或返佣关系",
                verifiedAt: "2026-07-22T00:00:00.000Z"
            )],
            revision: id
        )
    }

    private func elderProfile(latitude: Double, longitude: Double) throws -> ElderProfile {
        try JSONDecoder().decode(ElderProfile.self, from: Data("""
        {"id":"elder-profile-1","elder_id":"elder-1","display_name":"家人","relationship":"父亲",
         "city":"杭州市","district":"西湖区","home_latitude":\(latitude),"home_longitude":\(longitude),
         "home_location_label":"西湖区 · 杭州市"}
        """.utf8))
    }
}

private actor ProductStateRecorder {
    private(set) var values: [Loadable<ProductRecommendationsResponse>] = []
    func append(_ value: Loadable<ProductRecommendationsResponse>) { values.append(value) }
}

private actor ProductLoadCounter {
    private(set) var value = 0

    func increment() -> Int {
        value += 1
        return value
    }
}

@MainActor
private func waitUntil(
    timeoutNanoseconds: UInt64 = 1_000_000_000,
    condition: @escaping @MainActor () -> Bool
) async throws {
    let deadline = DispatchTime.now().uptimeNanoseconds + timeoutNanoseconds
    while !condition() {
        if DispatchTime.now().uptimeNanoseconds >= deadline {
            XCTFail("Timed out waiting for product recommendation state")
            return
        }
        try await Task.sleep(nanoseconds: 10_000_000)
    }
}
