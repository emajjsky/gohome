import SwiftUI

enum HomeLocationProfileUpdate {
    static func payload(
        preserving profile: ElderProfile,
        latitude: Double,
        longitude: Double,
        location: ResolvedLocation?
    ) -> ProfilePayload {
        let city = location?.city.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let district = location?.district.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let label = location?.displayName.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return ProfilePayload(
            displayName: profile.displayName,
            relationship: profile.relationship,
            city: city.isEmpty ? profile.city : city,
            district: district.isEmpty ? profile.district : district,
            phone: profile.phone,
            mobilePhone: profile.mobilePhone,
            homePhone: profile.homePhone,
            homeLatitude: latitude,
            homeLongitude: longitude,
            homeLocationLabel: label.isEmpty ? "家庭位置" : label
        )
    }
}

struct HomeLocationSetupView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var locationProvider = MemoryLocationProvider()
    @State private var profile: ElderProfile?
    @State private var isLoadingProfile = false
    @State private var isSaving = false
    @State private var errorMessage: String?

    let service: OnboardingService
    let familyID: String
    let onSaved: () -> Void

    init(
        service: OnboardingService,
        familyID: String,
        profile: ElderProfile? = nil,
        onSaved: @escaping () -> Void
    ) {
        self.service = service
        self.familyID = familyID
        self.onSaved = onSaved
        _profile = State(initialValue: profile)
    }

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 22) {
                Image(systemName: "house.and.flag.fill")
                    .font(.system(size: 25, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.ink)
                    .frame(width: 48, height: 48)
                    .background(GoHomeTheme.paleGinger, in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))

                VStack(alignment: .leading, spacing: 7) {
                    Text("家庭固定位置")
                        .font(.system(size: 24, weight: .bold, design: .rounded))
                    Text("用于计算手机与家的距离，并查找家庭附近的社区服务。")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }

                Button { locationProvider.requestLocation() } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "location.fill")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundStyle(GoHomeTheme.ginger)
                            .frame(width: 34, height: 34)
                            .background(GoHomeTheme.paleGinger, in: Circle())
                        VStack(alignment: .leading, spacing: 3) {
                            Text(locationProvider.resolvedLocation?.displayName ?? "使用当前位置")
                                .font(.system(size: 15, weight: .bold))
                                .foregroundStyle(GoHomeTheme.ink)
                            Text(locationProvider.coordinate == nil ? "仅保存为当前家庭的固定位置" : "位置已获取，可确认保存")
                                .font(.system(size: 11, weight: .medium))
                                .foregroundStyle(GoHomeTheme.mutedInk)
                        }
                        Spacer()
                        if locationProvider.isLocating {
                            ProgressView().controlSize(.small)
                        } else {
                            Image(systemName: "chevron.right")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(GoHomeTheme.mutedInk)
                        }
                    }
                    .padding(.horizontal, 14)
                    .frame(minHeight: 66)
                    .background(Color.black.opacity(0.028), in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
                }
                .buttonStyle(.plain)
                .disabled(locationProvider.isLocating || isSaving)
                .accessibilityIdentifier("home-location-use-current")

                if isLoadingProfile {
                    ProgressView("正在读取照护资料")
                        .font(.system(size: 13, weight: .medium))
                }

                if let message = locationMessage {
                    Label(message, systemImage: "exclamationmark.circle")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }

                Spacer()

                Button(action: save) {
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
                .disabled(!canSave)
                .opacity(canSave ? 1 : 0.38)
                .accessibilityIdentifier("home-location-save")
            }
            .padding(24)
            .background(GoHomeTheme.paper.ignoresSafeArea())
            .navigationTitle("设置家庭位置")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                        .disabled(isSaving)
                }
            }
            .task { await loadProfileIfNeeded() }
        }
        .interactiveDismissDisabled(isSaving)
    }

    private var canSave: Bool {
        profile != nil
            && locationProvider.coordinate != nil
            && !isLoadingProfile
            && !isSaving
    }

    private var locationMessage: String? {
        if locationProvider.coordinate != nil, locationProvider.resolvedLocation == nil {
            return "位置已获取，地址名称暂不可用，仍可保存"
        }
        return locationProvider.errorMessage ?? errorMessage
    }

    @MainActor
    private func loadProfileIfNeeded() async {
        guard profile == nil, !isLoadingProfile else { return }
        isLoadingProfile = true
        errorMessage = nil
        do {
            profile = try await service.profile(familyID: familyID)
        } catch {
            errorMessage = "照护资料读取失败，请稍后重试"
        }
        isLoadingProfile = false
    }

    private func save() {
        guard
            let profile,
            let coordinate = locationProvider.coordinate
        else { return }
        let payload = HomeLocationProfileUpdate.payload(
            preserving: profile,
            latitude: coordinate.latitude,
            longitude: coordinate.longitude,
            location: locationProvider.resolvedLocation
        )
        isSaving = true
        errorMessage = nil
        Task {
            do {
                _ = try await service.saveProfile(
                    familyID: familyID,
                    elderID: profile.elderID,
                    profile: payload
                )
                onSaved()
                dismiss()
            } catch {
                errorMessage = "家庭位置保存失败，请稍后重试"
            }
            isSaving = false
        }
    }
}
