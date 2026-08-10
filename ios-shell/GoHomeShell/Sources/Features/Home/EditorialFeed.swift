import SwiftUI

enum ArticleCategory: String, CaseIterable, Identifiable {
    case all = "全部"
    case local = "本地"
    case wellness = "生活健康"
    case culture = "文娱"
    case interests = "兴趣"
    case antiFraud = "防诈骗"

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
        case .antiFraud: return category.contains("反诈") || category.contains("防诈骗") || category.contains("anti_fraud") || category.contains("fraud")
        }
    }

    static func icon(for category: String) -> String {
        let value = category.lowercased()
        if value.contains("健康") || value.contains("养生") { return "leaf" }
        if value.contains("文娱") || value.contains("文化") { return "music.note" }
        if value.contains("本地") || value.contains("热点") { return "building.2" }
        if value.contains("反诈") || value.contains("诈骗") || value.contains("fraud") { return "checkmark.shield" }
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

    static func localImageName(for article: HomeArticle) -> String {
        let catalog = [
            "memory-daughter-walk",
            "memory-garden-sun",
            "memory-generations",
            "memory-outdoor-walk",
            "memory-relax-chat",
            "grandma-reading",
        ]
        let seed = article.id.unicodeScalars.reduce(0) { ($0 &* 31) &+ Int($1.value) }
        return catalog[abs(seed) % catalog.count]
    }

    static func localImageAssignments(_ articles: [HomeArticle]) -> [String: String] {
        let catalog = [
            "memory-daughter-walk",
            "memory-garden-sun",
            "memory-generations",
            "memory-outdoor-walk",
            "memory-relax-chat",
            "grandma-reading",
        ]
        var used = Set<String>()
        var assignments: [String: String] = [:]
        for article in articles {
            let start = abs(article.id.unicodeScalars.reduce(0) { ($0 &* 31) &+ Int($1.value) }) % catalog.count
            let name = (0..<catalog.count)
                .map { catalog[(start + $0) % catalog.count] }
                .first { used.insert($0).inserted }
                ?? catalog[start]
            assignments[article.id] = name
        }
        return assignments
    }

    static func remoteImageArticleIDs(_ articles: [HomeArticle]) -> Set<String> {
        var seen = Set<String>()
        var ids = Set<String>()
        for article in articles {
            let rawURL = article.imageURL.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !rawURL.isEmpty, seen.insert(rawURL).inserted else { continue }
            ids.insert(article.id)
        }
        return ids
    }
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
    private var remoteImageArticleIDs: Set<String> {
        HomeArticleComposition.remoteImageArticleIDs(visibleArticles)
    }
    private var localImageAssignments: [String: String] {
        HomeArticleComposition.localImageAssignments(visibleArticles)
    }

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
                    FeaturedArticleCard(
                        article: featuredArticle,
                        apiBaseURL: apiBaseURL,
                        usesRemoteImage: remoteImageArticleIDs.contains(featuredArticle.id),
                        fallbackImageName: localImageAssignments[featuredArticle.id]
                    ) {
                        selectedArticle = featuredArticle
                    }
                }
                LazyVGrid(
                    columns: [
                        GridItem(.flexible(), spacing: 12, alignment: .top),
                        GridItem(.flexible(), spacing: 12, alignment: .top),
                    ],
                    alignment: .leading,
                    spacing: 12
                ) {
                    ForEach(remainingArticles) { article in
                        ArticleCard(
                            article: article,
                            apiBaseURL: apiBaseURL,
                            usesRemoteImage: remoteImageArticleIDs.contains(article.id),
                            fallbackImageName: localImageAssignments[article.id]
                        ) {
                            selectedArticle = article
                        }
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
