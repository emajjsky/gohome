import XCTest
@testable import GoHomeShell

final class ProfilePermissionTests: XCTestCase {
    func testFamilyRoleUsesOnlyCreatorAndMemberProductLabels() {
        XCTAssertEqual(FamilyRole.resolve(familyRole: "owner", canEdit: false), .creator)
        XCTAssertEqual(FamilyRole.resolve(familyRole: "member", canEdit: false), .member)
        XCTAssertEqual(FamilyRole.resolve(familyRole: nil, canEdit: true), .creator)
        XCTAssertFalse(FamilyRole.allProductLabels.contains("管理员"))
    }

    func testRulePatchContainsOnlyProductSwitches() throws {
        let rules = fixtureProfile(canEdit: true).rules
        let data = try JSONEncoder().encode(rules.editablePayload)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])

        XCTAssertEqual(object["fall_detection_enabled"] as? Bool, true)
        XCTAssertNil(object["fall_score_threshold"])
        XCTAssertNil(object["yolo_confidence"])
        XCTAssertNil(object["capture_interval_seconds"])
    }

    @MainActor
    func testMemberCannotSubmitRuleMutation() async throws {
        let recorder = RuleUpdateRecorder()
        let cache = try DiskCache(rootURL: temporaryDirectory())
        let repository = AppRepository(
            cache: cache,
            bootstrapLoader: { throw APIError.invalidResponse },
            rulesUpdater: { familyID, patch in
                await recorder.record(familyID: familyID, patch: patch)
                return fixtureProfile(canEdit: false).rules
            }
        )
        let model = ProfileViewModel(
            user: AppUser(id: "user-1", phone: "13800138000", displayName: "测试用户"),
            family: AppFamily(id: "family-1", name: "测试家庭", role: "member"),
            repository: repository,
            scope: CacheScope(userID: "user-1", familyID: "family-1"),
            seed: fixtureProfile(canEdit: false)
        )

        var changed = try XCTUnwrap(model.state.value?.rules)
        changed.fireDetectionEnabled = false
        model.saveRules(changed)
        try await Task.sleep(nanoseconds: 50_000_000)
        let updateCount = await recorder.count

        XCTAssertFalse(model.canEditRules)
        XCTAssertEqual(updateCount, 0)
        XCTAssertEqual(model.state.value?.rules.fireDetectionEnabled, true)
    }

    private func temporaryDirectory() -> URL {
        FileManager.default.temporaryDirectory
            .appendingPathComponent("ProfilePermissionTests-\(UUID().uuidString)", isDirectory: true)
    }
}

private actor RuleUpdateRecorder {
    private(set) var count = 0

    func record(familyID: String, patch: RulePatch) {
        count += 1
    }
}

private func fixtureProfile(canEdit: Bool) -> ProfileData {
    ProfileData(
        elder: nil,
        bindings: [],
        cameras: [],
        rules: FamilyRules(
            canEdit: canEdit,
            offlineEnabled: true,
            blackScreenEnabled: true,
            noMotionEnabled: true,
            personDetectionEnabled: true,
            fallDetectionEnabled: true,
            activityDetectionEnabled: true,
            fireDetectionEnabled: true,
            notificationEnabled: true
        ),
        carePreferences: CarePreferences(familyID: "family-1", interests: ["天气"]),
        productPreferences: ProductPreferences(categories: [], needs: [])
    )
}

private extension FamilyRole {
    static var allProductLabels: [String] { [FamilyRole.creator.rawValue, FamilyRole.member.rawValue] }
}
