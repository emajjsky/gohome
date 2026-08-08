import SwiftUI

enum DeviceBindingPresentation {
    case onboarding
    case management
}

enum DeviceBindingHomeLocationDecision {
    case complete
    case confirm(ElderProfile)
    case retry

    static func resolve(_ result: Result<ElderProfile, Error>) -> Self {
        guard case let .success(profile) = result else { return .retry }
        guard profile.homeLatitude == nil || profile.homeLongitude == nil else { return .complete }
        return .confirm(profile)
    }
}

struct CloudDeviceLoadState {
    private(set) var devices: [ClaimableDevice] = []
    private(set) var errorMessage: String?

    mutating func beginLoading() {
        errorMessage = nil
    }

    mutating func resolve(_ result: Result<[ClaimableDevice], Error>) {
        switch result {
        case let .success(devices):
            self.devices = devices
            errorMessage = nil
        case .failure:
            errorMessage = "云端设备列表暂时无法更新，可继续使用局域网发现或重试。"
        }
    }
}

struct DeviceBindingView: View {
    let familyID: String?
    let service: OnboardingService
    let onComplete: @MainActor () -> Void
    var presentation: DeviceBindingPresentation = .onboarding
    @StateObject private var discovery = BoxDiscoveryService()
    @StateObject private var homeLocationProvider = MemoryLocationProvider()
    @State private var cloudDeviceState = CloudDeviceLoadState()
    @State private var isLoadingCloud = false
    @State private var isBinding = false
    @State private var bindingDeviceID: String?
    @State private var errorMessage: String?
    @State private var pendingProfile: ElderProfile?
    @State private var showsHomeLocationConfirmation = false
    @State private var isSavingHomeLocation = false
    @State private var homeLocationError: String?
    @State private var homeLocationRetryFamilyID: String?

    var body: some View {
        Group {
            switch presentation {
            case .onboarding:
                OnboardingPage(index: 3, title: "连接守护盒子", subtitle: "手机与盒子连接同一 Wi-Fi，系统会自动发现它。") {
                    bindingContent
                }
            case .management:
                ScrollView {
                    bindingContent
                        .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
                        .padding(.top, 18)
                        .padding(.bottom, 28)
                }
                .background(GoHomeTheme.paper)
                .profileNavigationTitle("添加家庭盒子")
            }
        }
        .accessibilityIdentifier("onboarding-device")
        .onAppear {
            discovery.start()
            loadCloudDevices()
        }
        .onDisappear { discovery.stop() }
        .sheet(isPresented: $showsHomeLocationConfirmation) {
            HomeLocationConfirmationView(
                provider: homeLocationProvider,
                isSaving: isSavingHomeLocation,
                saveError: homeLocationError,
                onConfirm: saveHomeLocation,
                onSkip: completeWithoutHomeLocation
            )
        }
    }

