import PhotosUI
import SwiftUI
import UIKit

struct AccountProfileEditor: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var model: ProfileViewModel
    let apiClient: APIClient?
    @StateObject private var location = MemoryLocationProvider()
    @State private var displayName: String
    @State private var city: String
    @State private var district: String
    @State private var selectedPhoto: PhotosPickerItem?
    @State private var avatarImage: UIImage?
    @State private var avatarJPEG: Data?
    @State private var showsCityPicker = false
    @State private var saveTask: Task<Void, Never>?

    init(model: ProfileViewModel, apiClient: APIClient?) {
        self.model = model
        self.apiClient = apiClient
        _displayName = State(initialValue: model.accountProfile.displayName)
        _city = State(initialValue: model.accountProfile.city)
        _district = State(initialValue: model.accountProfile.district)
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                PhotosPicker(selection: $selectedPhoto, matching: .images) {
                    avatarPicker
                }
                .buttonStyle(.plain)
                .accessibilityLabel("更换头像")
                .accessibilityIdentifier("profile-avatar-picker")

                VStack(spacing: 0) {
                    editorField("昵称", text: $displayName, prompt: "填写昵称")
                    Button { showsCityPicker = true } label: {
                        editorRow(title: "城市", value: normalized(city) ?? "选择城市")
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("profile-city-selector")
                    editorField("区域", text: $district, prompt: "例如 徐汇区")
                    locationAction
                    if location.errorMessage != nil {
                        Button("前往系统设置") { openSystemSettings() }
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(GoHomeTheme.ink)
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .trailing)
                    }
                }
                .padding(.horizontal, 16)
                .background(Color.black.opacity(0.035), in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))

                if let error = model.inlineError {
                    Text(error)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 24)
        }
        .background(GoHomeTheme.paper)
        .profileNavigationTitle("个人资料")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(model.savingAccountProfile ? "保存中" : "保存") { save() }
                    .fontWeight(.semibold)
                    .disabled(model.savingAccountProfile || normalized(displayName) == nil)
                    .accessibilityIdentifier("profile-save-account")
            }
        }
        .sheet(isPresented: $showsCityPicker) {
            CitySelectionView(selection: $city)
        }
        .onChange(of: selectedPhoto) { item in
            guard let item else { return }
            Task { await loadAvatar(item) }
        }
        .onChange(of: location.resolvedLocation) { value in
            guard let value else { return }
            city = value.city
            district = value.district
        }
        .onAppear { model.clearError() }
        .onDisappear {
            saveTask?.cancel()
            model.cancelInFlightAccountProfileRefresh()
        }
    }

    private var avatarPicker: some View {
        ZStack(alignment: .bottomTrailing) {
            if let avatarImage {
                Image(uiImage: avatarImage)
                    .resizable()
                    .scaledToFill()
                    .frame(width: 92, height: 92)
                    .clipShape(Circle())
            } else {
                AccountAvatar(
                    profile: model.accountProfile,
                    apiClient: apiClient,
                    size: 92
                )
            }
            Image(systemName: "camera.fill")
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(GoHomeTheme.ink)
                .frame(width: 30, height: 30)
                .background(GoHomeTheme.ginger, in: Circle())
                .overlay(Circle().stroke(GoHomeTheme.paper, lineWidth: 3))
        }
    }

    private var locationAction: some View {
        Button { location.requestLocation() } label: {
            HStack {
                Text("当前位置")
                Spacer()
                if location.isLocating { ProgressView().controlSize(.small) }
                Text(location.errorMessage == nil ? "使用系统定位" : "需要位置权限")
                    .foregroundStyle(GoHomeTheme.mutedInk)
                Image(systemName: "location.fill")
                    .foregroundStyle(GoHomeTheme.ginger)
            }
            .font(.system(size: 14, weight: .medium))
            .frame(minHeight: 50)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("profile-location-action")
    }

    private func editorField(_ title: String, text: Binding<String>, prompt: String) -> some View {
        HStack(spacing: 12) {
            Text(title).frame(width: 56, alignment: .leading)
            TextField(prompt, text: text).multilineTextAlignment(.trailing)
        }
        .font(.system(size: 14, weight: .medium))
        .frame(maxWidth: .infinity, minHeight: 50)
        .contentShape(Rectangle())
        .overlay(alignment: .bottom) { Rectangle().fill(GoHomeTheme.line).frame(height: 0.5) }
    }

    private func editorRow(title: String, value: String) -> some View {
        HStack {
            Text(title)
            Spacer()
            Text(value).foregroundStyle(value == "选择城市" ? GoHomeTheme.mutedInk : GoHomeTheme.ink)
            Image(systemName: "chevron.right").font(.caption.weight(.bold)).foregroundStyle(GoHomeTheme.mutedInk)
        }
        .font(.system(size: 14, weight: .medium))
        .frame(maxWidth: .infinity, minHeight: 50)
        .contentShape(Rectangle())
        .overlay(alignment: .bottom) { Rectangle().fill(GoHomeTheme.line).frame(height: 0.5) }
    }

    private func loadAvatar(_ item: PhotosPickerItem) async {
        guard let data = try? await item.loadTransferable(type: Data.self), let source = UIImage(data: data) else { return }
        let maxSide: CGFloat = 768
        let scale = min(1, maxSide / max(source.size.width, source.size.height))
        let size = CGSize(width: max(1, source.size.width * scale), height: max(1, source.size.height * scale))
        let renderer = UIGraphicsImageRenderer(size: size)
        let resized = renderer.image { _ in source.draw(in: CGRect(origin: .zero, size: size)) }
        guard let compressed = resized.jpegData(compressionQuality: 0.78) else { return }
        avatarImage = resized
        avatarJPEG = compressed
    }

    private func save() {
        guard saveTask == nil else { return }
        saveTask = Task { @MainActor in
            defer { saveTask = nil }
            if await model.saveAccountProfile(
                displayName: displayName,
                city: city,
                district: district,
                avatarJPEG: avatarJPEG
            ) { dismiss() }
        }
    }

    private func openSystemSettings() {
        guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
        UIApplication.shared.open(url)
    }

    private func normalized(_ value: String) -> String? {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}

struct AccountAvatar: View {
    let profile: AccountProfile
    let apiClient: APIClient?
    let size: CGFloat
    @State private var image: UIImage?

    var body: some View {
        ZStack {
            Circle().fill(GoHomeTheme.ink)
            if let image {
                Image(uiImage: image).resizable().scaledToFill()
            } else if let bundledAvatar = GoHomeImageResource.loadJPEG(named: "avatar") {
                Image(uiImage: bundledAvatar).resizable().scaledToFill()
            } else {
                Image(systemName: "person.fill")
                    .font(.system(size: size * 0.38, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.paleGinger)
            }
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        .task(id: profile.avatarAssetID) { await load() }
    }

    private func load() async {
        guard let apiClient, !profile.avatarAssetID.isEmpty else { image = nil; return }
        let data = try? await apiClient.data(
            path: "/api/v1/video/assets/\(profile.avatarAssetID)",
            queryItems: [URLQueryItem(name: "variant", value: "grid")]
        )
        image = data.flatMap(UIImage.init(data:))
    }
}
