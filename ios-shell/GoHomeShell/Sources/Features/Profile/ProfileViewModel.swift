import Foundation

enum DeviceOperationProgress: Equatable {
    case saving(String)
    case syncing(cameraID: String?, message: String)
    case ready(String)

    var message: String {
        switch self {
        case let .saving(message), let .syncing(_, message), let .ready(message): return message
        }
    }

    var showsActivity: Bool {
        if case .ready = self { return false }
        return true
    }
}

@MainActor
final class ProfileViewModel: ObservableObject {
    @Published private(set) var state: Loadable<ProfileData>
    @Published private(set) var savingRules = false
    @Published private(set) var savingPreferences = false
    @Published private(set) var savingProductPreferences = false
    @Published private(set) var savingElderProfile = false
    @Published private(set) var deviceActionID: String?
    @Published private(set) var deviceProgress: DeviceOperationProgress?
    @Published private(set) var deviceConfigurationRevision = 0
    @Published private(set) var inlineError: String?
    @Published private(set) var familyMembers: [FamilyMember]
    @Published private(set) var familyActionID: String?
    @Published private(set) var familyInvitations: [FamilyInvitation] = []
    @Published private(set) var invitationActionID: String?
    @Published private(set) var accountProfile: AccountProfile
    @Published private(set) var savingAccountProfile = false

    let user: AppUser
    let family: AppFamily

    private let repository: AppRepository?
    private let scope: CacheScope?
    private var loadTask: Task<Void, Never>?
    private var deviceReconciliationTask: Task<Void, Never>?
    private var deviceProgressDismissTask: Task<Void, Never>?
    private var hasStarted = false
    private let onFamilyChanged: () -> Void
    private let onAccountProfileChanged: (AccountProfile) -> Void

    init(
        user: AppUser,
        family: AppFamily,
        repository: AppRepository?,
        scope: CacheScope?,
        seed: ProfileData? = nil,
        onFamilyChanged: @escaping () -> Void = {},
        onAccountProfileChanged: @escaping (AccountProfile) -> Void = { _ in }
    ) {
        self.user = user
        self.family = family
        self.repository = repository
        self.scope = scope
        self.onFamilyChanged = onFamilyChanged
        self.onAccountProfileChanged = onAccountProfileChanged
        accountProfile = AccountProfile(user: user)
        state = Loadable(value: seed, isRefreshing: false, staleReason: nil)
        familyMembers = [FamilyMember(
            id: "current-\(user.id)",
            userID: user.id,
            displayName: user.displayName ?? "回家用户",
            accountHint: user.phone ?? "",
            role: family.role ?? "member",
            isCurrentUser: true,
            joinedAt: nil
        )]
    }

    var role: FamilyRole {
        FamilyRole.resolve(familyRole: family.role, canEdit: state.value?.rules.canEdit ?? false)
    }

    var canEditRules: Bool { role == .creator }
    var canManageDevices: Bool { role == .creator }
    var activeFamilyInvitation: FamilyInvitation? {
        familyInvitations.first(where: \.isActive)
    }

    func start() {
        guard !hasStarted else { return }
        hasStarted = true
        refresh()
        refreshAccountProfile()
    }

    func refreshAccountProfile() {
        guard let repository else { return }
        Task { [repository] in
            do {
                let profile = try await repository.accountProfile()
                accountProfile = profile
                onAccountProfileChanged(profile)
            } catch {
                if accountProfile.displayName.isEmpty { inlineError = "账户资料暂时无法更新" }
            }
        }
    }

