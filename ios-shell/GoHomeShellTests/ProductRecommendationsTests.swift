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
}

private actor ProductStateRecorder {
    private(set) var values: [Loadable<ProductRecommendationsResponse>] = []
    func append(_ value: Loadable<ProductRecommendationsResponse>) { values.append(value) }
}
