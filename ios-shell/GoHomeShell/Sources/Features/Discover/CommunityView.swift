import SwiftUI

struct CommunityView: View {
    @ObservedObject var model: ProductRecommendationsViewModel
    let apiBaseURL: URL?
    let homeLocation: HomeLocation?
    let onSetHomeLocation: (() -> Void)?
    @Environment(\.openURL) private var openURL

    private let columns = [
        GridItem(.flexible(), spacing: 10),
        GridItem(.flexible(), spacing: 10),
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                header
                LazyVGrid(columns: columns, spacing: 10) {
                    ForEach(CommunityService.allCases) { service in
                        serviceButton(service)
                    }
                }
                Rectangle().fill(GoHomeTheme.line).frame(height: 0.5)
                ProductRecommendationsView(model: model, apiBaseURL: apiBaseURL)
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 18)
            .padding(.bottom, 30)
        }
        .background(GoHomeTheme.paper)
        .accessibilityIdentifier("product-recommendations-content")
        .accessibilityElement(children: .contain)
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 5) {
                Text("社区")
                    .font(.system(size: 28, weight: .bold, design: .rounded))
                    .foregroundStyle(GoHomeTheme.ink)
                Text("附近服务")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
            Spacer()
            if homeLocation == nil {
                if let onSetHomeLocation {
                    Button(action: onSetHomeLocation) {
                        Label("设置家庭位置", systemImage: "location")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundStyle(GoHomeTheme.ink)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("community-home-location-setup")
                } else {
                    Label("家庭位置未设置", systemImage: "location.slash")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
            } else {
                Label(homeLocationLabel, systemImage: "location.fill")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.mutedInk)
                    .lineLimit(1)
            }
        }
    }

    private func serviceButton(_ service: CommunityService) -> some View {
        Button { open(service) } label: {
            HStack(spacing: 12) {
                Image(systemName: service.symbol)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(service.isEmergency ? Color.red : GoHomeTheme.ink)
                    .frame(width: 32, height: 32)
                    .background(service.isEmergency ? Color.red.opacity(0.08) : GoHomeTheme.paleGinger.opacity(0.7), in: Circle())
                VStack(alignment: .leading, spacing: 3) {
                    Text(service.title)
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(GoHomeTheme.ink)
                    Text(service.subtitle)
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 12)
            .frame(maxWidth: .infinity, minHeight: 72)
            .background(service.isEmergency ? Color.red.opacity(0.045) : Color.black.opacity(0.028), in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous)
                    .stroke(service.isEmergency ? Color.red.opacity(0.12) : GoHomeTheme.softLine, lineWidth: 0.5)
            }
        }
        .buttonStyle(.plain)
        .disabled(homeLocation == nil && !service.isEmergency)
        .opacity(homeLocation == nil && !service.isEmergency ? 0.45 : 1)
        .accessibilityLabel(service.title)
        .accessibilityHint(service.accessibilityHint)
    }

    private func open(_ service: CommunityService) {
        if let url = service.destinationURL(homeLocation: homeLocation) { openURL(url) }
    }

    private var homeLocationLabel: String {
        guard let homeLocation else { return "" }
        let label = homeLocation.label.trimmingCharacters(in: .whitespacesAndNewlines)
        if !label.isEmpty { return label }
        let fallback = [homeLocation.district, homeLocation.city]
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .joined(separator: " · ")
        return fallback.isEmpty ? "家庭位置" : fallback
    }
}

enum CommunityService: String, CaseIterable, Identifiable {
    case meals, groceries, convenience, clinic, emergency

    var id: String { rawValue }

    var title: String {
        switch self {
        case .meals: return "社区助餐"
        case .groceries: return "生活配送"
        case .convenience: return "便民服务"
        case .clinic: return "社区医院"
        case .emergency: return "紧急呼叫"
        }
    }

    var subtitle: String {
        switch self {
        case .meals: return "附近助餐点"
        case .groceries: return "商超与生活物资"
        case .convenience: return "维修、家政与服务站"
        case .clinic: return "卫生服务中心"
        case .emergency: return "拨打 120"
        }
    }

    var symbol: String {
        switch self {
        case .meals: return "fork.knife"
        case .groceries: return "basket.fill"
        case .convenience: return "wrench.and.screwdriver.fill"
        case .clinic: return "cross.case.fill"
        case .emergency: return "sos.circle.fill"
        }
    }

    var searchTerm: String {
        switch self {
        case .meals: return "社区助餐"
        case .groceries: return "生活超市"
        case .convenience: return "社区便民服务中心"
        case .clinic: return "社区卫生服务中心"
        case .emergency: return ""
        }
    }

    var phone: String? { self == .emergency ? "120" : nil }
    var isEmergency: Bool { self == .emergency }
    var accessibilityHint: String { phone == nil ? "在地图中查找附近服务" : "拨打急救电话" }

    func destinationURL(homeLocation: HomeLocation?) -> URL? {
        if let phone { return URL(string: "tel://\(phone)") }
        guard let homeLocation else { return nil }
        var components = URLComponents(string: "http://maps.apple.com/")
        components?.queryItems = [
            URLQueryItem(name: "q", value: searchTerm),
            URLQueryItem(name: "ll", value: "\(homeLocation.latitude),\(homeLocation.longitude)"),
        ]
        return components?.url
    }
}