    func saveAccountProfile(
        displayName: String,
        city: String,
        district: String,
        avatarJPEG: Data?
    ) async -> Bool {
        guard !savingAccountProfile, let repository, let scope else { return false }
        let original = accountProfile
        let trimmedName = displayName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedName.isEmpty, trimmedName.count <= 40 else {
            inlineError = "昵称请填写 1 到 40 个字符"
            return false
        }
        savingAccountProfile = true
        inlineError = nil
        defer { savingAccountProfile = false }
        do {
            var avatarAssetID = original.avatarAssetID
            if let avatarJPEG {
                avatarAssetID = try await repository.uploadMemoryMediaBatch(
                    familyID: scope.familyID,
                    media: [MemoryUploadAsset(
                        data: avatarJPEG,
                        contentType: "image/jpeg",
                        pixelWidth: 768,
                        pixelHeight: 768,
                        durationSeconds: nil
                    )]
                ).first?.id ?? original.avatarAssetID
            }
            let updated = try await repository.updateAccountProfile(AccountProfilePatch(
                displayName: trimmedName,
                city: city.trimmingCharacters(in: .whitespacesAndNewlines),
                district: district.trimmingCharacters(in: .whitespacesAndNewlines),
                avatarAssetID: avatarAssetID
            ))
            accountProfile = updated
            onAccountProfileChanged(updated)
            return true
        } catch {
            accountProfile = original
            inlineError = "账户资料未能保存，请重试"
            return false
        }
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

    func saveProductPreferences(_ preferences: ProductPreferences) {
        guard !savingProductPreferences, let repository, let scope else { return }
        let original = state.value
        savingProductPreferences = true
        inlineError = nil
        replaceProductPreferences(preferences)

        Task { [repository, scope] in
            do {
                let updated = try await repository.updateProductPreferences(
                    familyID: scope.familyID,
                    preferences: preferences
                )
                replaceProductPreferences(updated)
                await persist()
            } catch {
                if let original { state.value = original }
                inlineError = "推荐偏好未能保存，请重试"
            }
            savingProductPreferences = false
        }
    }

    func saveElderProfile(_ payload: ProfilePayload) async -> Bool {
        guard canEditRules, !savingElderProfile, let repository, let scope else { return false }
        savingElderProfile = true
        inlineError = nil
        defer { savingElderProfile = false }
        do {
            let elderID = state.value?.elder?.elderID ?? "elder_primary"
            let updated = try await repository.updateElderProfile(
                familyID: scope.familyID,
                elderID: elderID,
                payload: payload
            )
            guard var value = state.value else { return true }
            value.elder = updated
            state.value = value
            await persist()
            return true
        } catch {
            inlineError = "照护资料未能保存，请重试"
            return false
        }
    }

    func clearError() {
        inlineError = nil
    }

    func refreshFamilyMembers() {
        guard let repository, familyActionID == nil else { return }
        familyActionID = "refresh-members"
        inlineError = nil
        let shouldLoadInvitations = canEditRules
        Task { [repository, familyID = family.id, shouldLoadInvitations] in
            defer { familyActionID = nil }
            do {
                async let members = repository.familyMembers(familyID: familyID)
                if shouldLoadInvitations {
                    async let invitations = repository.familyInvitations(familyID: familyID)
                    let (memberResponse, invitationResponse) = try await (members, invitations)
                    familyMembers = memberResponse.members
                    familyInvitations = invitationResponse.invitations
                } else {
                    let memberResponse = try await members
                    familyMembers = memberResponse.members
                    familyInvitations = []
                }
            } catch {
                inlineError = "家庭成员暂时无法更新"
            }
        }
    }

    func createFamilyInvitation() async -> Bool {
        guard canEditRules, invitationActionID == nil, let repository else { return false }
        invitationActionID = "create-invitation"
        inlineError = nil
        defer { invitationActionID = nil }
        do {
            let invitation = try await repository.createFamilyInvitation(familyID: family.id)
            familyInvitations = [invitation] + familyInvitations.map { existing in
                guard existing.isActive else { return existing }
                return FamilyInvitation(
                    id: existing.id,
                    familyID: existing.familyID,
                    status: "revoked",
                    codeHint: existing.codeHint,
                    code: nil,
                    expiresAt: existing.expiresAt,
                    createdAt: existing.createdAt,
                    usedAt: existing.usedAt,
                    revokedAt: existing.revokedAt
                )
            }
            return true
        } catch {
            inlineError = "邀请码暂时无法生成，请重试"
            return false
        }
    }

    func revokeFamilyInvitation(_ invitation: FamilyInvitation) async -> Bool {
        guard canEditRules, invitation.isActive, invitationActionID == nil, let repository else { return false }
        invitationActionID = invitation.id
        inlineError = nil
        defer { invitationActionID = nil }
        do {
            let revoked = try await repository.revokeFamilyInvitation(
                familyID: family.id,
                invitationID: invitation.id
            )
            familyInvitations = familyInvitations.map { $0.id == revoked.id ? revoked : $0 }
            return true
        } catch {
            inlineError = "邀请码暂时无法撤销，请重试"
            return false
        }
    }

    func removeFamilyMember(_ member: FamilyMember) async -> Bool {
        guard canEditRules, !member.isCurrentUser, familyActionID == nil, let repository else { return false }
        familyActionID = member.id
        inlineError = nil
        defer { familyActionID = nil }
        do {
            try await repository.removeFamilyMember(familyID: family.id, memberID: member.id)
            familyMembers.removeAll { $0.id == member.id }
            return true
        } catch {
            inlineError = "成员暂时无法移出，请重试"
            return false
        }
    }

    func leaveFamily() async -> Bool {
        guard role == .member, familyActionID == nil, let repository else { return false }
        familyActionID = "leave-family"
        inlineError = nil
        defer { familyActionID = nil }
        do {
            try await repository.leaveFamily(familyID: family.id)
            onFamilyChanged()
            return true
        } catch {
            inlineError = "暂时无法退出家庭，请重试"
            return false
        }
    }

    func transferOwnership(to member: FamilyMember) async -> Bool {
        guard canEditRules, !member.isCurrentUser, familyActionID == nil, let repository else { return false }
        familyActionID = member.id
        inlineError = nil
        defer { familyActionID = nil }
        do {
            try await repository.transferFamilyOwnership(familyID: family.id, memberID: member.id)
            onFamilyChanged()
            return true
        } catch {
            inlineError = "创建者身份暂时无法转让，请重试"
            return false
        }
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
        beginDeviceOperation(id: "camera-new", message: "正在保存摄像头")
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
            deviceConfigurationRevision += 1
            reconcileDeviceConfiguration(cameraID: camera.id, expectedToExist: true)
            return true
        } catch {
            deviceProgress = nil
            inlineError = error.localizedDescription
            return false
        }
    }

