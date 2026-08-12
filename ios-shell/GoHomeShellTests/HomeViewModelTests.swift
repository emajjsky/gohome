import XCTest
@testable import GoHomeShell

final class HomeViewModelTests: XCTestCase {
    func testHomeDecodesVerifiedVisitAndExplicitReturnPlan() throws {
        let home = try JSONDecoder().decode(HomeResponse.self, from: Data("""
        {"family":null,"weather":null,"calendar":[],"distance":null,"critical_alert":null,
         "return_home":{"is_at_home":false,"network_matched":false,"last_visit_at":"2026-08-10T03:00:00Z","days_since_last_visit":2},
         "return_plan":{"id":"plan-1","starts_at":"2026-08-19T10:00:00Z","note":"周末回家吃饭","status":"planned","updated_at":"2026-08-12T05:00:00Z"},
         "articles":[],"cameras":[],"revision":"r-plan"}
        """.utf8))

        XCTAssertEqual(home.returnHome?.daysSinceLastVisit, 2)
        XCTAssertEqual(home.returnHome?.lastVisitAt, "2026-08-10T03:00:00Z")
        XCTAssertEqual(home.returnPlan?.id, "plan-1")
        XCTAssertEqual(home.returnPlan?.note, "周末回家吃饭")
    }

    func testHomeDecodesCareMessageAndRemainsCompatibleWhenItIsAbsent() throws {
        let withCare = try decodeHome(careFragment: """
        ,"care_message":{
          "message_id":"message-1","message_type":"return_home","title":"聊聊周末","subtitle":"联系建议",
          "body":"最近天气不错。","facts":[],"actions":[{"key":"shared","label":"分享"}],"status":"open",
          "metadata":{"trigger_reason":"days_since_last_visit","topics":["周末安排"],"message_variants":["周末有空一起吃饭吗？"],"snoozed_until":null},
          "created_at":"2026-07-23T08:00:00Z","updated_at":null
        }
        """)
        XCTAssertEqual(withCare.careMessage?.messageID, "message-1")
        XCTAssertEqual(withCare.careMessage?.metadata.topics, ["周末安排"])
        XCTAssertEqual(withCare.careMessage?.actions.first?.type, "shared")

        XCTAssertNil(try decodeHome().careMessage)
    }

    @MainActor
    func testContactedActionRemovesCareMessageWithoutReloadingHome() async throws {
        let fixture = try HomeCareFixture(actionResult: .success("closed"))
        let model = HomeViewModel(repository: fixture.repository, scope: fixture.scope)
        model.start()
        try await waitUntil { model.careMessage != nil }

        let succeeded = await model.recordCareAction(type: "contacted", payload: ["selected_text": "周末聊聊"])
        let callCount = await fixture.calls.value
        XCTAssertTrue(succeeded)
        XCTAssertNil(model.careMessage)
        XCTAssertNil(model.careActionError)
        XCTAssertEqual(callCount, 1)
    }

    @MainActor
    func testFailedCareActionPreservesMessageAndShowsContextualError() async throws {
        let fixture = try HomeCareFixture(actionResult: .failure(APIError.invalidResponse))
        let model = HomeViewModel(repository: fixture.repository, scope: fixture.scope)
        model.start()
        try await waitUntil { model.careMessage != nil }

        let succeeded = await model.recordCareAction(type: "dismissed")
        XCTAssertFalse(succeeded)
        XCTAssertEqual(model.careMessage?.messageID, "message-1")
        XCTAssertEqual(model.careActionError, "操作没有保存，请稍后重试")
    }

