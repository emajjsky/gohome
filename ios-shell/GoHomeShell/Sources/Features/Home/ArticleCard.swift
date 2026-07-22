import SwiftUI

struct ArticleCard: View {
    let article: HomeArticle
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 0) {
                ArticleImage(article: article)
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
                    Text(article.sourceName)
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

private struct ArticleImage: View {
    let article: HomeArticle

    var body: some View {
        Group {
            if let url = URL(string: article.imageURL), url.scheme == "https" {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case let .success(image):
                        image.resizable().scaledToFill()
                    default:
                        ArticleImageFallback(category: article.category)
                    }
                }
            } else {
                ArticleImageFallback(category: article.category)
            }
        }
        .frame(maxWidth: .infinity)
        .aspectRatio(4 / 3, contentMode: .fit)
        .clipped()
    }
}

private struct ArticleImageFallback: View {
    let category: String

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            GoHomeTheme.paleGinger.opacity(0.72)
            Image(systemName: ArticleCategory.icon(for: category))
                .font(.system(size: 30, weight: .light))
                .foregroundStyle(GoHomeTheme.ink.opacity(0.72))
                .padding(14)
        }
    }
}
