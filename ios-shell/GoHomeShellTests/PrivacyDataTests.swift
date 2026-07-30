import XCTest
@testable import GoHomeShell

final class PrivacyDataTests: XCTestCase {
    @MainActor
    func testDeletionPlanLoadsAndAllowedDeletionCallsRepositoryOnce() async throws {
        let recorder = AccountDeletionRecorder()
        let repository = AppRepository(
            cache: try makeCache(),
            bootstrapLoader: { throw APIError.invalidResponse },
            accountDeletionPlanLoader: { allowedPlan() },
            accountDeleter: {
                await recorder.recordDeletion()
                return AccountDeleteResponse(deleted: true)
            }
        )
        let model = PrivacyDataViewModel(repository: repository)

        model.start()
        try await waitUntil { model.plan != nil }
        XCTAssertTrue(model.plan?.canDelete == true)
        let deleted = await model.deleteAccount()
        let deletionCount = await recorder.count()
        XCTAssertTrue(deleted)
        XCTAssertEqual(deletionCount, 1)
    }

    @MainActor
    func testBlockedPlanNeverCallsAccountDeletion() async throws {
        let recorder = AccountDeletionRecorder()
        let repository = AppRepository(
            cache: try makeCache(),
            bootstrapLoader: { throw APIError.invalidResponse },
            accountDeletionPlanLoader: { blockedPlan() },
            accountDeleter: {
                await recorder.recordDeletion()
                return AccountDeleteResponse(deleted: true)
            }
        )
        let model = PrivacyDataViewModel(repository: repository)

        model.start()
        try await waitUntil { model.plan != nil }
        XCTAssertFalse(model.plan?.canDelete == true)
        let deleted = await model.deleteAccount()
        let deletionCount = await recorder.count()
        XCTAssertFalse(deleted)
        XCTAssertEqual(deletionCount, 0)
    }

    @MainActor
    func testExportWritesShareableJSONFile() async throws {
        let payload = Data("{\"schema_version\":1}".utf8)
        let repository = AppRepository(
            cache: try makeCache(),
            bootstrapLoader: { throw APIError.invalidResponse },
            accountExporter: { payload },
            accountDeletionPlanLoader: { allowedPlan() }
        )
        let model = PrivacyDataViewModel(repository: repository)

        model.exportData()
        try await waitUntil { model.exportURL != nil }
        let url = try XCTUnwrap(model.exportURL)
        XCTAssertEqual(try Data(contentsOf: url), payload)
        XCTAssertEqual(url.pathExtension, "json")
        model.clearExport()
        XCTAssertNil(model.exportURL)
        XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    }

    private func makeCache() throws -> DiskCache {
        try DiskCache(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true))
    }

    @MainActor
    private func waitUntil(_ condition: @escaping () -> Bool) async throws {
        for _ in 0..<100 where !condition() {
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        XCTAssertTrue(condition())
    }
}

private actor AccountDeletionRecorder {
    private var deletionCount = 0
    func recordDeletion() { deletionCount += 1 }
    func count() -> Int { deletionCount }
}

private func allowedPlan() -> AccountDeletionPlan {
    AccountDeletionPlan(
        canDelete: true,
        requiresOwnershipTransfer: false,
        families: [],
        blockers: [],
        deletionScope: AccountDeletionScope(familiesToDelete: ["family-a"], membershipsToLeave: [], authoredMemories: 2),
        retentionNote: ""
    )
}

private func blockedPlan() -> AccountDeletionPlan {
    AccountDeletionPlan(
        canDelete: false,
        requiresOwnershipTransfer: true,
        families: [],
        blockers: [AccountDeletionBlocker(
            code: "ownership_transfer_required",
            familyID: "family-a",
            familyName: "A Home",
            message: "请先转交家庭创建者身份"
        )],
        deletionScope: AccountDeletionScope(familiesToDelete: [], membershipsToLeave: [], authoredMemories: 0),
        retentionNote: ""
    )
}
