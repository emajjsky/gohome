import SwiftUI

struct ProductRecommendationsResponse: Codable, Equatable, Sendable {
    let products: [ProductRecommendation]
    let revision: String
}

struct ProductRecommendation: Codable, Equatable, Identifiable, Sendable {
    let id: String
    let category: String
    let brand: String
    let name: String
    let summary: String
    let imageURL: String
    let sourceName: String
    let sourceURL: String
    let suitability: [String]
    let recommendationReason: String
    let disclosure: String
    let verifiedAt: String

    enum CodingKeys: String, CodingKey {
        case id, category, brand, name, summary, suitability, disclosure
        case imageURL = "image_url"
        case sourceName = "source_name"
        case sourceURL = "source_url"
        case recommendationReason = "recommendation_reason"
        case verifiedAt = "verified_at"
    }
}

@MainActor
final class ProductRecommendationsViewModel: ObservableObject {
    @Published private(set) var state = Loadable<ProductRecommendationsResponse>()

    private let repository: AppRepository?
    private let scope: CacheScope?
    private var loadTask: Task<Void, Never>?
    private var hasStarted = false

    init(repository: AppRepository?, scope: CacheScope?) {
        self.repository = repository
        self.scope = scope
    }

    func start() {
        guard !hasStarted, let repository, let scope else { return }
        hasStarted = true
        loadTask = Task { [repository, scope] in
            await repository.products(scope: scope) { next in
                await MainActor.run { self.state = next }
            }
        }
    }

    deinit { loadTask?.cancel() }
}

struct ProductRecommendationsView: View {
    @ObservedObject var model: ProductRecommendationsViewModel
    @State private var selectedCategory = "全部"

    private let columns = [
        GridItem(.flexible(), spacing: 12, alignment: .top),
        GridItem(.flexible(), spacing: 12, alignment: .top),
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                GoHomePageHeader(eyebrow: "精选", title: "生活好物")

                if !categories.isEmpty {
                    categoryBar
                }

                if filteredProducts.isEmpty {
                    emptyState
                } else {
                    LazyVGrid(columns: columns, alignment: .leading, spacing: 22) {
                        ForEach(filteredProducts) { product in
                            ProductRecommendationCard(product: product)
                        }
                    }
                }

                if let staleReason = model.state.staleReason, model.state.value != nil {
                    Text(staleReason)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 18)
            .padding(.bottom, 30)
        }
        .background(GoHomeTheme.paper)
        .accessibilityIdentifier("product-recommendations-content")
    }

    private var products: [ProductRecommendation] {
        model.state.value?.products ?? []
    }

    private var categories: [String] {
        let values = Set(products.map(\.category).filter { !$0.isEmpty })
        return values.isEmpty ? [] : ["全部"] + values.sorted()
    }

    private var filteredProducts: [ProductRecommendation] {
        selectedCategory == "全部" ? products : products.filter { $0.category == selectedCategory }
    }

    private var categoryBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(categories, id: \.self) { category in
                    Button {
                        selectedCategory = category
                    } label: {
                        Text(category)
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(selectedCategory == category ? Color.white : GoHomeTheme.ink)
                            .padding(.horizontal, 14)
                            .frame(height: 34)
                            .background(selectedCategory == category ? GoHomeTheme.ink : Color.black.opacity(0.045))
                            .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: 10) {
            Image(systemName: "sparkles")
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(GoHomeTheme.ginger)
            Text("今天没有新的推荐")
                .font(.system(size: 17, weight: .bold))
                .foregroundStyle(GoHomeTheme.ink)
        }
        .frame(maxWidth: .infinity, minHeight: 180, alignment: .leading)
        .accessibilityIdentifier("product-recommendations-empty")
    }
}

private struct ProductRecommendationCard: View {
    let product: ProductRecommendation

    var body: some View {
        Group {
            if let url = URL(string: product.sourceURL) {
                Link(destination: url) { content }
            } else {
                content
            }
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("product-card-\(product.id)")
    }

    private var content: some View {
        VStack(alignment: .leading, spacing: 10) {
            AsyncImage(url: URL(string: product.imageURL)) { phase in
                switch phase {
                case .success(let image):
                    image.resizable().scaledToFill()
                default:
                    Rectangle()
                        .fill(Color.black.opacity(0.045))
                        .overlay {
                            Image(systemName: "photo")
                                .foregroundStyle(GoHomeTheme.mutedInk)
                        }
                }
            }
            .frame(maxWidth: .infinity)
            .aspectRatio(1, contentMode: .fit)
            .clipped()
            .clipShape(RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))

            Text(product.category)
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(GoHomeTheme.ginger)
                .lineLimit(1)

            Text(product.name)
                .font(.system(size: 16, weight: .bold))
                .foregroundStyle(GoHomeTheme.ink)
                .lineLimit(2)

            Text(product.summary)
                .font(.system(size: 12, weight: .regular))
                .foregroundStyle(GoHomeTheme.mutedInk)
                .lineLimit(3)

            HStack(spacing: 5) {
                Image(systemName: "checkmark.seal.fill")
                    .foregroundStyle(GoHomeTheme.ginger)
                Text(product.sourceName)
                    .lineLimit(1)
            }
            .font(.system(size: 10, weight: .semibold))
            .foregroundStyle(GoHomeTheme.mutedInk)
        }
    }
}
