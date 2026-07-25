import XCTest
@testable import GoHomeShell

final class ProfilePermissionTests: XCTestCase {
    func testFamilyRoleUsesOnlyCreatorAndMemberProductLabels() {
        XCTAssertEqual(FamilyRole.resolve(familyRole: "owner", canEdit: false), .creator)
        XCTAssertEqual(FamilyRole.resolve(familyRole: "member", canEdit: false), .member)
        XCTAssertEqual(FamilyRole.resolve(familyRole: nil, canEdit: true), .creator)
        XCTAssertFalse(FamilyRole.allProductLabels.contains("管理员"))
    }

    func testRulePatchMatchesWebRuleControls() throws {
        let rules = fixtureProfile(canEdit: true).rules
        let data = try JSONEncoder().encode(rules.editablePayload)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])

        XCTAssertEqual(object["fall_detection_enabled"] as? Bool, true)
        XCTAssertEqual(object["capture_interval_seconds"] as? Int, 5)
        XCTAssertEqual(object["no_motion_seconds"] as? Int, 900)
        XCTAssertEqual(object["no_person_seconds"] as? Int, 900)
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

    @MainActor
    func testMemberCannotInvokeDeviceMutations() async throws {
        let recorder = DeviceMutationRecorder()
        let binding = fixtureBinding()
        let camera = fixtureCamera()
        let repository = AppRepository(
            cache: try DiskCache(rootURL: temporaryDirectory()),
            bootstrapLoader: { throw APIError.invalidResponse },
            cameraCreator: { request in
                await recorder.record("create:\(request.deviceID)")
                return camera
            },
            cameraUpdater: { id, _ in
                await recorder.record("update:\(id)")
                return camera
            },
            cameraDeleter: { id in
                await recorder.record("delete:\(id)")
                return try cameraDeleteResponse(id: id)
            },
            deviceUnbinder: { id in
                await recorder.record("unbind:\(id)")
                return DeviceUnbindResponse(ok: true, binding: binding, removedCameraCount: 1, next: "device_claim")
            }
        )
        let model = makeModel(
            role: "member",
            repository: repository,
            seed: fixtureProfile(canEdit: false, bindings: [binding], cameras: [camera])
        )

        let created = await model.createCamera(
            binding: binding,
            name: "客厅主视",
            room: "客厅",
            streamURL: "rtsp://192.168.1.20:554/1/2",
            username: "admin",
            password: "secret"
        )
        let updated = await model.updateCamera(camera, name: "改名", room: "卧室", enabled: false)
        let deleted = await model.deleteCamera(camera)
        let unbound = await model.unbindDevice(binding)
        let actions = await recorder.actions
        XCTAssertFalse(created)
        XCTAssertFalse(updated)
        XCTAssertFalse(deleted)
        XCTAssertFalse(unbound)
        XCTAssertEqual(actions, [])
    }

    @MainActor
    func testCreatorDeviceMutationsUpdateVisibleStateAndProfileCache() async throws {
        let cache = try DiskCache(rootURL: temporaryDirectory())
        let scope = CacheScope(userID: "user-1", familyID: "family-1")
        let binding = fixtureBinding()
        let created = fixtureCamera(id: "camera-new", name: "客厅主视", status: "pending_edge_sync")
        let updated = fixtureCamera(id: created.id, name: "客厅全景", status: "online", enabled: false)
        let repository = AppRepository(
            cache: cache,
            bootstrapLoader: { throw APIError.invalidResponse },
            cameraCreator: { _ in created },
            cameraUpdater: { _, _ in updated },
            cameraDeleter: { id in try cameraDeleteResponse(id: id) },
            deviceUnbinder: { _ in
                DeviceUnbindResponse(ok: true, binding: binding, removedCameraCount: 1, next: "device_claim")
            }
        )
        let model = ProfileViewModel(
            user: AppUser(id: scope.userID, phone: "13800138000", displayName: "测试用户"),
            family: AppFamily(id: scope.familyID, name: "测试家庭", role: "owner"),
            repository: repository,
            scope: scope,
            seed: fixtureProfile(canEdit: true, bindings: [binding])
        )

        let didCreate = await model.createCamera(
            binding: binding,
            name: created.name,
            room: created.room,
            streamURL: "rtsp://192.168.1.20:554/1/2",
            username: "admin",
            password: "secret"
        )
        XCTAssertTrue(didCreate)
        XCTAssertEqual(model.state.value?.cameras, [created])

        let didUpdate = await model.updateCamera(created, name: updated.name, room: updated.room, enabled: updated.enabled)
        XCTAssertTrue(didUpdate)
        XCTAssertEqual(model.state.value?.cameras, [updated])

        let didDelete = await model.deleteCamera(updated)
        XCTAssertTrue(didDelete)
        XCTAssertEqual(model.state.value?.cameras, [])

        let didRecreate = await model.createCamera(
            binding: binding,
            name: created.name,
            room: created.room,
            streamURL: "rtsp://192.168.1.20:554/1/2",
            username: "admin",
            password: "secret"
        )
        let didUnbind = await model.unbindDevice(binding)
        XCTAssertTrue(didRecreate)
        XCTAssertTrue(didUnbind)
        XCTAssertEqual(model.state.value?.bindings, [])
        XCTAssertEqual(model.state.value?.cameras, [])

        let cached = try await cache.read(ProfileData.self, key: "profile", scope: scope)
        XCTAssertEqual(cached?.bindings, [])
        XCTAssertEqual(cached?.cameras, [])
    }

    private func temporaryDirectory() -> URL {
        FileManager.default.temporaryDirectory
            .appendingPathComponent("ProfilePermissionTests-\(UUID().uuidString)", isDirectory: true)
    }

    @MainActor
    private func makeModel(role: String, repository: AppRepository, seed: ProfileData) -> ProfileViewModel {
        ProfileViewModel(
            user: AppUser(id: "user-1", phone: "13800138000", displayName: "测试用户"),
            family: AppFamily(id: "family-1", name: "测试家庭", role: role),
            repository: repository,
            scope: CacheScope(userID: "user-1", familyID: "family-1"),
            seed: seed
        )
    }
}

