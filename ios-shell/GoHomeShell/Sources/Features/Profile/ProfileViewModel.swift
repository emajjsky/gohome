import Foundation

@MainActor
final class ProfileViewModel: ObservableObject {
    @Published private(set) var state: Loadable<ProfileData>
    @Published private(set) var savingRules = false
    @Published private(set) var savingPreferences = false
    @Published private(set) var deviceActionID: String?
    @Published private(set) var inlineError: String?

    let user: AppUser
    let family: AppFamily

    private let repository: AppRepository?
    private let scope: CacheScope?
    private var loadTask: Task<Void, Never>?
    private var hasStarted = false

    init(
        user: AppUser,
        family: AppFamily,
        repository: AppRepository?,
        scope: CacheScope?,
        seed: ProfileData? = nil
    ) {
        self.user = user
        self.family = family
        self.repository = repository
        self.scope = scope
        state = Loadable(value: seed, isRefreshing: false, staleReason: nil)
    }

    var role: FamilyRole {
        FamilyRole.resolve(familyRole: family.role, canEdit: state.value?.rules.canEdit ?? false)
    }

    var canEditRules: Bool { role == .creator }
    var canManageDevices: Bool { role == .creator }

    func start() {
        guard !hasStarted else { return }
        hasStarted = true
        refresh()
    }

    func refresh() {
        guard let repository, let scope else { return }
        loadTask?.cancel()
        loadTask = Task { [repository, scope] in
            await repository.profile(scope: scope) { next in
                await MainActor.run {
                    self.state = next
                }
            }
        }
    }

    func saveRules(_ rules: FamilyRules) {
        guard canEditRules, !savingRules, let repository, let scope else { return }
        let original = state.value
        savingRules = true
        inlineError = nil
        replaceRules(rules)

        Task { [repository, scope] in
            do {
                let updated = try await repository.updateRules(familyID: scope.familyID, patch: rules.editablePayload)
                replaceRules(updated)
                await persist()
            } catch {
                if let original { state.value = original }
                inlineError = "守护规则未能保存，请重试"
            }
            savingRules = false
        }
    }

    func savePreferences(_ preferences: CarePreferences) {
        guard !savingPreferences, let repository, let scope else { return }
        let original = state.value
        savingPreferences = true
        inlineError = nil
        replacePreferences(preferences)

        Task { [repository, scope] in
            do {
                let updated = try await repository.updateCarePreferences(
                    familyID: scope.familyID,
                    patch: preferences.editablePayload
                )
                replacePreferences(updated)
                await persist()
            } catch {
                if let original { state.value = original }
                inlineError = "内容偏好未能保存，请重试"
            }
            savingPreferences = false
        }
    }

    func clearError() {
        inlineError = nil
    }

    func createCamera(
        binding: DeviceBinding,
        name: String,
        room: String,
        streamURL: String,
        username: String,
        password: String
    ) async -> Bool {
        guard canManageDevices, deviceActionID == nil, let repository, let scope else { return false }
        deviceActionID = "camera-new"
        inlineError = nil
        defer { deviceActionID = nil }
        do {
            let camera = try await repository.createCamera(CameraCreateRequest(
                familyID: scope.familyID,
                deviceID: binding.deviceID,
                name: name,
                room: room,
                streamURL: streamURL,
                username: username,
                password: password,
                enabled: true
            ))
            replaceCamera(camera)
            await persist()
            return true
        } catch {
            inlineError = error.localizedDescription
            return false
        }
    }

    func updateCamera(_ camera: CameraConfig, name: String, room: String, enabled: Bool) async -> Bool {
        guard canManageDevices, deviceActionID == nil, let repository else { return false }
        deviceActionID = "camera-\(camera.id)"
        inlineError = nil
        defer { deviceActionID = nil }
        do {
            let updated = try await repository.updateCamera(
                id: camera.id,
                request: CameraUpdateRequest(name: name, room: room, enabled: enabled)
            )
            replaceCamera(updated)
            await persist()
            return true
        } catch {
            inlineError = error.localizedDescription
            return false
        }
    }

    func deleteCamera(_ camera: CameraConfig) async -> Bool {
        guard canManageDevices, deviceActionID == nil, let repository else { return false }
        deviceActionID = "camera-\(camera.id)"
        inlineError = nil
        defer { deviceActionID = nil }
        do {
            try await repository.deleteCamera(id: camera.id)
            guard var value = state.value else { return true }
            value.cameras.removeAll { $0.id == camera.id }
            state.value = value
            await persist()
            return true
        } catch {
            inlineError = error.localizedDescription
            return false
        }
    }

    func unbindDevice(_ binding: DeviceBinding) async -> Bool {
        guard canManageDevices, deviceActionID == nil, let repository else { return false }
        deviceActionID = "binding-\(binding.id)"
        inlineError = nil
        defer { deviceActionID = nil }
        do {
            _ = try await repository.unbindDevice(bindingID: binding.id)
            guard var value = state.value else { return true }
            value.bindings.removeAll { $0.id == binding.id }
            value.cameras.removeAll { $0.deviceID == binding.deviceID }
            state.value = value
            await persist()
            return true
        } catch {
            inlineError = error.localizedDescription
            return false
        }
    }

    private func replaceRules(_ rules: FamilyRules) {
        guard var value = state.value else { return }
        value.rules = rules
        state.value = value
    }

    private func replacePreferences(_ preferences: CarePreferences) {
        guard var value = state.value else { return }
        value.carePreferences = preferences
        state.value = value
    }

    private func replaceCamera(_ camera: CameraConfig) {
        guard var value = state.value else { return }
        if let index = value.cameras.firstIndex(where: { $0.id == camera.id }) {
            value.cameras[index] = camera
        } else {
            value.cameras.append(camera)
        }
        state.value = value
    }

    private func persist() async {
        guard let repository, let scope, let value = state.value else { return }
        await repository.cacheProfile(value, scope: scope)
    }

    deinit {
        loadTask?.cancel()
    }
}
