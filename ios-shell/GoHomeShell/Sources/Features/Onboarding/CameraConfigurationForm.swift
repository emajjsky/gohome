import SwiftUI

struct CameraConnectionValues: Equatable, Sendable {
    let name: String
    let room: String
    let streamURL: String
    let username: String
    let password: String
    let enabled: Bool
}

struct CameraConfigurationForm: View {
    let binding: DeviceBinding
    let existing: CameraConfig?
    let onSave: @MainActor (CameraConnectionValues) async -> Bool

    @StateObject private var discovery = BoxDiscoveryService()
    @State private var name: String
    @State private var roomSelection: String
    @State private var customRoom: String
    @State private var host = ""
    @State private var port = "554"
    @State private var streamPath = "/1/2"
    @State private var username = "admin"
    @State private var password = ""
    @State private var enabled: Bool
    @State private var candidates: [DiscoveredCamera] = []
    @State private var selectedCandidateID: String?
    @State private var isSearching = false
    @State private var isSaving = false
    @State private var showManualEntry = false
    @State private var errorMessage: String?
    @State private var attemptedAutomaticSearch = false

    private let commonRooms = ["客厅", "卧室", "厨房", "餐厅", "走廊", "玄关"]

    init(
        binding: DeviceBinding,
        existing: CameraConfig? = nil,
        onSave: @escaping @MainActor (CameraConnectionValues) async -> Bool
    ) {
        self.binding = binding
        self.existing = existing
        self.onSave = onSave
        let existingRoom = existing?.room.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let existingName = existing?.name.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let initialRoom = existingRoom.isEmpty ? "客厅" : existingRoom
        _name = State(initialValue: existingName.isEmpty ? "客厅摄像头" : existingName)
        _roomSelection = State(initialValue: commonRooms.contains(initialRoom) ? initialRoom : "其他")
        _customRoom = State(initialValue: commonRooms.contains(initialRoom) ? "" : initialRoom)
        _enabled = State(initialValue: existing?.enabled ?? true)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            ProfileSection(title: "基本信息") {
                formField("画面名称", text: $name, placeholder: "客厅摄像头")
                HStack {
                    Label("安装位置", systemImage: "mappin.and.ellipse")
                        .font(.system(size: 15, weight: .semibold))
                    Spacer()
                    Picker("安装位置", selection: $roomSelection) {
                        ForEach(commonRooms + ["其他"], id: \.self) { Text($0).tag($0) }
                    }
                    .labelsHidden()
                    .tint(GoHomeTheme.ink)
                }
                .frame(minHeight: 52)
                if roomSelection == "其他" {
                    formField("位置名称", text: $customRoom, placeholder: "例如：书房")
                }
                if existing != nil {
                    Toggle(isOn: $enabled) {
                        Label("启用画面", systemImage: "video.fill")
                            .font(.system(size: 15, weight: .semibold))
                    }
                    .tint(GoHomeTheme.ginger)
                    .frame(minHeight: 52)
                }
            }

            if existing == nil { connectionSection }

            if let errorMessage {
                Label(errorMessage, systemImage: "exclamationmark.circle")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(GoHomeTheme.mutedInk)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Button(action: save) {
                HStack(spacing: 8) {
                    if isSaving { ProgressView().tint(.white) }
                    Text(isSaving ? "正在保存" : "保存并同步")
                }
                .font(.system(size: 16, weight: .bold))
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, minHeight: 52)
                .background(GoHomeTheme.ink, in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
            }
            .buttonStyle(.plain)
            .disabled(!canSave || isSaving)
            .opacity(!canSave || isSaving ? 0.4 : 1)
            .accessibilityIdentifier("camera-save")
        }
        .onAppear { if existing == nil { discovery.start() } }
        .onDisappear { discovery.stop() }
        .onChange(of: discovery.boxes) { boxes in
            guard existing == nil,
                  !attemptedAutomaticSearch,
                  boxes.contains(where: { $0.deviceID == binding.deviceID })
            else { return }
            searchCameras()
        }
    }

