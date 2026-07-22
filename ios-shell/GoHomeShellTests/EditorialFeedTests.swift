import XCTest
@testable import GoHomeShell

final class EditorialFeedTests: XCTestCase {
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

    private func article(
        id: String,
        category: String = "本地",
        title: String = "城市公园本周开放夜游",
        sourceName: String = "城市发布",
        sourceURL: String = "https://example.com/a"
    ) -> HomeArticle {
        HomeArticle(
            id: id,
            category: category,
            title: title,
            summary: "",
            imageURL: "",
            sourceName: sourceName,
            sourceURL: sourceURL,
            publishedAt: nil
        )
    }
}
