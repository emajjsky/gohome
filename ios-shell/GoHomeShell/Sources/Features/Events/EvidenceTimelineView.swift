import SwiftUI
import UIKit

struct EvidenceTimelineView: View {
    let event: AppEvent
    let apiClient: APIClient?

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            GoHomeSectionHeader(title: "证据时间线", detail: "按发生顺序")
            VStack(spacing: 0) {
                ForEach(Array(EventPresentation.timeline(for: event).enumerated()), id: \.element.id) { index, item in
                    EventTimelineRow(
                        item: item,
                        isLast: index == EventPresentation.timeline(for: event).count - 1
                    )
                }
            }
            if event.evidenceMedia.count > 1 {
                evidenceStrip
            }
        }
    }

    private var evidenceStrip: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("关键画面")
                .font(.system(size: 14, weight: .bold))
                .foregroundStyle(GoHomeTheme.ink)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(event.evidenceMedia) { evidence in
                        VStack(alignment: .leading, spacing: 7) {
                            EventMediaImage(assetID: evidence.assetID, fallbackPath: nil, apiClient: apiClient)
                                .frame(width: 156, height: 96)
                                .clipShape(RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
                            Text(roleLabel(evidence.role))
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(GoHomeTheme.mutedInk)
                        }
                    }
                }
            }
        }
    }

    private func roleLabel(_ role: String) -> String {
        switch role {
        case "before": return "事发前"
        case "transition": return "姿态变化"
        case "current": return "当前画面"
        default: return "证据画面"
        }
    }
}

private struct EventTimelineRow: View {
    let item: EventTimelineItem
    let isLast: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 13) {
            VStack(spacing: 0) {
                ZStack {
                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                        .fill(item.tone == .warning ? GoHomeTheme.paleGinger : Color.black.opacity(0.05))
                        .frame(width: 32, height: 32)
                    Image(systemName: item.symbol)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(item.tone == .warning ? GoHomeTheme.ink : GoHomeTheme.mutedInk)
                }
                if !isLast {
                    Rectangle()
                        .fill(GoHomeTheme.line)
                        .frame(width: 1, height: 44)
                }
            }
            VStack(alignment: .leading, spacing: 5) {
                HStack(alignment: .firstTextBaseline) {
                    Text(item.title)
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(GoHomeTheme.ink)
                    Spacer(minLength: 8)
                    if let date = EventDateFormatter.time(item.date) {
                        Text(date)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(GoHomeTheme.mutedInk)
                    }
                }
                Text(item.detail)
                    .font(.system(size: 12, weight: .regular))
                    .foregroundStyle(GoHomeTheme.mutedInk)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.top, 2)
            .padding(.bottom, isLast ? 0 : 18)
        }
    }
}

struct EventMediaImage: View {
    let assetID: String?
    let fallbackPath: String?
    let apiClient: APIClient?
    @State private var image: UIImage?
    @State private var failed = false

    var body: some View {
        ZStack {
            Rectangle().fill(Color.black.opacity(0.045))
            if let image {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                Image(systemName: failed ? "photo" : "viewfinder")
                    .font(.system(size: 20, weight: .medium))
                    .foregroundStyle(GoHomeTheme.mutedInk.opacity(0.72))
            }
        }
        .clipped()
        .task(id: mediaPath) { await load() }
    }

    private var mediaPath: String? {
        if let assetID, !assetID.isEmpty { return "/api/v1/video/assets/\(assetID)" }
        guard let fallbackPath, !fallbackPath.isEmpty else { return nil }
        if fallbackPath.hasPrefix("/api/") { return fallbackPath }
        return "/api/v1/video/media/snapshots/\(fallbackPath.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? fallbackPath)"
    }

    @MainActor
    private func load() async {
        guard image == nil, let mediaPath, let apiClient else { return }
        do {
            let data = try await apiClient.data(path: mediaPath)
            guard !Task.isCancelled else { return }
            image = UIImage(data: data)
            failed = image == nil
        } catch is CancellationError {
            return
        } catch {
            failed = true
        }
    }
}

enum EventDateFormatter {
    private static let isoWithFractionalSeconds: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let iso = ISO8601DateFormatter()

    static func date(_ value: String?) -> Date? {
        guard let value, !value.isEmpty else { return nil }
        return isoWithFractionalSeconds.date(from: value) ?? iso.date(from: value)
    }

    static func time(_ value: String?) -> String? {
        guard let date = date(value) else { return nil }
        return date.formatted(.dateTime.hour(.twoDigits(amPM: .omitted)).minute(.twoDigits))
    }

    static func compact(_ value: String?) -> String {
        guard let date = date(value) else { return "时间待同步" }
        return date.formatted(.dateTime.month(.twoDigits).day(.twoDigits).hour(.twoDigits(amPM: .omitted)).minute(.twoDigits))
    }
}
