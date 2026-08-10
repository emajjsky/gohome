import XCTest

final class ProfileFlowTests: XCTestCase {
    func testProfileShowsNativeSettingsAndCreatorRules() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestMain", "-uiTestProfile"]
        app.launch()

        XCTAssertTrue(app.tabBars.buttons["我的"].waitForExistence(timeout: 5))
        app.tabBars.buttons["我的"].tap()
        XCTAssertTrue(app.staticTexts["账户与家庭"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.images["profile-account-avatar"].exists)
        let avatarScreenshot = XCTAttachment(screenshot: app.screenshot())
        avatarScreenshot.name = "Native profile default avatar"
        avatarScreenshot.lifetime = .keepAlways
        add(avatarScreenshot)
        XCTAssertFalse(app.staticTexts["创建者"].exists)
        XCTAssertFalse(app.staticTexts["管理员"].exists)

        app.buttons["守护规则, 可配置"].tap()
        XCTAssertTrue(app.navigationBars["守护规则"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.switches["人物出现"].exists)
        XCTAssertTrue(app.switches["姿态与跌倒"].exists)
        XCTAssertFalse(app.switches["烟火风险"].exists)
        XCTAssertTrue(app.descendants(matching: .any)["rule-number-静止提醒"].exists)
        XCTAssertTrue(app.descendants(matching: .any)["rule-number-无人提醒"].exists)
        XCTAssertFalse(app.staticTexts["抽帧间隔"].exists)
        XCTAssertFalse(app.staticTexts["fall_score_threshold"].exists)
        XCTAssertFalse(app.staticTexts["yolo_confidence"].exists)

        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "Native profile rule settings"
        screenshot.lifetime = .keepAlways
        add(screenshot)
    }

    func testCreatorCanOpenActivityDataSettingsWithoutTechnicalFields() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestMain", "-uiTestProfile"]
        app.launch()

        XCTAssertTrue(app.tabBars.buttons["我的"].waitForExistence(timeout: 5))
        app.tabBars.buttons["我的"].tap()
        app.buttons["活动数据与报告, 已开启"].tap()

        XCTAssertTrue(app.navigationBars["活动数据与报告"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.switches["记录活动轨迹"].exists)
        XCTAssertTrue(app.staticTexts["保留时间"].exists)
        XCTAssertTrue(app.switches["活动变化提醒"].exists)
        XCTAssertFalse(app.switches["每日活动摘要"].exists)
        XCTAssertFalse(app.switches["每周活动趋势"].exists)
        XCTAssertFalse(app.switches["多模态复核"].exists)
        XCTAssertFalse(app.staticTexts["activity_history"].exists)
        XCTAssertFalse(app.staticTexts["retention_days"].exists)
    }

    func testCreatorCanOpenDeviceAndCameraManagement() {
        let app = launchProfile()

        app.buttons["家庭盒子与摄像头, 1 路画面"].tap()
        XCTAssertTrue(app.navigationBars["设备与守护"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.staticTexts["演示守护盒子"].exists)
        XCTAssertTrue(app.buttons["添加家庭盒子"].exists)
        XCTAssertTrue(app.buttons["解除绑定：演示守护盒子"].exists)
        XCTAssertTrue(app.buttons["添加摄像头"].exists)

        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "Native device management"
        screenshot.lifetime = .keepAlways
        add(screenshot)

        app.staticTexts["客厅主视"].tap()
        XCTAssertTrue(app.navigationBars["编辑摄像头"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.buttons["保存并同步"].exists)
        XCTAssertTrue(app.buttons["删除摄像头"].exists)
        XCTAssertFalse(app.staticTexts["视频地址"].exists)
        XCTAssertFalse(app.staticTexts["rtsp"].exists)
    }

    func testFamilyInvitationEntryIsCreatorOnly() {
        let creatorApp = launchProfile()
        creatorApp.buttons["我的家庭, 家庭管理"].tap()
        XCTAssertTrue(creatorApp.navigationBars["家庭"].waitForExistence(timeout: 3))
        XCTAssertTrue(creatorApp.staticTexts["邀请家人"].exists)
        XCTAssertTrue(creatorApp.buttons["生成邀请码"].exists)

        creatorApp.terminate()
        let memberApp = launchProfile(extraArguments: ["-uiTestMember"])
        memberApp.buttons["我的家庭, 家庭管理"].tap()
        XCTAssertTrue(memberApp.navigationBars["家庭"].waitForExistence(timeout: 3))
        XCTAssertFalse(memberApp.staticTexts["邀请家人"].exists)
        XCTAssertFalse(memberApp.buttons["生成邀请码"].exists)
    }

    func testMemberSeesDeviceConfigurationWithoutMutationControls() {
        let app = launchProfile(extraArguments: ["-uiTestMember"])

        app.buttons["家庭盒子与摄像头, 1 路画面"].tap()
        XCTAssertTrue(app.navigationBars["设备与守护"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.staticTexts["演示守护盒子"].exists)
        XCTAssertTrue(app.staticTexts["客厅主视"].exists)
        XCTAssertFalse(app.buttons["添加家庭盒子"].exists)
        XCTAssertFalse(app.buttons["解除绑定：演示守护盒子"].exists)
        XCTAssertFalse(app.buttons["添加摄像头"].exists)
        XCTAssertFalse(app.navigationBars["编辑摄像头"].exists)
    }

    func testPrivacyDataShowsExportAndRequiresConfirmationForDeletion() {
        let app = launchProfile()

        app.buttons["隐私与数据, 已保护"].tap()
        XCTAssertTrue(app.navigationBars["隐私与数据"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.buttons["privacy-export-data"].exists)
        XCTAssertTrue(app.buttons["privacy-delete-account"].exists)
        XCTAssertFalse(app.alerts["永久删除账号？"].exists)

        app.buttons["privacy-delete-account"].tap()
        XCTAssertTrue(app.alerts["永久删除账号？"].waitForExistence(timeout: 2))
        XCTAssertTrue(app.alerts["永久删除账号？"].buttons["永久删除"].exists)
        app.alerts["永久删除账号？"].buttons["取消"].tap()
    }

    func testContentPreferencesOfferRealQuietHoursAndRecommendationEditors() {
        let app = launchProfile()

        app.buttons["提醒与内容偏好, 已开启"].tap()
        XCTAssertTrue(app.navigationBars["提醒与内容"].waitForExistence(timeout: 3))

        app.staticTexts["免打扰"].tap()
        XCTAssertTrue(app.navigationBars["免打扰"].waitForExistence(timeout: 2))
        XCTAssertTrue(app.descendants(matching: .any)["quiet-hours-start"].exists)
        XCTAssertTrue(app.descendants(matching: .any)["quiet-hours-end"].exists)
        app.buttons["取消"].tap()

        app.staticTexts["推荐方向"].tap()
        XCTAssertTrue(app.navigationBars["推荐方向"].waitForExistence(timeout: 2))
        XCTAssertTrue(app.staticTexts["照明与视野"].exists)
        XCTAssertTrue(app.staticTexts["夜间照明"].exists)
        app.buttons["取消"].tap()
    }

    func testCreatorCanAddMissingCaredForProfileWhileMemberCannot() {
        let creatorApp = launchProfile()
        creatorApp.buttons["照护资料, 未填写"].tap()
        XCTAssertTrue(creatorApp.buttons["添加资料"].waitForExistence(timeout: 2))
        creatorApp.buttons["添加资料"].tap()
        XCTAssertTrue(creatorApp.navigationBars["编辑照护资料"].waitForExistence(timeout: 2))
        creatorApp.buttons["取消"].tap()

        creatorApp.terminate()
        let memberApp = launchProfile(extraArguments: ["-uiTestMember"])
        memberApp.buttons["照护资料, 未填写"].tap()
        XCTAssertTrue(memberApp.staticTexts["尚未填写照护资料"].waitForExistence(timeout: 2))
        XCTAssertFalse(memberApp.buttons["添加资料"].exists)
    }

    private func launchProfile(extraArguments: [String] = []) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestMain", "-uiTestProfile"] + extraArguments
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["我的"].waitForExistence(timeout: 5))
        app.tabBars.buttons["我的"].tap()
        XCTAssertTrue(app.staticTexts["账户与家庭"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.images["profile-account-avatar"].exists)
        return app
    }
}