    func updateCamera(
        _ camera: CameraConfig,
        name: String,
        room: String,
        streamURL: String,
        username: String,
        password: String,
        enabled: Bool
    ) async -> Bool {
        guard canManageDevices, deviceActionID == nil, let repository else { return false }
        beginDeviceOperation(id: "camera-\(camera.id)", message: "正在保存摄像头设置")
        defer { deviceActionID = nil }
        do {
            let updated = try await repository.updateCamera(
                id: camera.id,
                request: CameraUpdateRequest(
                    name: name,
                    room: room,
                    streamURL: streamURL,
                    username: username.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
                    password: password.nilIfEmpty,
                    enabled: enabled
                )
            )
            replaceCamera(updated)
            await persist()
            deviceConfigurationRevision += 1
            reconcileDeviceConfiguration(cameraID: camera.id, expectedToExist: true)
            return true
        } catch {
            deviceProgress = nil
            inlineError = error.localizedDescription
            return false
        }
    }

    func deleteCamera(_ camera: CameraConfig) async -> Bool {
        guard canManageDevices, deviceActionID == nil, let repository else { return false }
        beginDeviceOperation(id: "camera-\(camera.id)", message: "正在删除摄像头")
        defer { deviceActionID = nil }
        do {
            try await repository.deleteCamera(id: camera.id)
            guard var value = state.value else { return true }
            value.cameras.removeAll { $0.id == camera.id }
            state.value = value
            await persist()
            deviceConfigurationRevision += 1
            reconcileDeviceConfiguration(cameraID: camera.id, expectedToExist: false)
            return true
        } catch {
            deviceProgress = nil
            inlineError = error.localizedDescription
            return false
        }
    }

