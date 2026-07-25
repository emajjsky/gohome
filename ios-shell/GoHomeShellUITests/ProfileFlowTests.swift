import XCTest

final class ProfileFlowTests: XCTestCase {
    func testProfileShowsNativeSettingsAndCreatorRules() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestMain", "-uiTestProfile"]
        app.launch()

        XCTAssertTrue(app.tabBars.buttons["我的"].waitForExistence(timeout: 5))
        app.tabBars.buttons["我的"].tap()
        XCTAssertTrue(app.staticTexts["账户与家庭"].waitForExistence(timeout: 3))
        XCTAssertFalse(app.staticTexts["创建者"].exists)
        XCTAssertFalse(app.staticTexts["管理员"].exists)

        app.buttons["守护规则, 可配置"].tap()
        XCTAssertTrue(app.navigationBars["守护规则"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.switches["人物出现"].exists)
        XCTAssertTrue(app.switches["姿态与跌倒"].exists)
        XCTAssertTrue(app.switches["烟火风险"].exists)
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
        XCTAssertFalse(app.switches["每日活动摘要"].exists)
        XCTAssertFalse(app.switches["每周活动趋势"].exists)
        XCTAssertFalse(app.switches["规律异常提醒"].exists)
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
        XCTAssertTrue(app.buttons["解除演示守护盒子绑定"].exists)
        XCTAssertTrue(app.buttons["添加摄像头"].exists)

        app.staticTexts["客厅主视"].tap()
        XCTAssertTrue(app.navigationBars["编辑摄像头"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.buttons["保存并同步"].exists)
        XCTAssertTrue(app.buttons["删除摄像头"].exists)
        XCTAssertFalse(app.staticTexts["视频地址"].exists)
        XCTAssertFalse(app.staticTexts["rtsp"].exists)
    }

    func testMemberSeesDeviceConfigurationWithoutMutationControls() {
        let app = launchProfile(extraArguments: ["-uiTestMember"])

        app.buttons["家庭盒子与摄像头, 1 路画面"].tap()
        XCTAssertTrue(app.navigationBars["设备与守护"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.staticTexts["演示守护盒子"].exists)
        XCTAssertTrue(app.staticTexts["客厅主视"].exists)
        XCTAssertFalse(app.buttons["添加家庭盒子"].exists)
        XCTAssertFalse(app.buttons["解除演示守护盒子绑定"].exists)
        XCTAssertFalse(app.buttons["添加摄像头"].exists)
        XCTAssertFalse(app.navigationBars["编辑摄像头"].exists)
    }

    private func launchProfile(extraArguments: [String] = []) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestMain", "-uiTestProfile"] + extraArguments
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["我的"].waitForExistence(timeout: 5))
        app.tabBars.buttons["我的"].tap()
        XCTAssertTrue(app.staticTexts["账户与家庭"].waitForExistence(timeout: 3))
        return app
    }
}
