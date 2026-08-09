import XCTest
@testable import GoHomeShell

final class ProfilePermissionTests: XCTestCase {
    func testCameraBindingResolutionNeverFallsBackToAnotherBox() {
        let first = DeviceBinding(
            id: "binding-1", familyID: "family-1", deviceID: "edge-1", deviceName: "客厅盒子", status: "online"
        )
        let second = DeviceBinding(
            id: "binding-2", familyID: "family-1", deviceID: "edge-2", deviceName: "卧室盒子", status: "online"
        )
        let camera = fixtureCamera(deviceID: "edge-2")
        let orphan = fixtureCamera(id: "camera-orphan", deviceID: "edge-unknown")

        XCTAssertEqual(CameraBindingResolver.exactBinding(for: camera, bindings: [first, second]), second)
        XCTAssertNil(CameraBindingResolver.exactBinding(for: orphan, bindings: [first, second]))
    }

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
        let updated = await model.updateCamera(
            camera,
            name: "改名",
            room: "卧室",
            streamURL: "rtsp://192.168.1.7:554/1/2",
            username: "",
            password: "",
            enabled: false
        )
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
        XCTAssertEqual(model.deviceConfigurationRevision, 1)

        let didUpdate = await model.updateCamera(
            created,
            name: updated.name,
            room: updated.room,
            streamURL: "rtsp://192.168.1.7:554/1/2",
            username: "",
            password: "",
            enabled: updated.enabled
        )
        XCTAssertTrue(didUpdate)
        XCTAssertEqual(model.state.value?.cameras, [updated])
        XCTAssertEqual(model.deviceConfigurationRevision, 2)

        let didDelete = await model.deleteCamera(updated)
        XCTAssertTrue(didDelete)
        XCTAssertEqual(model.state.value?.cameras, [])
        XCTAssertEqual(model.deviceConfigurationRevision, 3)

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
        XCTAssertEqual(model.deviceConfigurationRevision, 5)

