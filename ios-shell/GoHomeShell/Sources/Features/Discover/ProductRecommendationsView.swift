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

    init(repository: AppRepository?, scope: CacheScope?, seed: ProductRecommendationsResponse? = nil) {
        self.repository = repository
        self.scope = scope
        state = Loadable(value: seed, isRefreshing: false, staleReason: nil)
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
    @State private var selectedProduct: ProductRecommendation?

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
                            ProductRecommendationCard(product: product) {
                                selectedProduct = product
                            }
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
        .sheet(item: $selectedProduct) { product in
            ProductRecommendationDetail(product: product)
        }
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
    let action: () -> Void

    var body: some View {
        Button(action: action) { content }
        .buttonStyle(.plain)
        .accessibilityLabel("\(product.name)，\(product.category)")
        .accessibilityHint("查看推荐详情")
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

private struct ProductRecommendationDetail: View {
    @Environment(\.dismiss) private var dismiss
    let product: ProductRecommendation

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    AsyncImage(url: URL(string: product.imageURL)) { phase in
                        if case let .success(image) = phase {
                            image.resizable().scaledToFill()
                        } else {
                            Rectangle()
                                .fill(GoHomeTheme.paleGinger)
                                .overlay {
                                    Image(systemName: "shippingbox")
                                        .font(.system(size: 34, weight: .light))
                                        .foregroundStyle(GoHomeTheme.ink.opacity(0.72))
                                }
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .aspectRatio(4 / 3, contentMode: .fit)
                    .clipped()
                    .clipShape(RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))

                    VStack(alignment: .leading, spacing: 8) {
                        Text(product.category)
                            .font(.system(size: 11, weight: .bold))
                            .foregroundStyle(GoHomeTheme.ginger)
                        Text(product.name)
                            .font(.system(size: 26, weight: .bold, design: .rounded))
                            .foregroundStyle(GoHomeTheme.ink)
                        Text(product.brand)
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(GoHomeTheme.mutedInk)
                    }

                    Text(product.summary)
                        .font(.system(size: 15))
                        .foregroundStyle(GoHomeTheme.ink)
                        .fixedSize(horizontal: false, vertical: true)

                    detailSection(title: "推荐依据") {
                        Text(product.recommendationReason)
                    }

                    detailSection(title: "适用方向") {
                        Text(product.suitability.joined(separator: " · "))
                    }

                    detailSection(title: "来源与说明") {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(product.sourceName)
                            Text(product.disclosure)
                            Text("核验于 \(verifiedDateText)")
                        }
                    }

                    if let url = URL(string: product.sourceURL), url.scheme?.lowercased() == "https" {
                        Link(destination: url) {
                            Label("查看官方页面", systemImage: "arrow.up.right")
                                .font(.system(size: 15, weight: .bold))
                                .foregroundStyle(Color.white)
                                .frame(maxWidth: .infinity, minHeight: 48)
                                .background(GoHomeTheme.ink, in: RoundedRectangle(cornerRadius: GoHomeTheme.controlRadius, style: .continuous))
                        }
                        .accessibilityIdentifier("product-official-link")
                    }
                }
                .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
                .padding(.top, 12)
                .padding(.bottom, 28)
            }
            .background(GoHomeTheme.paper)
            .navigationTitle("推荐详情")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button { dismiss() } label: {
                        Image(systemName: "xmark")
                    }
                    .accessibilityLabel("关闭")
                }
            }
        }
    }

    private func detailSection<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            GoHomeSectionHeader(title: title)
            content()
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(GoHomeTheme.mutedInk)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 12)
        .overlay(alignment: .top) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
        .overlay(alignment: .bottom) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
    }

    private var verifiedDateText: String {
        let formatter = ISO8601DateFormatter()
        guard let date = formatter.date(from: product.verifiedAt) else { return product.verifiedAt }
        let displayFormatter = DateFormatter()
        displayFormatter.locale = Locale(identifier: "zh_CN")
        displayFormatter.timeZone = TimeZone(identifier: "Asia/Shanghai")
        displayFormatter.dateFormat = "yyyy年M月d日"
        return displayFormatter.string(from: date)
    }
}