    @MainActor
    func testCancelledCareActionPreservesMessageWithoutError() async throws {
        let cache = try DiskCache(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString))
        let scope = CacheScope(userID: "user-1", familyID: "family-1")
        let home = try JSONDecoder().decode(HomeResponse.self, from: Data("""
        {"family":null,"weather":null,"calendar":[],"distance":null,"critical_alert":null,
         "care_message":{"message_id":"message-cancel","message_type":"return_home","title":"聊聊周末","subtitle":"联系建议",
         "body":"最近天气不错。","facts":[],"actions":[],"status":"open",
         "metadata":{"trigger_reason":"days_since_last_visit","topics":["周末安排"],"message_variants":["周末有空一起吃饭吗？"],"snoozed_until":null},
         "created_at":"2026-07-23T08:00:00Z","updated_at":null},"articles":[],"cameras":[],"revision":"r1"}
        """.utf8))
        let repository = AppRepository(
            cache: cache,
            bootstrapLoader: { throw APIError.invalidResponse },
            homeLoader: { _ in home },
            messageActionLoader: { _, _, _ in
                try await Task.sleep(nanoseconds: 5_000_000_000)
                throw APIError.invalidResponse
            }
        )
        let model = HomeViewModel(repository: repository, scope: scope)
        model.start()
        try await waitUntil { model.careMessage != nil }
        let action = Task { @MainActor in
            await model.recordCareAction(type: "contacted")
        }

        try await waitUntil { model.pendingCareAction == "contacted" }
        model.cancelInFlightCareAction()
        let succeeded = await action.value

