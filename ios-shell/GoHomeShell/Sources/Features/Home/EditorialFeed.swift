import SwiftUI

enum ArticleCategory: String, CaseIterable, Identifiable {
    case all = "全部"
    case local = "本地"
    case wellness = "生活健康"
    case culture = "文娱"
    case interests = "兴趣"

    var id: String { rawValue }

    func matches(_ article: HomeArticle) -> Bool {
        guard self != .all else { return true }
        let category = article.category.lowercased()
        switch self {
        case .all: return true
        case .local: return category.contains("本地") || category.contains("热点") || category.contains("local")
        case .wellness: return category.contains("健康") || category.contains("养生") || category.contains("wellness")
        case .culture: return category.contains("文娱") || category.contains("文化") || category.contains("culture")
        case .interests: return category.contains("兴趣") || category.contains("生活") || category.contains("interest")
        }
    }

    static func icon(for category: String) -> String {
        let value = category.lowercased()
        if value.contains("健康") || value.contains("养生") { return "leaf" }
        if value.contains("文娱") || value.contains("文化") { return "music.note" }
        if value.contains("本地") || value.contains("热点") { return "building.2" }
        return "newspaper"
    }
}

enum HomeArticlePolicy {
    static func visibleArticles(_ articles: [HomeArticle]) -> [HomeArticle] {
        articles.filter { article in
            let category = article.category.trimmingCharacters(in: .whitespacesAndNewlines)
            let title = article.title.trimmingCharacters(in: .whitespacesAndNewlines)
            let source = article.sourceName.trimmingCharacters(in: .whitespacesAndNewlines)
            let incidentCategories = ["event", "incident", "alert", "安全事件", "家庭事件"]
            guard
                !category.isEmpty,
                !title.isEmpty,
                !source.isEmpty,
                !incidentCategories.contains(category.lowercased()),
                let url = URL(string: article.sourceURL),
                url.scheme?.lowercased() == "https",
                url.host != nil
            else { return false }
            return true
        }
    }
}

enum HomeArticleComposition {
    static func featured(_ articles: [HomeArticle]) -> HomeArticle? { articles.first }
    static func remaining(_ articles: [HomeArticle]) -> [HomeArticle] { Array(articles.dropFirst()) }
}

struct EditorialFeed: View {
    let articles: [HomeArticle]
    let apiBaseURL: URL?
    @State private var category: ArticleCategory = .all
    @State private var selectedArticle: HomeArticle?

    private var visibleArticles: [HomeArticle] {
        HomeArticlePolicy.visibleArticles(articles).filter(category.matches)
    }

    private var featuredArticle: HomeArticle? { HomeArticleComposition.featured(visibleArticles) }
    private var remainingArticles: [HomeArticle] { HomeArticleComposition.remaining(visibleArticles) }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            GoHomeSectionHeader(title: "今日阅读", detail: articles.isEmpty ? nil : "\(visibleArticles.count) 篇")
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(ArticleCategory.allCases) { item in
                        Button { category = item } label: {
                            Text(item.rawValue)
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundStyle(category == item ? Color.white : GoHomeTheme.ink)
                                .padding(.horizontal, 12)
                                .frame(height: 32)
                                .background(
                                    category == item ? GoHomeTheme.ink : GoHomeTheme.softLine,
                                    in: Capsule()
                                )
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            if visibleArticles.isEmpty {
                Text("暂无更新")
                    .font(.system(size: 14))
                    .foregroundStyle(GoHomeTheme.mutedInk)
                    .frame(maxWidth: .infinity, minHeight: 72, alignment: .leading)
            } else {
                if let featuredArticle {
                    FeaturedArticleCard(article: featuredArticle, apiBaseURL: apiBaseURL) {
                        selectedArticle = featuredArticle
                    }
                }
                MasonryLayout(spacing: 12) {
                    ForEach(remainingArticles) { article in
                        ArticleCard(article: article, apiBaseURL: apiBaseURL) { selectedArticle = article }
                    }
                }
            }
        }
        .sheet(item: $selectedArticle) { article in
            if let url = URL(string: article.sourceURL) {
                ArticleDetailRoute(url: url)
                    .ignoresSafeArea()
            }
        }
    }
}
