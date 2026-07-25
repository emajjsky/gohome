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
}