        XCTAssertFalse(succeeded)
        XCTAssertEqual(model.careMessage?.messageID, "message-cancel")
        XCTAssertNil(model.careActionError)
        XCTAssertNil(model.pendingCareAction)
    }

    @MainActor
    func testLateCancelledCareActionCannotClearANewerAction() async throws {
        let scope = CacheScope(userID: "user-1", familyID: "family-1")
        let home = try decodeHome(careFragment: """
        ,"care_message":{"message_id":"message-late","message_type":"return_home","title":"聊聊周末","subtitle":"联系建议",
        "body":"最近天气不错。","facts":[],"actions":[],"status":"open",
        "metadata":{"trigger_reason":"days_since_last_visit","topics":["周末安排"],"message_variants":[],"snoozed_until":null},
        "created_at":"2026-07-23T08:00:00Z","updated_at":null}
        """)
        let calls = HomeCareActionCallCounter()
        let firstResponse = HomeCareActionResponseGate()
        let secondResponse = HomeCareActionResponseGate()
        let repository = AppRepository(
            cache: try DiskCache(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)),
            bootstrapLoader: { throw APIError.invalidResponse },
            homeLoader: { _ in home },
            messageActionLoader: { _, _, _ in
                if await calls.next() == 0 { return await firstResponse.wait() }
                return await secondResponse.wait()
            }
        )
        let model = HomeViewModel(repository: repository, scope: scope)
        model.start()
        try await waitUntil { model.careMessage != nil }
        let firstAction = Task { @MainActor in await model.recordCareAction(type: "contacted") }

        try await waitUntil { model.pendingCareAction == "contacted" }
        await waitUntilHomeCareResponse(firstResponse)
        model.cancelInFlightCareAction()
        XCTAssertNil(model.pendingCareAction)
        XCTAssertEqual(model.careMessage?.messageID, "message-late")

        let secondAction = Task { @MainActor in await model.recordCareAction(type: "shared") }
        try await waitUntil { model.pendingCareAction == "shared" }
        await waitUntilHomeCareResponse(secondResponse)
        await firstResponse.release(Self.careActionResponse(status: "closed", messageID: "message-late"))
        let firstSucceeded = await firstAction.value

        XCTAssertFalse(firstSucceeded)
        XCTAssertEqual(model.pendingCareAction, "shared")
        XCTAssertEqual(model.careMessage?.messageID, "message-late")
        await secondResponse.release(Self.careActionResponse(status: "open", messageID: "message-late"))
        let secondSucceeded = await secondAction.value
        XCTAssertTrue(secondSucceeded)
        XCTAssertNil(model.pendingCareAction)
        XCTAssertNil(model.careActionError)
    }

    @MainActor
    func testRefreshPublishesNewCameraWithoutRecreatingTheViewModel() async throws {
        let cache = try DiskCache(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString))
        let scope = CacheScope(userID: "user-1", familyID: "family-1")
        let calls = HomeLoadCounter()
        let repository = AppRepository(
            cache: cache,
            bootstrapLoader: { throw APIError.invalidResponse },
            homeLoader: { _ in
                let count = await calls.increment()
                let cameras = count == 1 ? "[]" : #"[{"id":"camera-1","name":"客厅主视","status":"online"}]"#
                return try JSONDecoder().decode(HomeResponse.self, from: Data("""
                {"family":null,"weather":null,"calendar":[],"distance":null,"critical_alert":null,
                 "articles":[],"cameras":\(cameras),"revision":"r\(count)"}
                """.utf8))
            }
        )
        let model = HomeViewModel(repository: repository, scope: scope)

        model.start()
        try await waitUntil { model.state.value?.revision == "r1" }
        XCTAssertEqual(model.state.value?.cameras, [])

        model.refresh()
        try await waitUntil { model.state.value?.revision == "r2" }
        XCTAssertEqual(model.state.value?.cameras.first?.id, "camera-1")
    }

    @MainActor
    func testVisitVerificationCompletesBeforeHomeRefresh() async throws {
        let trace = HomeOperationTrace()
        let home = try decodeHome()
        let repository = AppRepository(
            cache: try DiskCache(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)),
            bootstrapLoader: { throw APIError.invalidResponse },
            homeLoader: { _ in
                await trace.append("home")
                return home
            },
            homeVisitVerifier: { _ in
                await trace.append("verify")
                return HomeVisitVerificationResponse(matched: true, recorded: true, verifiedAt: "2026-08-12T05:00:00Z")
            }
        )
        let model = HomeViewModel(repository: repository, scope: CacheScope(userID: "user-1", familyID: "family-1"))

        model.start()
        try await waitUntil { model.state.value?.revision == "r1" }

        let operationTrace = await trace.values
        XCTAssertEqual(operationTrace, ["verify", "home"])
        XCTAssertNil(model.homeVisitVerificationError)
    }

    @MainActor
    func testVisitVerificationFailurePreservesSeedAndStillRefreshesHome() async throws {
        let seed = try decodeHome()
        let refreshed = HomeResponse(
            family: nil,
            weather: HomeWeather(city: "杭州", temperature: 29, condition: "晴"),
            calendar: [],
            distance: nil,
            criticalAlert: nil,
            careMessage: nil,
            articles: [],
            cameras: [],
            revision: "refreshed"
        )
        let repository = AppRepository(
            cache: try DiskCache(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)),
            bootstrapLoader: { throw APIError.invalidResponse },
            homeLoader: { _ in refreshed },
            homeVisitVerifier: { _ in throw APIError.invalidResponse }
        )
        let model = HomeViewModel(
            repository: repository,
            scope: CacheScope(userID: "user-1", familyID: "family-1"),
            seed: seed
        )

        model.start()
        XCTAssertEqual(model.state.value?.revision, "r1")
        try await waitUntil { model.state.value?.revision == "refreshed" }

        XCTAssertEqual(model.state.value?.weather?.city, "杭州")
        XCTAssertEqual(model.homeVisitVerificationError, "当前网络暂时无法核验，到家记录未改变")
    }

    @MainActor
    func testReturnPlanSaveAndCancelUseExplicitRepositoryOperations() async throws {
        let calls = HomeReturnPlanCalls()
        let home = try decodeHome()
        let repository = AppRepository(
            cache: try DiskCache(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)),
            bootstrapLoader: { throw APIError.invalidResponse },
            homeLoader: { _ in home },
            homeVisitVerifier: { _ in HomeVisitVerificationResponse(matched: false, recorded: false, verifiedAt: nil) },
            homeReturnPlanUpdater: { familyID, request in
                await calls.recordSave(familyID: familyID, request: request)
                return HomeReturnPlanEnvelope(plan: HomeReturnPlan(
                    id: "plan-1",
                    startsAt: request.startsAt,
                    note: request.note,
                    status: "planned",
                    updatedAt: nil
                ))
            },
            homeReturnPlanCanceller: { familyID in
                await calls.recordCancel(familyID: familyID)
                return HomeReturnPlanCancelResponse(cancelled: true)
            }
        )
        let model = HomeViewModel(repository: repository, scope: CacheScope(userID: "user-1", familyID: "family-1"))
        let date = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-08-19T10:00:00Z"))

        let saved = await model.saveReturnPlan(date: date, note: "周末回家吃饭")
        let cancelled = await model.cancelReturnPlan()

        let snapshot = await calls.snapshot
        XCTAssertTrue(saved)
        XCTAssertTrue(cancelled)
        XCTAssertEqual(snapshot.savedFamilyID, "family-1")
        XCTAssertEqual(snapshot.savedRequest?.startsAt, "2026-08-19T10:00:00Z")
        XCTAssertEqual(snapshot.savedRequest?.note, "周末回家吃饭")
        XCTAssertEqual(snapshot.cancelledFamilyID, "family-1")
        XCTAssertNil(model.returnPlanError)
        XCTAssertFalse(model.isSavingReturnPlan)
    }

    @MainActor
    func testReturnPlanFailureDoesNotReportSuccess() async throws {
        let repository = AppRepository(
            cache: try DiskCache(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)),
            bootstrapLoader: { throw APIError.invalidResponse },
            homeReturnPlanUpdater: { _, _ in throw APIError.invalidResponse },
            homeReturnPlanCanceller: { _ in throw APIError.invalidResponse }
        )
        let model = HomeViewModel(repository: repository, scope: CacheScope(userID: "user-1", familyID: "family-1"))

        let saved = await model.saveReturnPlan(date: Date().addingTimeInterval(86_400), note: "")
        XCTAssertFalse(saved)
        XCTAssertEqual(model.returnPlanError, "回家计划没有保存，请稍后重试")
        let cancelled = await model.cancelReturnPlan()
        XCTAssertFalse(cancelled)
        XCTAssertEqual(model.returnPlanError, "回家计划没有取消，请稍后重试")
        XCTAssertFalse(model.isSavingReturnPlan)
    }

    @MainActor
    func testCancelledHomeRefreshCannotPublishLateState() async throws {
        let original = try decodeHome()
        let late = HomeResponse(
            family: nil,
            weather: HomeWeather(city: "迟到城市", temperature: 31, condition: "晴"),
            calendar: [],
            distance: nil,
            homeLocation: nil,
            criticalAlert: nil,
            careMessage: nil,
            articles: [],
            cameras: [HomeCamera(id: "camera-late", name: "迟到画面", status: "online")],
            revision: "late"
        )
        let repository = AppRepository(
            cache: try DiskCache(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)),
            bootstrapLoader: { throw APIError.invalidResponse },
            homeLoader: { _ in
                try? await Task.sleep(nanoseconds: 100_000_000)
                return late
            }
        )
        let model = HomeViewModel(
            repository: repository,
            scope: CacheScope(userID: "user-1", familyID: "family-1"),
            seed: original
        )

        model.refresh()
        try await Task.sleep(nanoseconds: 20_000_000)
        model.cancelInFlightLoad()
        try await Task.sleep(nanoseconds: 150_000_000)

        XCTAssertEqual(model.state.value, original)
        XCTAssertFalse(model.state.isRefreshing)
        XCTAssertNil(model.state.staleReason)
    }

    @MainActor
    func testHomeLoadRestartsAfterLifecycleCancellation() async throws {
        let home = try decodeHome()
        let repository = AppRepository(
            cache: try DiskCache(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)),
            bootstrapLoader: { throw APIError.invalidResponse },
            homeLoader: { _ in
                try? await Task.sleep(nanoseconds: 100_000_000)
                return home
            }
        )
        let model = HomeViewModel(repository: repository, scope: CacheScope(userID: "user-1", familyID: "family-1"))

        model.start()
        try await Task.sleep(nanoseconds: 20_000_000)
        model.cancelInFlightLoad()
        model.start()
        try await waitUntil { model.state.value?.revision == home.revision }

        XCTAssertEqual(model.state.value, home)
        XCTAssertFalse(model.state.isRefreshing)
    }

    func testWeatherFormattingUsesOnlyServerValues() {
        XCTAssertEqual(
            HomePresentation.weatherText(HomeWeather(city: "上海", temperature: 28, condition: "晴")),
            "上海 · 晴 · 28°"
        )
        XCTAssertNil(HomePresentation.weatherText(nil))
    }

    func testCalendarAlwaysBuildsSevenDaysFromReferenceDate() throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "Asia/Shanghai"))
        let reference = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-07-22T04:00:00Z"))
        let days = HomePresentation.calendarDays(reference: reference, calendar: calendar)

        XCTAssertEqual(days.count, 7)
        XCTAssertEqual(days.first?.day, "22")
        XCTAssertEqual(days.filter(\.isToday).count, 1)
    }

    func testDistanceNeverInventsAValue() {
        XCTAssertEqual(HomePresentation.distanceState(nil), .permissionRequired)
        XCTAssertEqual(
            HomePresentation.distanceState(HomeDistance(meters: 12_800, travelMinutes: 35)),
            .value(kilometers: 12.8, travelMinutes: 35, user: nil, home: nil)
        )
    }

    func testAcknowledgedCriticalAlertIsHidden() {
        XCTAssertNil(HomePresentation.activeAlert(HomeCriticalAlert(id: "1", title: "已处理", level: "critical", acknowledged: true)))
        XCTAssertNotNil(HomePresentation.activeAlert(HomeCriticalAlert(id: "2", title: "待处理", level: "critical", acknowledged: false)))
    }

    func testContextualTopicUsesCalendarThenWeatherAndAlwaysHasAShareableFallback() {
        let calendarHome = HomeResponse(
            family: nil,
            weather: HomeWeather(city: "上海", temperature: 28, condition: "晴"),
            calendar: [HomeCalendarEvent(id: "1", title: "周末回家", startsAt: "2026-08-01T10:00:00+08:00")],
            distance: nil,
            criticalAlert: nil,
            careMessage: nil,
            articles: [],
            cameras: [],
            revision: "1"
        )
        XCTAssertTrue(HomePresentation.contextualTopic(calendarHome).message.contains("周末回家"))

        let weatherOnly = HomeResponse(
            family: nil,
            weather: HomeWeather(city: "杭州", temperature: 31, condition: "多云"),
            calendar: [],
            distance: nil,
            criticalAlert: nil,
            careMessage: nil,
            articles: [],
            cameras: [],
            revision: "2"
        )
        XCTAssertTrue(HomePresentation.contextualTopic(weatherOnly).message.contains("杭州"))
        XCTAssertFalse(HomePresentation.contextualTopic(nil).message.isEmpty)
    }

    private func decodeHome(careFragment: String = "") throws -> HomeResponse {
        let data = Data("""
        {"family":null,"weather":null,"calendar":[],"distance":null,"critical_alert":null,
         "articles":[],"cameras":[],"revision":"r1"\(careFragment)}
        """.utf8)
        return try JSONDecoder().decode(HomeResponse.self, from: data)
    }

    private static func careActionResponse(status: String, messageID: String) -> CareMessageActionResponse {
        let data = Data("""
        {"message":{"message_id":"\(messageID)","message_type":"return_home","title":"聊聊周末","subtitle":"联系建议",
        "body":"最近天气不错。","facts":[],"actions":[],"status":"\(status)",
        "metadata":{"trigger_reason":"days_since_last_visit","topics":["周末安排"],"message_variants":[],"snoozed_until":null},
        "created_at":"2026-07-23T08:00:00Z","updated_at":null}}
        """.utf8)
        return try! JSONDecoder().decode(CareMessageActionResponse.self, from: data)
    }
}

