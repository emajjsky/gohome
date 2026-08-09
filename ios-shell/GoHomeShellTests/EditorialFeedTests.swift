import XCTest
@testable import GoHomeShell

final class EditorialFeedTests: XCTestCase {
    func testRemoteImagesUseTheApprovedServerProxy() throws {
        let baseURL = try XCTUnwrap(URL(string: "https://gohome.example.com"))
        let url = try XCTUnwrap(proxiedContentImageURL("https://images.example.com/photo.jpg", baseURL: baseURL))
        let components = try XCTUnwrap(URLComponents(url: url, resolvingAgainstBaseURL: false))
        XCTAssertEqual(components.path, "/api/v1/content/image")
        XCTAssertEqual(components.queryItems?.first?.value, "https://images.example.com/photo.jpg")
        XCTAssertNil(proxiedContentImageURL("http://unsafe.example.com/photo.jpg", baseURL: baseURL))
    }

    func testPolicyRequiresHTTPSSourceTitleCategoryAndPublisher() {
        let valid = article(id: "1")
        let invalidURL = article(id: "2", sourceURL: "http://example.com/a")
        let missingSource = article(id: "3", sourceName: "")
        let missingCategory = article(id: "4", category: "")

        XCTAssertEqual(HomeArticlePolicy.visibleArticles([valid, invalidURL, missingSource, missingCategory]).map(\.id), ["1"])
    }

    func testHouseholdIncidentIsNotEditorialContent() {
        XCTAssertTrue(HomeArticlePolicy.visibleArticles([article(id: "1", category: "incident")]).isEmpty)
        XCTAssertTrue(HomeArticlePolicy.visibleArticles([article(id: "2", category: "安全事件")]).isEmpty)
    }

    func testOfficialAntiFraudEducationCanRemainEditorial() {
        let education = article(id: "1", category: "防诈骗", sourceName: "公安部刑侦局")
        XCTAssertEqual(HomeArticlePolicy.visibleArticles([education]).map(\.id), ["1"])
    }

    func testEditorialCompositionPromotesOneArticleWithoutDuplicatingIt() {
        let articles = [article(id: "lead"), article(id: "second"), article(id: "third")]

        XCTAssertEqual(HomeArticleComposition.featured(articles)?.id, "lead")
        XCTAssertEqual(HomeArticleComposition.remaining(articles).map(\.id), ["second", "third"])
        XCTAssertNil(HomeArticleComposition.featured([]))
    }

    func testLocalFallbackImagesAreStableAndDistributedAcrossArticles() {
        let articles = (1...7).map { article(id: "article-\($0)") }
        let firstPass = articles.map(HomeArticleComposition.localImageName)
        let secondPass = articles.map(HomeArticleComposition.localImageName)
        let assignments = HomeArticleComposition.localImageAssignments(Array(articles.prefix(6)))

        XCTAssertEqual(firstPass, secondPass)
        XCTAssertGreaterThanOrEqual(Set(firstPass).count, 5)
        XCTAssertEqual(Set(assignments.values).count, 6)
        XCTAssertFalse(assignments.values.contains("memory-family-dinner"))
    }

    func testOnlyFirstArticleUsesADuplicatedRemoteImage() {
        let articles = [
            article(id: "first", imageURL: "https://images.example.com/shared.jpg"),
            article(id: "second", imageURL: "https://images.example.com/shared.jpg"),
            article(id: "third", imageURL: "https://images.example.com/unique.jpg"),
            article(id: "empty", imageURL: ""),
        ]

        XCTAssertEqual(
            HomeArticleComposition.remoteImageArticleIDs(articles),
            Set(["first", "third"])
        )
    }

    private func article(
        id: String,
        category: String = "本地",
        title: String = "城市公园本周开放夜游",
        sourceName: String = "城市发布",
        sourceURL: String = "https://example.com/a",
        imageURL: String = ""
    ) -> HomeArticle {
        HomeArticle(
            id: id,
            category: category,
            title: title,
            summary: "",
            imageURL: imageURL,
            sourceName: sourceName,
            sourceURL: sourceURL,
            publishedAt: nil
        )
    }
}
