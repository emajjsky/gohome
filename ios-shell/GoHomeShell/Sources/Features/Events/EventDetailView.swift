import SwiftUI

struct EventDetailView: View {
    @Environment(\.dismiss) private var dismiss
    let eventID: String
    let fallback: AppEvent
    @ObservedObject var model: EventsViewModel
    let apiClient: APIClient?

    private var event: AppEvent { model.event(id: eventID, fallback: fallback) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                hero
                summary
                EvidenceTimelineView(event: event, apiClient: apiClient)
                if let error = model.actionErrors[eventID] {
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "exclamationmark.circle")
                        Text(error)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(GoHomeTheme.ink)
                    .padding(12)
                    .background(GoHomeTheme.paleGinger, in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
                    .accessibilityIdentifier("event-action-error")
                }
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 10)
            .padding(.bottom, 120)
        }
        .background(GoHomeTheme.paper)
        .navigationTitle("事件详情")
        .navigationBarTitleDisplayMode(.inline)
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                Button { dismiss() } label: {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 16, weight: .semibold))
                }
                .foregroundStyle(GoHomeTheme.ink)
                .accessibilityLabel("返回")
            }
        }
        .safeAreaInset(edge: .bottom) { actionBar }
        .task { model.loadDetail(id: eventID) }
    }

    private var hero: some View {
        VStack(alignment: .leading, spacing: 14) {
            EventMediaImage(
                assetID: event.mediaAssetID,
                fallbackPath: event.snapshotURL,
                apiClient: apiClient
            )
            .frame(maxWidth: .infinity)
            .aspectRatio(16 / 9, contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
            .accessibilityIdentifier("event-evidence-image")

            HStack(alignment: .firstTextBaseline) {
                Text(EventPresentation.label(for: event.type))
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(GoHomeTheme.ginger)
                Spacer()
                Text(statusTitle)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
            Text(EventPresentation.title(for: event))
                .font(.system(size: 24, weight: .bold, design: .rounded))
                .foregroundStyle(GoHomeTheme.ink)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var summary: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 7) {
                Image(systemName: "clock")
                Text(EventDateFormatter.compact(event.occurredAt))
                Text("·")
                Text(event.room.isEmpty ? event.cameraName.isEmpty ? "家庭画面" : event.cameraName : event.room)
            }
            .font(.system(size: 12, weight: .medium))
            .foregroundStyle(GoHomeTheme.mutedInk)

            HStack(alignment: .top, spacing: 8) {
                Image(systemName: verificationSymbol)
                Text(EventPresentation.verificationText(event.payload.verification, evidenceCount: event.evidenceMedia.count))
                    .fixedSize(horizontal: false, vertical: true)
            }
            .font(.system(size: 13, weight: .semibold))
            .foregroundStyle(GoHomeTheme.ink)
            .padding(.top, 3)
            .accessibilityIdentifier("event-verification-status")
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 14)
        .overlay(alignment: .top) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
        .overlay(alignment: .bottom) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
    }

    private var actionBar: some View {
        VStack(spacing: 9) {
            HStack(spacing: 10) {
                Button {
                    model.resolve(eventID, as: "handled")
                } label: {
                    Label("确认安全", systemImage: "checkmark")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(EventPrimaryButtonStyle())
                .disabled(isActionDisabled)
                .accessibilityIdentifier("event-confirm-safe")

                Button {
                    model.resolve(eventID, as: "false_positive")
                } label: {
                    Label("标记误报", systemImage: "checkmark.seal")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(EventSecondaryButtonStyle())
                .disabled(isActionDisabled)
                .accessibilityIdentifier("event-mark-false-positive")

                ShareLink(item: shareMessage) {
                    Image(systemName: "square.and.arrow.up")
                        .frame(width: 42, height: 42)
                }
                .buttonStyle(EventSecondaryButtonStyle())
                .accessibilityLabel("分享事件信息")
                .accessibilityIdentifier("event-share")
            }
        }
        .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
        .padding(.top, 10)
        .padding(.bottom, 8)
        .background(.ultraThinMaterial)
    }

    private var statusTitle: String {
        switch EventPresentation.segment(event) {
        case .pending: return "待处理"
        case .handled: return "已处理"
        case .falsePositive: return "误报"
        }
    }

    private var verificationSymbol: String {
        switch event.payload.verification?.status {
        case "confirmed": return "checkmark.seal.fill"
        case "rejected": return "checkmark"
        case "uncertain": return "questionmark.circle"
        default: return "icloud"
        }
    }

    private var isActionDisabled: Bool {
        model.pendingActions.contains(eventID) || event.acknowledged
    }

    private var shareMessage: String {
        "GoHome 守护提醒：\(EventPresentation.title(for: event))，时间 \(EventDateFormatter.compact(event.occurredAt))。请结合实时画面确认。"
    }
}

private struct EventPrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .bold))
            .foregroundStyle(GoHomeTheme.ink)
            .frame(height: 42)
            .background(GoHomeTheme.ginger, in: RoundedRectangle(cornerRadius: GoHomeTheme.controlRadius, style: .continuous))
            .opacity(configuration.isPressed ? 0.8 : 1)
    }
}

private struct EventSecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .bold))
            .foregroundStyle(GoHomeTheme.ink)
            .frame(height: 42)
            .padding(.horizontal, 10)
            .background(GoHomeTheme.paper, in: RoundedRectangle(cornerRadius: GoHomeTheme.controlRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: GoHomeTheme.controlRadius, style: .continuous)
                    .stroke(GoHomeTheme.line, lineWidth: 1)
            }
            .opacity(configuration.isPressed ? 0.65 : 1)
    }
}