private struct HomeCareFixture {
    let scope = CacheScope(userID: "user-1", familyID: "family-1")
    let repository: AppRepository
    let calls = CareActionCounter()

    init(actionResult: Result<String, Error>) throws {
        let cache = try DiskCache(rootURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString))
        let home = try JSONDecoder().decode(HomeResponse.self, from: Data("""
        {"family":null,"weather":null,"calendar":[],"distance":null,"critical_alert":null,
         "care_message":{"message_id":"message-1","message_type":"return_home","title":"聊聊周末","subtitle":"联系建议",
         "body":"最近天气不错。","facts":[],"actions":[],"status":"open",
         "metadata":{"trigger_reason":"days_since_last_visit","topics":["周末安排"],"message_variants":["周末有空一起吃饭吗？"],"snoozed_until":null},
         "created_at":"2026-07-23T08:00:00Z","updated_at":null},"articles":[],"cameras":[],"revision":"r1"}
        """.utf8))
        let calls = self.calls
        repository = AppRepository(
            cache: cache,
            bootstrapLoader: { throw APIError.invalidResponse },
            homeLoader: { _ in home },
            messageActionLoader: { _, _, _ in
                await calls.increment()
                let status = try actionResult.get()
                let responseData = Data("""
                {"message":{"message_id":"message-1","message_type":"return_home","title":"聊聊周末","subtitle":"联系建议",
                "body":"最近天气不错。","facts":[],"actions":[],"status":"\(status)",
                "metadata":{"trigger_reason":"days_since_last_visit","topics":["周末安排"],"message_variants":["周末有空一起吃饭吗？"],"snoozed_until":null},
                "created_at":"2026-07-23T08:00:00Z","updated_at":null}}
                """.utf8)
                return try JSONDecoder().decode(CareMessageActionResponse.self, from: responseData)
            }
        )
    }
}

