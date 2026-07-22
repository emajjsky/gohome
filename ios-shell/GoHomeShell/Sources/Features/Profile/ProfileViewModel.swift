import Foundation

@MainActor
final class ProfileViewModel: ObservableObject {
    @Published private(set) var state: Loadable<ProfileData>
    @Published private(set) var savingRules = false
    @Published private(set) var savingPreferences = false
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
                persist()
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
                persist()
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

    private func persist() {
        guard let repository, let scope, let value = state.value else { return }
        Task { await repository.cacheProfile(value, scope: scope) }
    }

    deinit {
        loadTask?.cancel()
    }
}
