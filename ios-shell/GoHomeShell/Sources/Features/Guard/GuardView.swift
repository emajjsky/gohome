import SwiftUI

struct GuardView: View {
    @Environment(\.scenePhase) private var scenePhase
    let cameras: [HomeCamera]
    let apiClient: APIClient?
    @ObservedObject var eventsModel: EventsViewModel
    let onOpenEvents: () -> Void
    @StateObject private var model: GuardViewModel
    @State private var isVisible = false

    init(cameras: [HomeCamera], apiClient: APIClient?, eventsModel: EventsViewModel, onOpenEvents: @escaping () -> Void = {}) {
        self.cameras = cameras
        self.apiClient = apiClient
        self.eventsModel = eventsModel
        self.onOpenEvents = onOpenEvents
        _model = StateObject(wrappedValue: GuardViewModel(
            streamClient: apiClient.map { client in
                MJPEGStreamClient(apiClient: client)
            } ?? UnavailableStreamClient()
        ))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                GoHomePageHeader(eyebrow: "守护", title: "实时画面")
                CameraStageView(frameData: model.latestFrame, state: model.streamState)
                CameraThumbnailStrip(cameras: cameras, selectedID: model.selectedCameraID) { cameraID in
                    model.select(cameraID: cameraID)
                }
                HStack(spacing: 8) {
                    GoHomeStatusDot(color: statusColor)
                    Text(statusText)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                    Spacer()
                    if case .failed = model.streamState {
                        Button("重试") { model.retry() }
                            .font(.system(size: 13, weight: .bold))
                            .foregroundStyle(GoHomeTheme.ink)
                    }
                }
                .padding(.top, 2)
                Button(action: onOpenEvents) {
                    HStack(spacing: 12) {
                        Image(systemName: "bell.badge")
                            .foregroundStyle(GoHomeTheme.ginger)
                        VStack(alignment: .leading, spacing: 3) {
                            Text("守护记录")
                                .font(.system(size: 15, weight: .bold))
                                .foregroundStyle(GoHomeTheme.ink)
                            Text(eventsModel.pendingCount > 0 ? "\(eventsModel.pendingCount) 条待确认" : "查看事件与云端复核证据")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundStyle(GoHomeTheme.mutedInk)
                        }
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(GoHomeTheme.mutedInk)
                    }
                    .padding(.vertical, 14)
                    .overlay(alignment: .top) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
                    .overlay(alignment: .bottom) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("guard-events-entry")
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 18)
            .padding(.bottom, 28)
        }
        .background(GoHomeTheme.paper)
        .onChange(of: cameras) { next in
            guard let first = next.first else {
                model.clearSelection()
                return
            }
            if model.selectedCameraID == nil || !next.contains(where: { $0.id == model.selectedCameraID }) {
                model.select(cameraID: first.id)
            }
        }
        .onAppear {
            isVisible = true
            eventsModel.start()
            guard let cameraID = model.selectedCameraID ?? cameras.first?.id else { return }
            model.select(cameraID: cameraID)
        }
        .onDisappear {
            isVisible = false
            model.stop()
        }
        .onChange(of: scenePhase) { phase in
            if phase == .background {
                model.stop()
            } else if phase == .active, isVisible, let cameraID = model.selectedCameraID {
                model.select(cameraID: cameraID)
            }
        }
        .accessibilityIdentifier("guard-content")
    }

    private var statusText: String {
        switch model.streamState {
        case .idle: return cameras.isEmpty ? "暂无可用画面" : "选择一路画面"
        case .connecting: return "正在连接"
        case .playing: return "实时播放中"
        case let .failed(message): return message.isEmpty ? "画面暂时不可用" : message
        }
    }

    private var statusColor: Color {
        switch model.streamState {
        case .playing: return .green
        case .failed: return .red
        default: return GoHomeTheme.ginger
        }
    }
}

private actor UnavailableStreamClient: CameraStreamClient {
    func frames(cameraID: String, profile: String) async throws -> AsyncThrowingStream<Data, Error> {
        throw APIError.invalidResponse
    }

    func stop() async {}
}