    func unbindDevice(_ binding: DeviceBinding) async -> Bool {
        guard canManageDevices, deviceActionID == nil, let repository else { return false }
        beginDeviceOperation(id: "binding-\(binding.id)", message: "正在解除盒子绑定")
        defer { deviceActionID = nil }
        do {
            _ = try await repository.unbindDevice(bindingID: binding.id)
            guard var value = state.value else { return true }
            value.bindings.removeAll { $0.id == binding.id }
            value.cameras.removeAll { $0.deviceID == binding.deviceID }
            state.value = value
            await persist()
            deviceConfigurationRevision += 1
            reconcileDeviceConfiguration(cameraID: nil, expectedToExist: false)
            return true
        } catch {
            deviceProgress = nil
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

    private func replaceProductPreferences(_ preferences: ProductPreferences) {
        guard var value = state.value else { return }
        value.productPreferences = preferences
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

    private func beginDeviceOperation(id: String, message: String) {
        deviceReconciliationTask?.cancel()
        deviceReconciliationTask = nil
        deviceProgressDismissTask?.cancel()
        deviceProgressDismissTask = nil
        deviceActionID = id
        deviceProgress = .saving(message)
        inlineError = nil
    }

    private func reconcileDeviceConfiguration(cameraID: String?, expectedToExist: Bool) {
        guard let repository, let scope else {
            deviceProgress = nil
            return
        }
        deviceReconciliationTask?.cancel()
        deviceProgress = .syncing(cameraID: cameraID, message: expectedToExist ? "已保存，正在同步到盒子" : "云端已更新，正在确认盒子状态")
        deviceReconciliationTask = Task { [weak self, repository, scope] in
            let delays: [UInt64] = [0, 1, 2, 3, 5, 8]
            for delay in delays {
                if delay > 0 {
                    do {
                        try await Task.sleep(nanoseconds: delay * 1_000_000_000)
                    } catch {
                        return
                    }
                }
                guard !Task.isCancelled else { return }
                do {
                    let profile = try await repository.freshProfile(scope: scope)
                    guard let self, !Task.isCancelled else { return }
                    self.state = Loadable(value: profile, isRefreshing: false, staleReason: nil)
                    self.deviceConfigurationRevision += 1
                    let camera = cameraID.flatMap { id in profile.cameras.first(where: { $0.id == id }) }
                    if expectedToExist, let camera, camera.isReadyForLiveView {
                        self.finishDeviceReconciliation("摄像头已在线")
                        return
                    }
                    if !expectedToExist, cameraID == nil || camera == nil {
                        self.finishDeviceReconciliation("设备配置已更新")
                        return
                    }
                } catch is CancellationError {
                    return
                } catch {
                    continue
                }
            }
            guard let self, !Task.isCancelled else { return }
            self.deviceProgress = .syncing(cameraID: cameraID, message: "配置已保存，盒子仍在后台同步")
        }
    }

    private func finishDeviceReconciliation(_ message: String) {
        deviceProgressDismissTask?.cancel()
        deviceProgress = .ready(message)
        deviceProgressDismissTask = Task { [weak self] in
            do {
                try await Task.sleep(nanoseconds: 1_500_000_000)
            } catch {
                return
            }
            guard let self, self.deviceProgress == .ready(message) else { return }
            self.deviceProgress = nil
            self.deviceProgressDismissTask = nil
        }
    }

    private func persist() async {
        guard let repository, let scope, let value = state.value else { return }
        await repository.cacheProfile(value, scope: scope)
    }

    deinit {
        loadTask?.cancel()
        deviceReconciliationTask?.cancel()
        deviceProgressDismissTask?.cancel()
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}