        let cached = try await cache.read(ProfileData.self, key: "profile", scope: scope)
        XCTAssertEqual(cached?.bindings, [])
        XCTAssertEqual(cached?.cameras, [])
    }

    @MainActor
    func testCancelledDeviceMutationsDoNotPublishReturnedState() async throws {
        let binding = fixtureBinding()
        let existing = fixtureCamera()
        let created = fixtureCamera(id: "camera-new", name: "新摄像头")
        let updated = fixtureCamera(id: existing.id, name: "不应更新")
        let repository = AppRepository(
            cache: try DiskCache(rootURL: temporaryDirectory()),
            bootstrapLoader: { throw APIError.invalidResponse },
            cameraCreator: { _ in
                try? await Task.sleep(nanoseconds: 100_000_000)
                return created
            },
            cameraUpdater: { _, _ in
                try? await Task.sleep(nanoseconds: 100_000_000)
                return updated
            },
            cameraDeleter: { id in
                try? await Task.sleep(nanoseconds: 100_000_000)
                return try cameraDeleteResponse(id: id)
            },
            deviceUnbinder: { _ in
                try? await Task.sleep(nanoseconds: 100_000_000)
                return DeviceUnbindResponse(ok: true, binding: binding, removedCameraCount: 1, next: "device_claim")
            }
        )
        let model = makeModel(
            role: "owner",
            repository: repository,
            seed: fixtureProfile(canEdit: true, bindings: [binding], cameras: [existing])
        )

        let createTask = Task { @MainActor in
            await model.createCamera(
                binding: binding,
                name: created.name,
                room: created.room,
                streamURL: "rtsp://192.168.1.20:554/1/2",
                username: "admin",
                password: "secret"
            )
        }
        try await Task.sleep(nanoseconds: 20_000_000)
        createTask.cancel()
        let createdResult = await createTask.value
        XCTAssertFalse(createdResult)

        let updateTask = Task { @MainActor in
            await model.updateCamera(
                existing,
                name: updated.name,
                room: updated.room,
                streamURL: "rtsp://192.168.1.7:554/1/2",
                username: "",
                password: "",
                enabled: true
            )
        }
        try await Task.sleep(nanoseconds: 20_000_000)
        updateTask.cancel()
        let updatedResult = await updateTask.value
        XCTAssertFalse(updatedResult)

        let deleteTask = Task { @MainActor in await model.deleteCamera(existing) }
        try await Task.sleep(nanoseconds: 20_000_000)
        deleteTask.cancel()
        let deletedResult = await deleteTask.value
        XCTAssertFalse(deletedResult)

        let unbindTask = Task { @MainActor in await model.unbindDevice(binding) }
        try await Task.sleep(nanoseconds: 20_000_000)
        unbindTask.cancel()
        let unboundResult = await unbindTask.value
        XCTAssertFalse(unboundResult)

        XCTAssertEqual(model.state.value?.cameras, [existing])
        XCTAssertEqual(model.state.value?.bindings, [binding])
        XCTAssertNil(model.inlineError)
        XCTAssertNil(model.deviceActionID)
        XCTAssertNil(model.deviceProgress)
    }

    @MainActor
    func testNewDeviceOperationKeepsItsProgressAfterPreviousSuccessMessageExpires() async throws {
        let binding = fixtureBinding()
        let created = fixtureCamera(id: "camera-new", status: "pending_edge_sync")
        let ready = fixtureCamera(id: created.id, status: "online")
        let repository = AppRepository(
            cache: try DiskCache(rootURL: temporaryDirectory()),
            bootstrapLoader: { throw APIError.invalidResponse },
            profileLoader: { _ in
                fixtureProfile(canEdit: true, bindings: [binding], cameras: [ready])
            },
            cameraCreator: { _ in created },
            cameraUpdater: { _, _ in
                try await Task.sleep(nanoseconds: 2_000_000_000)
                return ready
            }
        )
        let model = ProfileViewModel(
            user: AppUser(id: "user-1", phone: "13800138000", displayName: "测试用户"),
            family: AppFamily(id: "family-1", name: "测试家庭", role: "owner"),
            repository: repository,
            scope: CacheScope(userID: "user-1", familyID: "family-1"),
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
        for _ in 0..<100 where model.deviceProgress != .ready("摄像头已在线") {
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        XCTAssertEqual(model.deviceProgress, .ready("摄像头已在线"))

        let updateTask = Task { @MainActor in
            await model.updateCamera(
                ready,
                name: "更新后的摄像头",
                room: ready.room,
                streamURL: "rtsp://192.168.1.7:554/1/2",
                username: "",
                password: "",
                enabled: true
            )
        }
        for _ in 0..<100 where model.deviceProgress != .saving("正在保存摄像头设置") {
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        XCTAssertEqual(model.deviceProgress, .saving("正在保存摄像头设置"))
        try await Task.sleep(nanoseconds: 1_600_000_000)
        XCTAssertEqual(model.deviceProgress, .saving("正在保存摄像头设置"))
        _ = await updateTask.value
    }

    @MainActor
    func testNewDeviceOperationCancelsPreviousReconciliation() async throws {
        let binding = fixtureBinding()
        let pending = fixtureCamera(id: "camera-new", status: "pending_edge_sync")
        let ready = fixtureCamera(id: pending.id, status: "online")
        let profiles = ProfileLoadSequence(profiles: [
            fixtureProfile(canEdit: true, bindings: [binding], cameras: [pending]),
            fixtureProfile(canEdit: true, bindings: [binding], cameras: [ready]),
        ])
        let repository = AppRepository(
            cache: try DiskCache(rootURL: temporaryDirectory()),
            bootstrapLoader: { throw APIError.invalidResponse },
            profileLoader: { _ in await profiles.next() },
            cameraCreator: { _ in pending },
            cameraUpdater: { _, _ in
                try await Task.sleep(nanoseconds: 2_000_000_000)
                return ready
            }
        )
        let model = ProfileViewModel(
            user: AppUser(id: "user-1", phone: "13800138000", displayName: "测试用户"),
            family: AppFamily(id: "family-1", name: "测试家庭", role: "owner"),
            repository: repository,
            scope: CacheScope(userID: "user-1", familyID: "family-1"),
            seed: fixtureProfile(canEdit: true, bindings: [binding])
        )

        let didCreate = await model.createCamera(
            binding: binding,
            name: pending.name,
            room: pending.room,
            streamURL: "rtsp://192.168.1.20:554/1/2",
            username: "admin",
            password: "secret"
        )
        XCTAssertTrue(didCreate)
        for _ in 0..<100 {
            if await profiles.loadCount > 0 { break }
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        let initialLoadCount = await profiles.loadCount
        XCTAssertEqual(initialLoadCount, 1)

        let updateTask = Task { @MainActor in
            await model.updateCamera(
                pending,
                name: "更新后的摄像头",
                room: pending.room,
                streamURL: "rtsp://192.168.1.7:554/1/2",
                username: "",
                password: "",
                enabled: true
            )
        }
        for _ in 0..<100 where model.deviceProgress != .saving("正在保存摄像头设置") {
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        try await Task.sleep(nanoseconds: 1_200_000_000)
        XCTAssertEqual(model.deviceProgress, .saving("正在保存摄像头设置"))
        let loadCountAfterCancellation = await profiles.loadCount
        XCTAssertEqual(loadCountAfterCancellation, 1)
        _ = await updateTask.value
    }

    @MainActor
    func testFamilyManagementHonorsRolesAndRefreshesAfterOwnershipTransfer() async throws {
        let recorder = FamilyMutationRecorder()
        let member = FamilyMember(
            id: "member-2", userID: "user-2", displayName: "家庭成员", accountHint: "139****0000",
            role: "member", isCurrentUser: false, joinedAt: nil
        )
        var refreshCount = 0
        let repository = AppRepository(
            cache: try DiskCache(rootURL: temporaryDirectory()),
            bootstrapLoader: { throw APIError.invalidResponse },
            familyMembersLoader: { _ in FamilyMembersResponse(familyID: "family-1", members: [member], revision: "r1") },
            familyMemberRemover: { _, memberID in
                await recorder.record("remove:\(memberID)")
                return FamilyMemberRemovalResponse(removed: true)
            },
            familyOwnershipTransferer: { _, memberID in
                await recorder.record("transfer:\(memberID)")
                return FamilyOwnershipTransferResponse(transferred: true)
            }
        )
        let creator = ProfileViewModel(
            user: AppUser(id: "user-1", phone: "13800138000", displayName: "创建者"),
            family: AppFamily(id: "family-1", name: "测试家庭", role: "owner"),
            repository: repository,
            scope: CacheScope(userID: "user-1", familyID: "family-1"),
            seed: fixtureProfile(canEdit: true),
            onFamilyChanged: { refreshCount += 1 }
        )

        let transferred = await creator.transferOwnership(to: member)
        let actionsAfterTransfer = await recorder.snapshot()
        XCTAssertTrue(transferred)
        XCTAssertEqual(actionsAfterTransfer, ["transfer:member-2"])
        XCTAssertEqual(refreshCount, 1)

        let ordinaryMember = makeModel(role: "member", repository: repository, seed: fixtureProfile(canEdit: false))
        let removed = await ordinaryMember.removeFamilyMember(member)
        let actionsAfterDeniedRemoval = await recorder.snapshot()
        XCTAssertFalse(removed)
        XCTAssertEqual(actionsAfterDeniedRemoval, ["transfer:member-2"])
    }

    @MainActor
    func testOnlyCreatorCanCreateAndRevokeOneTimeFamilyInvitations() async throws {
        let recorder = FamilyMutationRecorder()
        let active = FamilyInvitation(
            id: "invitation-1", familyID: "family-1", status: "active", codeHint: "7XYZ",
            code: "GH-2345-6789-7XYZ", expiresAt: "2026-07-27T10:10:00.000Z",
            createdAt: "2026-07-27T10:00:00.000Z", usedAt: nil, revokedAt: nil
        )
        let revoked = FamilyInvitation(
            id: active.id, familyID: active.familyID, status: "revoked", codeHint: active.codeHint,
            code: nil, expiresAt: active.expiresAt, createdAt: active.createdAt,
            usedAt: nil, revokedAt: "2026-07-27T10:01:00.000Z"
        )
        let repository = AppRepository(
            cache: try DiskCache(rootURL: temporaryDirectory()),
            bootstrapLoader: { throw APIError.invalidResponse },
            familyInvitationCreator: { familyID in
                await recorder.record("invite:\(familyID)")
                return active
            },
            familyInvitationRevoker: { _, invitationID in
                await recorder.record("revoke:\(invitationID)")
                return revoked
            }
        )
        let creator = makeModel(role: "owner", repository: repository, seed: fixtureProfile(canEdit: true))

        let created = await creator.createFamilyInvitation()
        XCTAssertTrue(created)
        XCTAssertEqual(creator.activeFamilyInvitation?.code, active.code)
        let didRevoke = await creator.revokeFamilyInvitation(active)
        XCTAssertTrue(didRevoke)
        XCTAssertNil(creator.activeFamilyInvitation)

        let member = makeModel(role: "member", repository: repository, seed: fixtureProfile(canEdit: false))
        let memberCreated = await member.createFamilyInvitation()
        let actions = await recorder.snapshot()
        XCTAssertFalse(memberCreated)
        XCTAssertEqual(actions, ["invite:family-1", "revoke:invitation-1"])
    }

    @MainActor
    func testCancelledFamilyRefreshCannotOverwriteMembersOrInvitations() async throws {
        let lateMember = FamilyMember(
            id: "member-late", userID: "user-late", displayName: "迟到成员", accountHint: "139****0000",
            role: "member", isCurrentUser: false, joinedAt: nil
        )
        let lateInvitation = FamilyInvitation(
            id: "invitation-late", familyID: "family-1", status: "active", codeHint: "LATE",
            code: "GH-LATE", expiresAt: nil, createdAt: nil, usedAt: nil, revokedAt: nil
        )
        let repository = AppRepository(
            cache: try DiskCache(rootURL: temporaryDirectory()),
            bootstrapLoader: { throw APIError.invalidResponse },
            familyMembersLoader: { _ in
                try? await Task.sleep(nanoseconds: 100_000_000)
                return FamilyMembersResponse(familyID: "family-1", members: [lateMember], revision: "late")
            },
            familyInvitationsLoader: { _ in
                try? await Task.sleep(nanoseconds: 100_000_000)
                return FamilyInvitationsResponse(familyID: "family-1", invitations: [lateInvitation], revision: "late")
            }
        )
        let model = makeModel(role: "owner", repository: repository, seed: fixtureProfile(canEdit: true))

        model.refreshFamilyMembers()
        try await Task.sleep(nanoseconds: 20_000_000)
        model.cancelInFlightFamilyRefresh()
        try await Task.sleep(nanoseconds: 140_000_000)

        XCTAssertEqual(model.familyMembers.count, 1)
        XCTAssertNil(model.activeFamilyInvitation)
        XCTAssertNil(model.inlineError)
        XCTAssertNil(model.familyActionID)
    }

    @MainActor
    func testCancelledFamilyMemberRemovalKeepsMemberWithoutError() async throws {
        let member = FamilyMember(
            id: "member-2", userID: "user-2", displayName: "家庭成员", accountHint: "139****0000",
            role: "member", isCurrentUser: false, joinedAt: nil
        )
        let repository = AppRepository(
            cache: try DiskCache(rootURL: temporaryDirectory()),
            bootstrapLoader: { throw APIError.invalidResponse },
            familyMembersLoader: { _ in
                FamilyMembersResponse(familyID: "family-1", members: [member], revision: "current")
            },
            familyMemberRemover: { _, _ in
                try? await Task.sleep(nanoseconds: 100_000_000)
                return FamilyMemberRemovalResponse(removed: true)
            },
            familyInvitationsLoader: { _ in
                FamilyInvitationsResponse(familyID: "family-1", invitations: [], revision: "current")
            }
        )
        let model = makeModel(role: "owner", repository: repository, seed: fixtureProfile(canEdit: true))
        model.refreshFamilyMembers()
        for _ in 0..<50 where !model.familyMembers.contains(member) {
            try await Task.sleep(nanoseconds: 2_000_000)
        }
        XCTAssertTrue(model.familyMembers.contains(member))

        let actionTask = Task { @MainActor in await model.removeFamilyMember(member) }
        try await Task.sleep(nanoseconds: 20_000_000)
        actionTask.cancel()
        let removed = await actionTask.value

        XCTAssertFalse(removed)
        XCTAssertTrue(model.familyMembers.contains(member))
        XCTAssertNil(model.inlineError)
        XCTAssertNil(model.familyActionID)
    }

    @MainActor
    func testCancelledFamilyInvitationCreationKeepsExistingStateWithoutError() async throws {
        let late = FamilyInvitation(
            id: "invitation-late", familyID: "family-1", status: "active", codeHint: "LATE",
            code: "GH-LATE", expiresAt: nil, createdAt: nil, usedAt: nil, revokedAt: nil
        )
        let repository = AppRepository(
            cache: try DiskCache(rootURL: temporaryDirectory()),
            bootstrapLoader: { throw APIError.invalidResponse },
            familyInvitationCreator: { _ in
                try? await Task.sleep(nanoseconds: 100_000_000)
                return late
            }
        )
        let model = makeModel(role: "owner", repository: repository, seed: fixtureProfile(canEdit: true))

        let actionTask = Task { @MainActor in await model.createFamilyInvitation() }
        try await Task.sleep(nanoseconds: 20_000_000)
        actionTask.cancel()
        let created = await actionTask.value

        XCTAssertFalse(created)
        XCTAssertEqual(model.familyInvitations, [])
        XCTAssertNil(model.inlineError)
        XCTAssertNil(model.invitationActionID)
    }

    @MainActor
    func testProductPreferencesPersistThroughRepositoryAndCache() async throws {
        let cache = try DiskCache(rootURL: temporaryDirectory())
        let scope = CacheScope(userID: "user-1", familyID: "family-1")
        let expected = ProductPreferences(categories: ["照明与视野"], needs: ["夜间照明"])
        let repository = AppRepository(
            cache: cache,
            bootstrapLoader: { throw APIError.invalidResponse },
            productPreferencesUpdater: { familyID, preferences in
                XCTAssertEqual(familyID, scope.familyID)
                return ProductPreferencesEnvelope(preferences: preferences)
            }
        )
        let model = makeModel(role: "owner", repository: repository, seed: fixtureProfile(canEdit: true))

        model.saveProductPreferences(expected)
        for _ in 0..<20 where model.savingProductPreferences {
            try await Task.sleep(nanoseconds: 10_000_000)
        }

        XCTAssertEqual(model.state.value?.productPreferences, expected)
        let cached = try await cache.read(ProfileData.self, key: "profile", scope: scope)
        XCTAssertEqual(cached?.productPreferences, expected)
    }

    @MainActor
    func testCancelledRuleSaveRollsBackWithoutError() async throws {
        let original = fixtureProfile(canEdit: true)
        let repository = AppRepository(
            cache: try DiskCache(rootURL: temporaryDirectory()),
            bootstrapLoader: { throw APIError.invalidResponse },
            rulesUpdater: { _, _ in
                try await Task.sleep(nanoseconds: 5_000_000_000)
                throw APIError.invalidResponse
            }
        )
        let model = makeModel(role: "owner", repository: repository, seed: original)
        var changed = original.rules
        changed.fireDetectionEnabled = false

        model.saveRules(changed)
        try await Task.sleep(nanoseconds: 20_000_000)
        XCTAssertTrue(model.savingRules)
        model.cancelInFlightPreferenceSaves()
        try await Task.sleep(nanoseconds: 20_000_000)

        XCTAssertEqual(model.state.value?.rules, original.rules)
        XCTAssertFalse(model.savingRules)
        XCTAssertNil(model.inlineError)
    }

    @MainActor
    func testCancelledContentPreferenceSaveRollsBackWithoutError() async throws {
        let original = fixtureProfile(canEdit: true)
        let repository = AppRepository(
            cache: try DiskCache(rootURL: temporaryDirectory()),
            bootstrapLoader: { throw APIError.invalidResponse },
            carePreferencesUpdater: { _, _ in
                try await Task.sleep(nanoseconds: 5_000_000_000)
                throw APIError.invalidResponse
            }
        )
        let model = makeModel(role: "owner", repository: repository, seed: original)
        var changed = original.carePreferences
        changed.contentSourcesEnabled.toggle()

        model.savePreferences(changed)
        try await Task.sleep(nanoseconds: 20_000_000)
        XCTAssertTrue(model.savingPreferences)
        model.cancelInFlightPreferenceSaves()
        try await Task.sleep(nanoseconds: 20_000_000)

        XCTAssertEqual(model.state.value?.carePreferences, original.carePreferences)
        XCTAssertFalse(model.savingPreferences)
        XCTAssertNil(model.inlineError)
    }

    @MainActor
    func testCancelledProductPreferenceSaveRollsBackWithoutError() async throws {
        let original = fixtureProfile(canEdit: true)
        let repository = AppRepository(
            cache: try DiskCache(rootURL: temporaryDirectory()),
            bootstrapLoader: { throw APIError.invalidResponse },
            productPreferencesUpdater: { _, _ in
                try await Task.sleep(nanoseconds: 5_000_000_000)
                throw APIError.invalidResponse
            }
        )
        let model = makeModel(role: "owner", repository: repository, seed: original)
        let changed = ProductPreferences(categories: ["照明与视野"], needs: ["夜间照明"])

        model.saveProductPreferences(changed)
        try await Task.sleep(nanoseconds: 20_000_000)
        XCTAssertTrue(model.savingProductPreferences)
        model.cancelInFlightPreferenceSaves()
        try await Task.sleep(nanoseconds: 20_000_000)

        XCTAssertEqual(model.state.value?.productPreferences, original.productPreferences)
        XCTAssertFalse(model.savingProductPreferences)
        XCTAssertNil(model.inlineError)
    }

    @MainActor
    func testOnlyCreatorCanSaveCaredForProfile() async throws {
        let updated = try elderProfileFixture()
        let recorder = FamilyMutationRecorder()
        let repository = AppRepository(
            cache: try DiskCache(rootURL: temporaryDirectory()),
            bootstrapLoader: { throw APIError.invalidResponse },
            elderProfileUpdater: { familyID, elderID, payload in
                await recorder.record("elder:\(familyID):\(elderID):\(payload.displayName)")
                return updated
            }
        )
        let payload = ProfilePayload(
            displayName: "林姨",
            relationship: "母亲",
            city: "杭州",
            district: "西湖区",
            phone: "13800138000",
            mobilePhone: "13800138000",
            homePhone: ""
        )
        let creator = makeModel(role: "owner", repository: repository, seed: fixtureProfile(canEdit: true))
        let member = makeModel(role: "member", repository: repository, seed: fixtureProfile(canEdit: false))

        let creatorSaved = await creator.saveElderProfile(payload)
        XCTAssertEqual(creator.state.value?.elder, updated)
        let memberSaved = await member.saveElderProfile(payload)
        let actions = await recorder.snapshot()
        XCTAssertTrue(creatorSaved)
        XCTAssertFalse(memberSaved)
        XCTAssertEqual(actions, ["elder:family-1:elder_primary:林姨"])
    }

    @MainActor
    func testCancelledElderProfileSaveCannotPublishReturnedServerState() async throws {
        let updated = try elderProfileFixture()
        let repository = AppRepository(
            cache: try DiskCache(rootURL: temporaryDirectory()),
            bootstrapLoader: { throw APIError.invalidResponse },
            elderProfileUpdater: { _, _, _ in
                try? await Task.sleep(nanoseconds: 100_000_000)
                return updated
            }
        )
        let model = makeModel(role: "owner", repository: repository, seed: fixtureProfile(canEdit: true))
        let payload = ProfilePayload(
            displayName: "不应保存",
            relationship: "母亲",
            city: "杭州",
            district: "西湖区",
            phone: "13800138000",
            mobilePhone: "13800138000",
            homePhone: ""
        )
        let saveTask = Task { @MainActor in await model.saveElderProfile(payload) }

        try await Task.sleep(nanoseconds: 20_000_000)
        saveTask.cancel()
        let saved = await saveTask.value

        XCTAssertFalse(saved)
        XCTAssertNil(model.state.value?.elder)
        XCTAssertFalse(model.savingElderProfile)
        XCTAssertNil(model.inlineError)
    }

    @MainActor
    func testAccountProfileUploadsAvatarAndPublishesSavedServerState() async throws {
        let scope = CacheScope(userID: "user-1", familyID: "family-1")
        let updated = try accountProfileFixture(
            displayName: "林舟",
            city: "上海市",
            district: "徐汇区",
            avatarAssetID: "asset-avatar"
        )
        let recorder = AccountProfileMutationRecorder()
        var publishedProfiles: [AccountProfile] = []
        let repository = AppRepository(
            cache: try DiskCache(rootURL: temporaryDirectory()),
            bootstrapLoader: { throw APIError.invalidResponse },
            memoryMediaBatchUploader: { familyID, media in
                await recorder.recordUpload(familyID: familyID, media: media)
                return MemoryMediaBatchUploadResponse(assets: [
                    MemoryUploadedAsset(
                        id: "asset-avatar",
                        contentType: "image/jpeg",
                        imageURL: "/api/v1/video/assets/asset-avatar",
                        mediaURL: nil,
                        mediaType: "image",
                        sizeBytes: media[0].data.count
                    )
                ])
            },
            accountProfileUpdater: { patch in
                await recorder.recordPatch(patch)
                return AccountProfileEnvelope(profile: updated)
            }
        )
        let model = ProfileViewModel(
            user: AppUser(id: scope.userID, phone: "13800138000", displayName: "测试用户"),
            family: AppFamily(id: scope.familyID, name: "测试家庭", role: "owner"),
            repository: repository,
            scope: scope,
            seed: fixtureProfile(canEdit: true),
            onAccountProfileChanged: { publishedProfiles.append($0) }
        )

        let saved = await model.saveAccountProfile(
            displayName: "  林舟  ",
            city: "上海市",
            district: "徐汇区",
            avatarJPEG: Data([1, 2, 3])
        )
        let snapshot = await recorder.snapshot()

        XCTAssertTrue(saved)
        XCTAssertEqual(model.accountProfile, updated)
        XCTAssertEqual(publishedProfiles, [updated])
        XCTAssertEqual(snapshot.uploadFamilyID, scope.familyID)
        XCTAssertEqual(snapshot.uploadCount, 1)
        XCTAssertEqual(snapshot.patch?.displayName, "林舟")
        XCTAssertEqual(snapshot.patch?.avatarAssetID, "asset-avatar")
        XCTAssertNil(model.inlineError)
    }

    @MainActor
    func testAccountProfileSaveFailureRestoresCurrentProfile() async throws {
        let scope = CacheScope(userID: "user-1", familyID: "family-1")
        let current = try accountProfileFixture(
            displayName: "当前昵称",
            city: "杭州市",
            district: "西湖区",
            avatarAssetID: "asset-current"
        )
        let repository = AppRepository(
            cache: try DiskCache(rootURL: temporaryDirectory()),
            bootstrapLoader: { throw APIError.invalidResponse },
            accountProfileLoader: { AccountProfileEnvelope(profile: current) },
            accountProfileUpdater: { _ in throw APIError.invalidResponse }
        )
        let model = ProfileViewModel(
            user: AppUser(id: scope.userID, phone: "13800138000", displayName: "测试用户"),
            family: AppFamily(id: scope.familyID, name: "测试家庭", role: "owner"),
            repository: repository,
            scope: scope,
            seed: fixtureProfile(canEdit: true)
        )
        model.refreshAccountProfile()
        for _ in 0..<20 where model.accountProfile != current {
            try await Task.sleep(nanoseconds: 10_000_000)
        }

        let saved = await model.saveAccountProfile(
            displayName: "失败的新昵称",
            city: "上海市",
            district: "徐汇区",
            avatarJPEG: nil
        )

        XCTAssertFalse(saved)
        XCTAssertEqual(model.accountProfile, current)
        XCTAssertEqual(model.inlineError, "账户资料未能保存，请重试")
        XCTAssertFalse(model.savingAccountProfile)
    }

    @MainActor
    func testCancelledAvatarUploadCannotUpdateProfileOrShowFailure() async throws {
        let scope = CacheScope(userID: "user-1", familyID: "family-1")
        let recorder = CancelledAccountProfileRecorder()
        let repository = AppRepository(
            cache: try DiskCache(rootURL: temporaryDirectory()),
            bootstrapLoader: { throw APIError.invalidResponse },
            memoryMediaBatchUploader: { _, media in
                await recorder.recordUploadStarted()
                try? await Task.sleep(nanoseconds: 80_000_000)
                return MemoryMediaBatchUploadResponse(assets: [
                    MemoryUploadedAsset(
                        id: "asset-late",
                        contentType: media[0].contentType,
                        imageURL: "/assets/late",
                        mediaURL: nil,
                        mediaType: "image",
                        sizeBytes: media[0].data.count
                    )
                ])
            },
            accountProfileUpdater: { patch in
                await recorder.recordPatch(patch)
                return AccountProfileEnvelope(profile: try accountProfileFixture(
                    displayName: patch.displayName,
                    city: patch.city,
                    district: patch.district,
                    avatarAssetID: patch.avatarAssetID
                ))
            }
        )
        let model = ProfileViewModel(
            user: AppUser(id: scope.userID, phone: "13800138000", displayName: "当前昵称"),
            family: AppFamily(id: scope.familyID, name: "测试家庭", role: "owner"),
            repository: repository,
            scope: scope,
            seed: fixtureProfile(canEdit: true)
        )
        let original = model.accountProfile
        let saveTask = Task { @MainActor in
            await model.saveAccountProfile(
                displayName: "不应保存",
                city: "上海市",
                district: "徐汇区",
                avatarJPEG: Data([1, 2, 3])
            )
        }
        for _ in 0..<100 {
            if await recorder.uploadStarted { break }
            try await Task.sleep(nanoseconds: 2_000_000)
        }

        saveTask.cancel()
        let saved = await saveTask.value

        XCTAssertFalse(saved)
        XCTAssertEqual(model.accountProfile, original)
        XCTAssertFalse(model.savingAccountProfile)
        XCTAssertNil(model.inlineError)
        let patchCount = await recorder.patchCount
        XCTAssertEqual(patchCount, 0)
    }

    @MainActor
    func testCancelledAccountProfileRefreshCannotOverwriteCurrentProfile() async throws {
        let user = AppUser(id: "user-1", phone: "13800138000", displayName: "当前昵称")
        let current = AccountProfile(user: user)
        let late = try accountProfileFixture(
            displayName: "迟到的资料",
            city: "上海市",
            district: "徐汇区",
            avatarAssetID: "asset-late"
        )
        let repository = AppRepository(
            cache: try DiskCache(rootURL: temporaryDirectory()),
            bootstrapLoader: { throw APIError.invalidResponse },
            accountProfileLoader: {
                try? await Task.sleep(nanoseconds: 100_000_000)
                return AccountProfileEnvelope(profile: late)
            }
        )
        let model = ProfileViewModel(
            user: user,
            family: AppFamily(id: "family-1", name: "测试家庭", role: "owner"),
            repository: repository,
            scope: CacheScope(userID: "user-1", familyID: "family-1"),
            seed: fixtureProfile(canEdit: true)
        )

        model.refreshAccountProfile()
        try await Task.sleep(nanoseconds: 20_000_000)
        model.cancelInFlightAccountProfileRefresh()
        try await Task.sleep(nanoseconds: 140_000_000)

        XCTAssertEqual(model.accountProfile, current)
        XCTAssertNil(model.inlineError)
    }

    @MainActor
    func testCancelledAccountProfileSaveCannotPublishReturnedServerState() async throws {
        let user = AppUser(id: "user-1", phone: "13800138000", displayName: "当前昵称")
        let original = AccountProfile(user: user)
        let updated = try accountProfileFixture(
            displayName: "不应发布",
            city: "上海市",
            district: "徐汇区",
            avatarAssetID: "asset-new"
        )
        let repository = AppRepository(
            cache: try DiskCache(rootURL: temporaryDirectory()),
            bootstrapLoader: { throw APIError.invalidResponse },
            accountProfileUpdater: { _ in
                try? await Task.sleep(nanoseconds: 100_000_000)
                return AccountProfileEnvelope(profile: updated)
            }
        )
        let model = ProfileViewModel(
            user: user,
            family: AppFamily(id: "family-1", name: "测试家庭", role: "owner"),
            repository: repository,
            scope: CacheScope(userID: "user-1", familyID: "family-1"),
            seed: fixtureProfile(canEdit: true)
        )
        let saveTask = Task { @MainActor in
            await model.saveAccountProfile(
                displayName: "新昵称",
                city: "上海市",
                district: "徐汇区",
                avatarJPEG: nil
            )
        }

        try await Task.sleep(nanoseconds: 20_000_000)
        saveTask.cancel()
        let saved = await saveTask.value

        XCTAssertFalse(saved)
        XCTAssertEqual(model.accountProfile, original)
        XCTAssertFalse(model.savingAccountProfile)
        XCTAssertNil(model.inlineError)
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

private actor ProfileLoadSequence {
    private let profiles: [ProfileData]
    private(set) var loadCount = 0

    init(profiles: [ProfileData]) {
        self.profiles = profiles
    }

    func next() -> ProfileData {
        let profile = profiles[min(loadCount, profiles.count - 1)]
        loadCount += 1
        return profile
    }
}

private actor FamilyMutationRecorder {
    private(set) var actions: [String] = []
    func record(_ action: String) { actions.append(action) }
    func snapshot() -> [String] { actions }
}

private actor AccountProfileMutationRecorder {
    private var uploadFamilyID: String?
    private var uploadCount = 0
    private var patch: AccountProfilePatch?

    func recordUpload(familyID: String, media: [MemoryUploadAsset]) {
        uploadFamilyID = familyID
        uploadCount = media.count
    }

    func recordPatch(_ patch: AccountProfilePatch) {
        self.patch = patch
    }

    func snapshot() -> (uploadFamilyID: String?, uploadCount: Int, patch: AccountProfilePatch?) {
        (uploadFamilyID, uploadCount, patch)
    }
}

private actor CancelledAccountProfileRecorder {
    private(set) var uploadStarted = false
    private(set) var patchCount = 0

    func recordUploadStarted() { uploadStarted = true }
    func recordPatch(_ patch: AccountProfilePatch) { patchCount += 1 }
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
    deviceID: String = "edge-1",
    name: String = "客厅主视",
    status: String = "online",
    enabled: Bool = true
) -> CameraConfig {
    CameraConfig(
        id: id,
        familyID: "family-1",
        deviceID: deviceID,
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

private func elderProfileFixture() throws -> ElderProfile {
    try JSONDecoder().decode(
        ElderProfile.self,
        from: Data(#"{"id":"elder-1","elder_id":"elder_primary","display_name":"林姨","relationship":"母亲","city":"杭州","district":"西湖区","phone":"13800138000","mobile_phone":"13800138000","home_phone":""}"#.utf8)
    )
}

private func accountProfileFixture(
    displayName: String,
    city: String,
    district: String,
    avatarAssetID: String
) throws -> AccountProfile {
    let object: [String: Any] = [
        "id": "user-1",
        "phone": "13800138000",
        "display_name": displayName,
        "city": city,
        "district": district,
        "avatar_asset_id": avatarAssetID,
        "avatar_url": "/api/v1/video/assets/\(avatarAssetID)",
        "updated_at": "2026-07-28T08:00:00.000Z",
    ]
    return try JSONDecoder().decode(AccountProfile.self, from: JSONSerialization.data(withJSONObject: object))
}

private extension FamilyRole {
    static var allProductLabels: [String] { [FamilyRole.creator.rawValue, FamilyRole.member.rawValue] }
}
