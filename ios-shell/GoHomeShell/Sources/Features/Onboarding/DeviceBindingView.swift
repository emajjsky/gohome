import SwiftUI

struct DeviceBindingView: View {
    let familyID: String?
    let service: OnboardingService
    let onComplete: @MainActor () -> Void
    @StateObject private var discovery = BoxDiscoveryService()
    @State private var cloudDevices: [ClaimableDevice] = []
    @State private var isLoadingCloud = false
    @State private var isBinding = false
    @State private var errorMessage: String?

    var body: some View {
        OnboardingPage(index: 3, title: "连接守护盒子", subtitle: "手机与盒子连接同一 Wi-Fi，系统会自动发现它。") {
            VStack(alignment: .leading, spacing: 18) {
                HStack(spacing: 12) {
                    Image(systemName: discovery.isSearching ? "dot.radiowaves.left.and.right" : "wifi")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(Color.black)
                        .frame(width: 42, height: 42)
                        .background(Color.yellow.opacity(0.82), in: Circle())
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
                        Text("没有发现设备")
                            .font(.system(size: 15, weight: .semibold))
                        Text("确认盒子已通电，并与手机连接同一 Wi-Fi")
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
                                Image(systemName: "cube.transparent")
                                    .foregroundStyle(Color.black)
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(device.name)
                                        .font(.system(size: 15, weight: .semibold))
                                        .foregroundStyle(.black)
                                    Text(device.serialNumber ?? device.deviceID)
                                        .font(.system(size: 12, design: .monospaced))
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.caption.weight(.bold))
                                    .foregroundStyle(.secondary)
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
                .background(Color.yellow.opacity(0.5), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .disabled(isBinding)

                OnboardingError(message: errorMessage)
            }
        }
        .accessibilityIdentifier("onboarding-device")
        .onAppear {
            discovery.start()
            loadCloudDevices()
        }
        .onDisappear { discovery.stop() }
    }

    private var allDevices: [DiscoveredBox] {
        var result = discovery.boxes
        let localIDs = Set(result.map(\.deviceID))
        result += cloudDevices
            .filter { !localIDs.contains($0.deviceID) }
            .map { DiscoveredBox(id: $0.deviceID, name: $0.name, deviceID: $0.deviceID, serialNumber: $0.serialNumber) }
        return result
    }

    private func loadCloudDevices() {
        guard !isLoadingCloud else { return }
        isLoadingCloud = true
        Task {
            defer { isLoadingCloud = false }
            cloudDevices = (try? await service.availableDevices()) ?? []
        }
    }

    private func bind(_ device: DiscoveredBox) {
        guard let familyID, !isBinding else { return }
        isBinding = true
        errorMessage = nil
        Task {
            do {
                if discovery.supportsLocalPairing(device) {
                    let bindingCode = try await service.createBindingCode(familyID: familyID)
                    try await discovery.pair(box: device, code: bindingCode.code, returnURL: service.pairReturnURL)
                } else {
                    _ = try await service.claimDevice(familyID: familyID, device: device)
                }
                onComplete()
            } catch {
                errorMessage = error.localizedDescription
            }
            isBinding = false
        }
    }
}
