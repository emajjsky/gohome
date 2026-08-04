import SwiftUI

enum GuardCameraCatalog {
    static func resolve(profile: ProfileData?, fallback: [HomeCamera]) -> [HomeCamera] {
        guard let profile else { return fallback }
        return profile.cameras
            .filter(\.enabled)
            .map { camera in
                HomeCamera(id: camera.id, name: camera.name, status: camera.status)
            }
    }
}

struct GuardView: View {
    @Environment(\.scenePhase) private var scenePhase
    let cameras: [HomeCamera]
    let apiClient: APIClient?
    let familyID: String
    @ObservedObject var eventsModel: EventsViewModel
    @ObservedObject var timelineModel: ActivityTimelineViewModel
    @Binding var section: GuardSection
    @StateObject private var model: GuardViewModel
    @State private var isVisible = false

    init(
        cameras: [HomeCamera],
        apiClient: APIClient?,
        familyID: String,
        eventsModel: EventsViewModel,
        timelineModel: ActivityTimelineViewModel,
        section: Binding<GuardSection>
    ) {
        self.cameras = cameras
        self.apiClient = apiClient
        self.familyID = familyID
        self.eventsModel = eventsModel
        self.timelineModel = timelineModel
        _section = section
        _model = StateObject(wrappedValue: GuardViewModel(
            streamClient: apiClient.map { client in
                WHEPStreamClient(apiClient: client)
            } ?? UnavailableStreamClient(),
            privacyService: apiClient.map(VideoPrivacyService.init(apiClient:)),
            familyID: familyID
        ))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                GoHomePageHeader(
                    eyebrow: "守护",
                    title: section.title,
                    trailing: eventsModel.pendingCount > 0 ? AnyView(pendingCounter) : nil
                )
                sectionPicker
                sectionContent
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 18)
            .padding(.bottom, 28)
        }
        .background(GoHomeTheme.paper)
        .refreshable {
            if section == .events { eventsModel.refresh() }
            if section == .timeline { timelineModel.refresh() }
        }
        .onChange(of: cameras) { next in
            guard let first = next.first else {
                model.clearSelection()
                return
            }
            if model.selectedCameraID == nil || !next.contains(where: { $0.id == model.selectedCameraID }) {
                if section == .live {
                    model.select(cameraID: first.id)
                }
            }
        }
        .onAppear {
            isVisible = true
            eventsModel.start()
            timelineModel.start()
            startLiveStreamIfNeeded()
        }
        .onDisappear {
            isVisible = false
            model.stop()
        }
        .onChange(of: section) { next in
            if next == .live {
                startLiveStreamIfNeeded()
            } else {
                model.stop()
            }
        }
        .onChange(of: scenePhase) { phase in
            if phase == .background {
                model.stop()
            } else if phase == .active {
                startLiveStreamIfNeeded()
            }
        }
        .accessibilityIdentifier("guard-content")
    }

    @ViewBuilder
    private var sectionContent: some View {
        switch section {
        case .live:
            liveContent
        case .timeline:
            ActivityTimelineView(model: timelineModel)
        case .events:
            EventsListContent(model: eventsModel, apiClient: apiClient)
        }
    }

    private var liveContent: some View {
        VStack(alignment: .leading, spacing: 20) {
            privacyModeControl
            CameraStageView(
                surface: model.videoSurface,
                state: model.streamState,
                displayFPS: model.displayFPS,
                privacyMode: model.selectedPrivacyMode
            )
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
        }
    }

    private var sectionPicker: some View {
        Picker("守护内容", selection: $section) {
            ForEach(GuardSection.allCases) { item in
                Text(item.label).tag(item)
            }
        }
        .pickerStyle(.segmented)
        .accessibilityIdentifier("guard-section-picker")
    }

    private var privacyModeControl: some View {
        HStack(spacing: 4) {
            ForEach(VideoPrivacyMode.allCases) { mode in
                Button {
                    model.setPrivacyMode(mode)
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: mode.symbol)
                            .font(.system(size: 12, weight: .semibold))
                        Text(mode.title)
                            .font(.system(size: 12, weight: .semibold))
                    }
                    .foregroundStyle(model.selectedPrivacyMode == mode ? Color.white : GoHomeTheme.mutedInk)
                    .frame(maxWidth: .infinity, minHeight: 34)
                    .background(
                        model.selectedPrivacyMode == mode ? GoHomeTheme.ink : Color.clear,
                        in: RoundedRectangle(cornerRadius: 6, style: .continuous)
                    )
                }
                .buttonStyle(.plain)
                .disabled(model.privacyPolicy?.canManage != true || model.privacyUpdateInFlight)
                .accessibilityIdentifier("guard-privacy-\(mode.rawValue)")
            }
            if model.privacyPolicy?.canManage == false {
                Image(systemName: "lock.fill")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.mutedInk)
                    .frame(width: 28)
                    .accessibilityLabel("由家庭创建者设置")
            }
        }
        .padding(3)
        .background(Color.black.opacity(0.035), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(GoHomeTheme.line, lineWidth: 1)
        )
    }

    private var pendingCounter: some View {
        Text("\(min(eventsModel.pendingCount, 99))")
            .font(.system(size: 12, weight: .bold, design: .rounded))
            .foregroundStyle(GoHomeTheme.ink)
            .frame(minWidth: 30, minHeight: 30)
            .background(GoHomeTheme.ginger, in: Circle())
            .accessibilityLabel("\(eventsModel.pendingCount) 条待处理事件")
    }

    private func startLiveStreamIfNeeded() {
        guard isVisible, section == .live else { return }
        model.startPrivacySync()
        guard let cameraID = model.selectedCameraID ?? cameras.first?.id else { return }
        model.select(cameraID: cameraID)
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

enum GuardSection: String, CaseIterable, Identifiable {
    case live
    case timeline
    case events

    var id: String { rawValue }

    var label: String {
        switch self {
        case .live: return "实时"
        case .timeline: return "轨迹"
        case .events: return "事件"
        }
    }

    var title: String {
        switch self {
        case .live: return "实时画面"
        case .timeline: return "今日轨迹"
        case .events: return "安全事件"
        }
    }
}

private actor UnavailableStreamClient: CameraStreamClient {
    func streams(
        cameraID: String,
        profile: String,
        privacyMode: VideoPrivacyMode
    ) async throws -> CameraDisplayStreams {
        throw APIError.invalidResponse
    }

    func stop() async {}
}
