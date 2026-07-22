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
}