    private var connectionSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                GoHomeSectionHeader(title: "选择摄像头", detail: candidates.isEmpty ? nil : "\(candidates.count) 台")
                Spacer()
                Button(action: searchCameras) {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 14, weight: .semibold))
                        .frame(width: 34, height: 34)
                }
                .buttonStyle(.plain)
                .foregroundStyle(GoHomeTheme.ink)
                .disabled(isSearching)
                .accessibilityLabel("重新搜索摄像头")
            }

            if isSearching {
                HStack(spacing: 10) {
                    ProgressView().tint(GoHomeTheme.ink)
                    Text("正在搜索同一网络内的摄像头")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
                .frame(minHeight: 52)
            } else if !candidates.isEmpty {
                VStack(spacing: 0) {
                    ForEach(candidates) { candidate in
                        Button { select(candidate) } label: {
                            HStack(spacing: 12) {
                                Image(systemName: selectedCandidateID == candidate.id ? "checkmark.circle.fill" : "circle")
                                    .foregroundStyle(selectedCandidateID == candidate.id ? GoHomeTheme.ginger : GoHomeTheme.mutedInk)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(candidate.label)
                                        .font(.system(size: 14, weight: .semibold))
                                        .foregroundStyle(GoHomeTheme.ink)
                                    Text(candidate.host)
                                        .font(.system(size: 12, design: .monospaced))
                                        .foregroundStyle(GoHomeTheme.mutedInk)
                                }
                                Spacer()
                            }
                            .frame(minHeight: 54)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        Divider().overlay(GoHomeTheme.softLine)
                    }
                }
                .overlay(alignment: .top) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
            }

            DisclosureGroup("手动添加", isExpanded: $showManualEntry) {
                VStack(spacing: 0) {
                    formField("设备地址", text: $host, placeholder: "192.168.1.20", keyboard: .numbersAndPunctuation)
                    formField("端口", text: $port, placeholder: "554", keyboard: .numberPad)
                    formField("视频路径", text: $streamPath, placeholder: "/1/2")
                }
                .padding(.top, 8)
            }
            .font(.system(size: 14, weight: .semibold))
            .tint(GoHomeTheme.ink)

            ProfileSection(title: "摄像头账号") {
                formField("用户名", text: $username, placeholder: "admin")
                    .textInputAutocapitalization(.never)
                SecureField("密码", text: $password)
                    .textContentType(.password)
                    .padding(.horizontal, 2)
                    .frame(minHeight: 52)
            }
        }
    }

    private var room: String {
        roomSelection == "其他"
            ? customRoom.trimmingCharacters(in: .whitespacesAndNewlines)
            : roomSelection
    }

    private var canSave: Bool {
        guard !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, !room.isEmpty else { return false }
        if existing != nil { return true }
        guard let portNumber = Int(port), (1...65_535).contains(portNumber) else { return false }
        return !host.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !streamPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func formField(
        _ title: String,
        text: Binding<String>,
        placeholder: String,
        keyboard: UIKeyboardType = .default
    ) -> some View {
        HStack(spacing: 12) {
            Text(title)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(GoHomeTheme.ink)
                .frame(width: 74, alignment: .leading)
            TextField(placeholder, text: text)
                .keyboardType(keyboard)
                .multilineTextAlignment(.trailing)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
        }
        .frame(minHeight: 52)
    }

    private func searchCameras() {
        guard !isSearching else { return }
        attemptedAutomaticSearch = true
        errorMessage = nil
        guard let box = discovery.boxes.first(where: { $0.deviceID == binding.deviceID }) else {
            errorMessage = "没有在当前 Wi-Fi 找到已绑定盒子，请确认手机与盒子连接同一网络。"
            showManualEntry = true
            return
        }
        isSearching = true
        Task {
            defer { isSearching = false }
            do {
                candidates = try await discovery.discoverCameras(box: box)
                if let first = candidates.first { select(first) }
                if candidates.isEmpty {
                    errorMessage = "没有发现可连接的摄像头，可检查供电和网络后重试。"
                    showManualEntry = true
                }
            } catch {
                errorMessage = error.localizedDescription
                showManualEntry = true
            }
        }
    }

    private func select(_ candidate: DiscoveredCamera) {
        selectedCandidateID = candidate.id
        host = candidate.host
        port = String(candidate.port)
        streamPath = candidate.path
        errorMessage = nil
    }

    private func save() {
        guard canSave, !isSaving else { return }
        let cleanName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let path = streamPath.trimmingCharacters(in: .whitespacesAndNewlines)
        let normalizedPath = path.hasPrefix("/") ? path : "/\(path)"
        let streamURL = existing == nil
            ? "rtsp://\(host.trimmingCharacters(in: .whitespacesAndNewlines)):\(port)\(normalizedPath)"
            : ""
        isSaving = true
        errorMessage = nil
        Task {
            let success = await onSave(CameraConnectionValues(
                name: cleanName,
                room: room,
                streamURL: streamURL,
                username: username.trimmingCharacters(in: .whitespacesAndNewlines),
                password: password,
                enabled: enabled
            ))
            if !success { errorMessage = "配置未能保存，请检查网络后重试。" }
            isSaving = false
        }
    }
}
