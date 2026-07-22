import SwiftUI

struct EventsView: View {
    @ObservedObject var model: EventsViewModel
    let apiClient: APIClient?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                GoHomePageHeader(
                    eyebrow: "事件",
                    title: "守护记录",
                    trailing: model.pendingCount > 0 ? AnyView(pendingCounter) : nil
                )
                segmentPicker
                if model.groups.isEmpty {
                    EventEmptyState(segment: model.segment)
                } else {
                    LazyVStack(spacing: 0) {
                        ForEach(model.groups) { group in
                            NavigationLink(value: group.primary.id) {
                                EventListRow(group: group, apiClient: apiClient)
                            }
                            .buttonStyle(.plain)
                            .accessibilityIdentifier("event-row-\(group.primary.id)")
                            Divider().overlay(GoHomeTheme.softLine)
                        }
                    }
                }
                if let reason = model.state.staleReason, model.state.value != nil {
                    Label(reason, systemImage: "wifi.exclamationmark")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 18)
            .padding(.bottom, 28)
        }
        .background(GoHomeTheme.paper)
        .refreshable { model.refresh() }
        .navigationDestination(for: String.self) { eventID in
            if let fallback = model.state.value?.first(where: { $0.id == eventID }) {
                EventDetailView(eventID: eventID, fallback: fallback, model: model, apiClient: apiClient)
            }
        }
        .task { model.start() }
        .accessibilityIdentifier("events-content")
    }

    private var pendingCounter: some View {
        Text("\(min(model.pendingCount, 99))")
            .font(.system(size: 12, weight: .bold, design: .rounded))
            .foregroundStyle(GoHomeTheme.ink)
            .frame(minWidth: 30, minHeight: 30)
            .background(GoHomeTheme.ginger, in: Circle())
            .accessibilityLabel("\(model.pendingCount) 条待处理事件")
    }

    private var segmentPicker: some View {
        Picker("事件状态", selection: $model.segment) {
            ForEach(EventSegment.allCases) { segment in
                Text(segment.title).tag(segment)
            }
        }
        .pickerStyle(.segmented)
        .accessibilityIdentifier("event-segment-picker")
    }
}

private struct EventListRow: View {
    let group: EventGroup
    let apiClient: APIClient?

    var body: some View {
        HStack(alignment: .top, spacing: 13) {
            EventMediaImage(
                assetID: group.primary.mediaAssetID,
                fallbackPath: group.primary.snapshotURL,
                apiClient: apiClient
            )
            .frame(width: 104, height: 78)
            .clipShape(RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))

            VStack(alignment: .leading, spacing: 7) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(EventPresentation.label(for: group.primary.type))
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(GoHomeTheme.ginger)
                    Spacer(minLength: 6)
                    Text(EventDateFormatter.compact(group.primary.occurredAt))
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
                Text(EventPresentation.title(for: group.primary))
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(GoHomeTheme.ink)
                    .lineLimit(2)
                HStack(spacing: 6) {
                    Image(systemName: verificationSymbol)
                        .font(.system(size: 10, weight: .bold))
                    Text(EventPresentation.verificationText(
                        group.primary.payload.verification,
                        evidenceCount: group.primary.evidenceMedia.count
                    ))
                    .lineLimit(1)
                }
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(GoHomeTheme.mutedInk)
                if group.cameraCount > 1 {
                    Text("\(group.cameraCount) 路画面共同佐证")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.vertical, 14)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("event-row-\(group.primary.id)")
    }

    private var verificationSymbol: String {
        switch group.primary.payload.verification?.status {
        case "confirmed": return "checkmark.seal.fill"
        case "rejected": return "checkmark"
        case "uncertain": return "questionmark.circle"
        default: return "icloud"
        }
    }
}

private struct EventEmptyState: View {
    let segment: EventSegment

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 25, weight: .medium))
                .foregroundStyle(GoHomeTheme.ginger)
            Text(title)
                .font(.system(size: 18, weight: .bold))
                .foregroundStyle(GoHomeTheme.ink)
            Text(detail)
                .font(.system(size: 13, weight: .regular))
                .foregroundStyle(GoHomeTheme.mutedInk)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 26)
        .overlay(alignment: .top) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
        .accessibilityIdentifier("events-empty-state")
    }

    private var icon: String {
        segment == .pending ? "checkmark.shield" : "tray"
    }

    private var title: String {
        switch segment {
        case .pending: return "暂无待处理事件"
        case .handled: return "暂无已处理记录"
        case .falsePositive: return "暂无误报记录"
        }
    }

    private var detail: String {
        switch segment {
        case .pending: return "只有需要家人确认的异常会出现在这里。"
        case .handled: return "确认安全后的事件会保留在这里。"
        case .falsePositive: return "标记为误报的证据会用于后续校准。"
        }
    }
}