private actor RuleUpdateRecorder {
    private(set) var count = 0

    func record(familyID: String, patch: RulePatch) {
        count += 1
    }
}

private actor DeviceMutationRecorder {
    private(set) var actions: [String] = []
    func record(_ action: String) { actions.append(action) }
}

private func fixtureProfile(
    canEdit: Bool,
    bindings: [DeviceBinding] = [],
    cameras: [CameraConfig] = []
) -> ProfileData {
    ProfileData(
        elder: nil,
        bindings: bindings,
        cameras: cameras,
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

private func fixtureBinding() -> DeviceBinding {
    DeviceBinding(
        id: "binding-1",
        familyID: "family-1",
        deviceID: "edge-1",
        deviceName: "家庭盒子",
        status: "online"
    )
}

private func fixtureCamera(
    id: String = "camera-1",
    name: String = "客厅主视",
    status: String = "online",
    enabled: Bool = true
) -> CameraConfig {
    CameraConfig(
        id: id,
        familyID: "family-1",
        deviceID: "edge-1",
        name: name,
        room: "客厅",
        status: status,
        syncStatus: status == "online" ? "synced" : "pending_edge_sync",
        connectionOwner: "edge_agent",
        hasStreamConfig: true,
        passwordSet: true,
        enabled: enabled
    )
}

private func cameraDeleteResponse(id: String) throws -> CameraDeleteResponse {
    try JSONDecoder().decode(
        CameraDeleteResponse.self,
        from: Data(#"{"ok":true,"deleted":"\#(id)"}"#.utf8)
    )
}

private extension FamilyRole {
    static var allProductLabels: [String] { [FamilyRole.creator.rawValue, FamilyRole.member.rawValue] }
}
