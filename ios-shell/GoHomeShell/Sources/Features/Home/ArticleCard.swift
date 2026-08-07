import SwiftUI

struct FeaturedArticleCard: View {
    let article: HomeArticle
    let apiBaseURL: URL?
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            ZStack(alignment: .bottomLeading) {
                ArticleImage(article: article, apiBaseURL: apiBaseURL, aspectRatio: 2.2)
                Color.black.opacity(0.68)
                    .frame(maxWidth: .infinity)
                    .frame(height: 92)
                VStack(alignment: .leading, spacing: 5) {
                    HStack {
                        Text(article.category)
                            .font(.system(size: 11, weight: .bold))
                            .foregroundStyle(GoHomeTheme.ginger)
                        Spacer()
                        Text(article.articleMetadataText)
                            .font(.system(size: 10, weight: .medium))
                            .foregroundStyle(Color.white.opacity(0.82))
                            .lineLimit(1)
                    }
                    Text(article.title)
                        .font(.system(size: 20, weight: .bold, design: .rounded))
                        .foregroundStyle(Color.white)
                        .multilineTextAlignment(.leading)
                        .lineLimit(2)
                }
                .padding(13)
            }
            .background(GoHomeTheme.paper)
            .clipShape(RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous)
                    .stroke(GoHomeTheme.line, lineWidth: 0.5)
            }
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(article.category)，\(article.title)，来源 \(article.sourceName)")
        .accessibilityHint("打开原文")
        .accessibilityIdentifier("home-featured-article-\(article.id)")
    }
}

struct ArticleCard: View {
    let article: HomeArticle
    let apiBaseURL: URL?
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 0) {
                ArticleImage(article: article, apiBaseURL: apiBaseURL)
                VStack(alignment: .leading, spacing: 8) {
                    Text(article.category)
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(GoHomeTheme.ginger)
                        .lineLimit(1)
                    Text(article.title)
                        .font(.system(size: 16, weight: .bold, design: .rounded))
                        .foregroundStyle(GoHomeTheme.ink)
                        .multilineTextAlignment(.leading)
                        .lineLimit(3)
                    if !article.summary.isEmpty {
                        Text(article.summary)
                            .font(.system(size: 12))
                            .foregroundStyle(GoHomeTheme.mutedInk)
                            .multilineTextAlignment(.leading)
                            .lineLimit(3)
                    }
                    Text(article.articleMetadataText)
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                        .lineLimit(1)
                }
                .padding(11)
            }
            .background(GoHomeTheme.paper)
            .clipShape(RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous)
                    .stroke(GoHomeTheme.line, lineWidth: 0.5)
            }
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(article.category)，\(article.title)，来源 \(article.sourceName)")
        .accessibilityHint("打开原文")
        .accessibilityIdentifier("home-article-\(article.id)")
    }

}

struct ArticleImage: View {
    let article: HomeArticle
    let apiBaseURL: URL?
    var aspectRatio: CGFloat = 4 / 3

    var body: some View {
        Group {
            if let url = proxiedContentImageURL(article.imageURL, baseURL: apiBaseURL) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case let .success(image):
                        image.resizable().scaledToFill()
                    default:
                        localFallback
                    }
                }
            } else {
                localFallback
            }
        }
        .frame(maxWidth: .infinity)
        .aspectRatio(aspectRatio, contentMode: .fit)
        .clipped()
    }

    private var localFallback: some View {
        GoHomeLocalImage(name: article.localImageName)
            .overlay(alignment: .bottomLeading) {
                if aspectRatio > 2 {
                    Color.black.opacity(0.22)
                }
            }
    }
}

private extension HomeArticle {
    var localImageName: String {
        let value = category.lowercased()
        if value.contains("健康") || value.contains("养生") { return "grandma-reading" }
        if value.contains("本地") || value.contains("热点") { return "memory-garden-sun" }
        if value.contains("文娱") || value.contains("文化") { return "memory-generations" }
        return "memory-relax-chat"
    }

    var articleMetadataText: String {
        guard let publishedAt else { return sourceName }
        let formatter = ISO8601DateFormatter()
        guard let date = formatter.date(from: publishedAt) else { return sourceName }
        return "\(sourceName) · \(date.formatted(.dateTime.month().day()))"
    }
}

func proxiedContentImageURL(_ rawURL: String, baseURL: URL?) -> URL? {
    guard let source = URL(string: rawURL), source.scheme?.lowercased() == "https" else { return nil }
    guard let baseURL else { return source }
    var components = URLComponents(
        url: baseURL.appendingPathComponent("api/v1/content/image"),
        resolvingAgainstBaseURL: false
    )
    components?.queryItems = [URLQueryItem(name: "url", value: source.absoluteString)]
    return components?.url
}
