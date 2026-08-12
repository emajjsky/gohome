import XCTest

final class AppSurfaceAuditTests: XCTestCase {
    func testPrimaryAndSettingsSurfacesRemainNavigable() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestMain", "-uiTestHome", "-uiTestProfile", "-uiTestSurface"]
        app.launch()

        XCTAssertTrue(app.scrollViews["home-content-anchor"].waitForExistence(timeout: 5))
        capture(app, name: "01 Home")

        app.tabBars.buttons["守护"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["guard-camera-stage"].waitForExistence(timeout: 2))
        capture(app, name: "02 Guard live")

        app.buttons["轨迹"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["activity-timeline-content"].waitForExistence(timeout: 2))
        capture(app, name: "03 Guard activity")

        app.buttons["事件"].tap()
        XCTAssertTrue(app.buttons["event-row-ui-test-event-1"].waitForExistence(timeout: 2))
        capture(app, name: "04 Guard events")

        app.tabBars.buttons["记忆"].tap()
        XCTAssertTrue(app.scrollViews["memory-content-anchor"].waitForExistence(timeout: 2))
        capture(app, name: "05 Memory")

        app.tabBars.buttons["社区"].tap()
        XCTAssertTrue(app.scrollViews["product-recommendations-content"].waitForExistence(timeout: 2))
        XCTAssertTrue(app.descendants(matching: .any)["product-image-unavailable-product-1"].waitForExistence(timeout: 2))
        capture(app, name: "06 Community")
        app.buttons["product-card-product-1"].tap()
        XCTAssertTrue(app.navigationBars["推荐详情"].waitForExistence(timeout: 2))
        capture(app, name: "06b Recommendation detail")
        let officialLink = app.descendants(matching: .any)["product-official-link"]
        for _ in 0..<3 where !officialLink.exists {
            app.swipeUp()
        }
        XCTAssertTrue(officialLink.waitForExistence(timeout: 2))
        app.buttons["关闭"].tap()

        app.tabBars.buttons["我的"].tap()
        XCTAssertTrue(app.staticTexts["账户与家庭"].waitForExistence(timeout: 2))
        capture(app, name: "07 Profile")

        open(app, button: "家庭盒子与摄像头, 1 路画面", navigationTitle: "设备与守护", screenshot: "08 Devices")
        open(app, button: "守护规则, 可配置", navigationTitle: "守护规则", screenshot: "09 Guard rules")
        open(app, button: "活动数据与报告, 已开启", navigationTitle: "活动数据与报告", screenshot: "10 Activity settings")
        open(app, button: "提醒与内容偏好, 已开启", navigationTitle: "提醒与内容", screenshot: "11 Content settings")
        open(app, button: "隐私与数据, 已保护", navigationTitle: "隐私与数据", screenshot: "12 Privacy")
    }

    func testAccountEditorAndCitySelectorRemainUsable() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestMain", "-uiTestProfile"]
        app.launch()

        XCTAssertTrue(app.tabBars.buttons["我的"].waitForExistence(timeout: 5))
        app.tabBars.buttons["我的"].tap()
        let accountEntry = app.buttons["profile-account-entry"]
        XCTAssertTrue(accountEntry.waitForExistence(timeout: 2))
        accountEntry.tap()

        XCTAssertTrue(app.navigationBars["个人资料"].waitForExistence(timeout: 2))
        XCTAssertTrue(app.buttons["profile-avatar-picker"].exists)
        XCTAssertTrue(app.buttons["profile-location-action"].exists)
        capture(app, name: "13 Account editor")

        app.buttons["profile-city-selector"].tap()
        XCTAssertTrue(app.navigationBars["选择城市"].waitForExistence(timeout: 2))
        XCTAssertTrue(app.descendants(matching: .any)["city-selection-list"].exists)
        capture(app, name: "14 City selector")
    }

    private func open(_ app: XCUIApplication, button: String, navigationTitle: String, screenshot: String) {
        let entry = app.buttons[button]
        XCTAssertTrue(entry.waitForExistence(timeout: 2), "Missing settings entry: \(button)")
        entry.tap()
        XCTAssertTrue(app.navigationBars[navigationTitle].waitForExistence(timeout: 2))
        capture(app, name: screenshot)
        app.buttons["返回"].tap()
        XCTAssertTrue(app.staticTexts["账户与家庭"].waitForExistence(timeout: 2))
    }

    private func capture(_ app: XCUIApplication, name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