    private var bindingContent: some View {
        VStack(alignment: .leading, spacing: 18) {
                HStack(spacing: 12) {
                    Image(systemName: discovery.isSearching ? "dot.radiowaves.left.and.right" : "wifi")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(Color.black)
                        .frame(width: 42, height: 42)
                        .background(GoHomeTheme.paleGinger, in: Circle())
                    VStack(alignment: .leading, spacing: 3) {
                        Text(discovery.isSearching ? "正在搜索附近设备" : "搜索已暂停")
                            .font(.system(size: 15, weight: .semibold))
                        Text("仅发现局域网内的回家盒子")
                            .font(.system(size: 12))
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                }

                if allDevices.isEmpty {
                    VStack(spacing: 10) {
                        Image(systemName: "shippingbox")
                            .font(.system(size: 28))
                            .foregroundStyle(.secondary)
                        Text(cloudDeviceState.errorMessage == nil ? "没有发现设备" : "设备列表未能更新")
                            .font(.system(size: 15, weight: .semibold))
                        Text(cloudDeviceState.errorMessage == nil ? "确认盒子已通电，并与手机连接同一 Wi-Fi" : "请检查网络后重新搜索")
                            .font(.system(size: 12))
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 34)
                    .background(Color.black.opacity(0.035), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                } else {
                    ForEach(allDevices) { device in
                        Button { bind(device) } label: {
                            HStack(spacing: 12) {
                                if bindingDeviceID == device.deviceID {
                                    ProgressView().tint(.black)
                                        .frame(width: 20)
                                } else {
                                    Image(systemName: "cube.transparent")
                                        .foregroundStyle(Color.black)
                                        .frame(width: 20)
                                }
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(device.name)
                                        .font(.system(size: 15, weight: .semibold))
                                        .foregroundStyle(.black)
                                    Text(device.serialNumber ?? device.deviceID)
                                        .font(.system(size: 12, design: .monospaced))
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                if bindingDeviceID == device.deviceID {
                                    Text("正在绑定")
                                        .font(.system(size: 12, weight: .semibold))
                                        .foregroundStyle(.secondary)
                                } else {
                                    Image(systemName: "chevron.right")
                                        .font(.caption.weight(.bold))
                                        .foregroundStyle(.secondary)
                                }
                            }
                            .padding(16)
                            .background(Color.black.opacity(0.045), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                        }
                        .disabled(isBinding)
                    }
                }

                Button("重新搜索") {
                    discovery.start()
                    loadCloudDevices()
                }
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(.black)
                .frame(maxWidth: .infinity)
                .frame(height: 48)
                .background(GoHomeTheme.paleGinger, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .disabled(isBinding)

                OnboardingError(message: errorMessage ?? cloudDeviceState.errorMessage)
                if let familyID = homeLocationRetryFamilyID {
                    Button("重新读取家庭位置") {
                        Task { await offerHomeLocation(for: familyID) }
                    }
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.ink)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .background(GoHomeTheme.paleGinger, in: RoundedRectangle(cornerRadius: GoHomeTheme.controlRadius, style: .continuous))
                    .disabled(isBinding)
                    .accessibilityIdentifier("home-location-retry")
                }
        }
    }

    private var allDevices: [DiscoveredBox] {
        var result = discovery.boxes
        let localIDs = Set(result.map(\.deviceID))
        result += cloudDeviceState.devices
            .filter { !localIDs.contains($0.deviceID) }
            .map { DiscoveredBox(id: $0.deviceID, name: $0.name, deviceID: $0.deviceID, serialNumber: $0.serialNumber) }
        return result
    }

    private func loadCloudDevices() {
        guard let familyID, !isLoadingCloud else { return }
        isLoadingCloud = true
        cloudDeviceState.beginLoading()
        Task {
            defer { isLoadingCloud = false }
            do {
                cloudDeviceState.resolve(.success(try await service.availableDevices(familyID: familyID)))
            } catch {
                cloudDeviceState.resolve(.failure(error))
            }
        }
    }

    private func bind(_ device: DiscoveredBox) {
        guard let familyID, !isBinding else { return }
        isBinding = true
        bindingDeviceID = device.deviceID
        errorMessage = nil
        Task {
            do {
                if discovery.supportsLocalPairing(device) {
                    let bindingCode = try await service.createBindingCode(familyID: familyID)
                    try await discovery.pair(box: device, code: bindingCode.code, returnURL: service.pairReturnURL)
                } else {
                    _ = try await service.claimDevice(familyID: familyID, device: device)
                }
                await offerHomeLocation(for: familyID)
            } catch {
                errorMessage = error.localizedDescription
                bindingDeviceID = nil
                isBinding = false
            }
        }
    }

    @MainActor
    private func offerHomeLocation(for familyID: String) async {
        bindingDeviceID = nil
        isBinding = false
        homeLocationRetryFamilyID = nil
        let result: Result<ElderProfile, Error>
        do {
            result = .success(try await service.profile(familyID: familyID))
        } catch {
            result = .failure(error)
        }
        switch DeviceBindingHomeLocationDecision.resolve(result) {
        case .retry:
            errorMessage = "盒子已绑定，但家庭位置读取失败，请重试"
            homeLocationRetryFamilyID = familyID
        case .complete:
            errorMessage = nil
            onComplete()
        case let .confirm(profile):
            errorMessage = nil
            pendingProfile = profile
            homeLocationError = nil
            showsHomeLocationConfirmation = true
        }
    }

    private func saveHomeLocation() {
        guard
            let familyID,
            let profile = pendingProfile,
            let coordinate = homeLocationProvider.coordinate
        else { return }
        let payload = HomeLocationProfileUpdate.payload(
            preserving: profile,
            latitude: coordinate.latitude,
            longitude: coordinate.longitude,
            location: homeLocationProvider.resolvedLocation
        )
        isSavingHomeLocation = true
        homeLocationError = nil
        Task {
            do {
                _ = try await service.saveProfile(familyID: familyID, profile: payload)
                showsHomeLocationConfirmation = false
                pendingProfile = nil
                onComplete()
            } catch {
                homeLocationError = error.localizedDescription
            }
            isSavingHomeLocation = false
        }
    }

    private func completeWithoutHomeLocation() {
        showsHomeLocationConfirmation = false
        pendingProfile = nil
        onComplete()
    }
}

private struct HomeLocationConfirmationView: View {
    @ObservedObject var provider: MemoryLocationProvider
    let isSaving: Bool
    let saveError: String?
    let onConfirm: () -> Void
    let onSkip: () -> Void

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 22) {
                Image(systemName: "house.and.flag.fill")
                    .font(.system(size: 25, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.ink)
                    .frame(width: 48, height: 48)
                    .background(GoHomeTheme.paleGinger, in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))

                VStack(alignment: .leading, spacing: 7) {
                    Text("确认家庭位置")
                        .font(.system(size: 24, weight: .bold, design: .rounded))
                    Text(locationText)
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }

                if provider.isLocating {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 20)
                }

                if let message = provider.errorMessage ?? saveError {
                    Label(message, systemImage: "exclamationmark.circle")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }

                Spacer()

                Button(action: onConfirm) {
                    HStack(spacing: 8) {
                        if isSaving { ProgressView().tint(.white) }
                        Text(isSaving ? "保存中" : "设为家庭位置")
                    }
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .frame(height: 52)
                    .background(GoHomeTheme.ink, in: RoundedRectangle(cornerRadius: GoHomeTheme.controlRadius, style: .continuous))
                }
                .disabled(provider.coordinate == nil || isSaving)
                .opacity(provider.coordinate == nil || isSaving ? 0.38 : 1)

                Button("稍后设置", action: onSkip)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.mutedInk)
                    .frame(maxWidth: .infinity)
                    .disabled(isSaving)
            }
            .padding(24)
            .background(GoHomeTheme.paper.ignoresSafeArea())
            .task { provider.requestLocation() }
        }
        .presentationDetents([.medium])
        .interactiveDismissDisabled(true)
    }

    private var locationText: String {
        if let location = provider.resolvedLocation { return location.displayName }
        if provider.coordinate != nil { return "已获取新位置，可确认保存" }
        return provider.isLocating ? "正在获取当前位置" : "绑定后可用于回家距离与家庭附近服务"
    }
}