private actor CareActionCounter {
    private(set) var value = 0
    func increment() { value += 1 }
}

private actor HomeLoadCounter {
    private var value = 0

    func increment() -> Int {
        value += 1
        return value
    }
}

private actor HomeOperationTrace {
    private var storage: [String] = []
    var values: [String] { storage }

    func append(_ value: String) {
        storage.append(value)
    }
}

private actor HomeReturnPlanCalls {
    struct Snapshot: Sendable {
        let savedFamilyID: String?
        let savedRequest: HomeReturnPlanRequest?
        let cancelledFamilyID: String?
    }

    private var savedFamilyID: String?
    private var savedRequest: HomeReturnPlanRequest?
    private var cancelledFamilyID: String?

    var snapshot: Snapshot {
        Snapshot(savedFamilyID: savedFamilyID, savedRequest: savedRequest, cancelledFamilyID: cancelledFamilyID)
    }

    func recordSave(familyID: String, request: HomeReturnPlanRequest) {
        savedFamilyID = familyID
        savedRequest = request
    }

    func recordCancel(familyID: String) {
        cancelledFamilyID = familyID
    }
}

private actor HomeCareActionCallCounter {
    private var count = 0

    func next() -> Int {
        defer { count += 1 }
        return count
    }
}

private actor HomeCareActionResponseGate {
    private var continuation: CheckedContinuation<CareMessageActionResponse, Never>?
    private(set) var isWaiting = false

    func wait() async -> CareMessageActionResponse {
        isWaiting = true
        return await withCheckedContinuation { continuation = $0 }
    }

    func release(_ response: CareMessageActionResponse) {
        continuation?.resume(returning: response)
        continuation = nil
    }
}

private func waitUntilHomeCareResponse(
    _ gate: HomeCareActionResponseGate,
    timeout: TimeInterval = 1
) async {
    let deadline = Date().addingTimeInterval(timeout)
    while !(await gate.isWaiting), Date() < deadline {
        try? await Task.sleep(nanoseconds: 10_000_000)
    }
    let isWaiting = await gate.isWaiting
    XCTAssertTrue(isWaiting, "Timed out waiting for care action response")
}

@MainActor
private func waitUntil(
    timeout: TimeInterval = 1,
    condition: @escaping @MainActor () -> Bool
) async throws {
    let deadline = Date().addingTimeInterval(timeout)
    while !condition() {
        if Date() >= deadline { throw APIError.invalidResponse }
        try await Task.sleep(nanoseconds: 10_000_000)
    }
}
