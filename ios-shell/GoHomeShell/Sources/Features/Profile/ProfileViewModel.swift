import Foundation

@MainActor
final class ProfileViewModel: ObservableObject {
    @Published private(set) var state: Loadable<ProfileData>
    @Published private(set) var savingRules = false
    @Published private(set) var savingPreferences = false
    @Published private(set) var deviceActionID: String?
    @Published private(set) var deviceConfigurationRevision = 0
    @Published private(set) var inlineError: String?
    @Published private(set) var familyMembers: [FamilyMember]
    @Published private(set) var familyActionID: String?
    @Published private(set) var familyInvitations: [FamilyInvitation] = []
    @Published private(set) var invitationActionID: String?

    let user: AppUser
    let family: AppFamily

    private let repository: AppRepository?
    private let scope: CacheScope?
    private var loadTask: Task<Void, Never>?
    private var hasStarted = false
    private let onFamilyChanged: () -> Void

    init(
        user: AppUser,
        family: AppFamily,
        repository: AppRepository?,
        scope: CacheScope?,
        seed: ProfileData? = nil,
        onFamilyChanged: @escaping () -> Void = {}
    ) {
        self.user = user
        self.family = family
        self.repository = repository
        self.scope = scope
        self.onFamilyChanged = onFamilyChanged
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
            deviceConfigurationRevision += 1
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
            deviceConfigurationRevision += 1
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
            deviceConfigurationRevision += 1
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
            deviceConfigurationRevision += 1
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
