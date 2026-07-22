import XCTest

final class TabStateTests: XCTestCase {
    func testMainShellHasFivePersistentTabs() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestMain"]
        app.launch()

        XCTAssertTrue(app.tabBars.buttons["首页"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.tabBars.buttons["守护"].exists)
        XCTAssertTrue(app.tabBars.buttons["事件"].exists)
        XCTAssertTrue(app.tabBars.buttons["精选"].exists)
        XCTAssertTrue(app.tabBars.buttons["我的"].exists)
    }

    func testSwitchingTabsKeepsHomeContentMounted() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestMain"]
        app.launch()

        let home = app.scrollViews["home-content-anchor"]
        XCTAssertTrue(home.waitForExistence(timeout: 5))
        app.tabBars.buttons["守护"].tap()
        XCTAssertTrue(app.staticTexts["守护画面"].waitForExistence(timeout: 2))
        app.tabBars.buttons["首页"].tap()
        XCTAssertTrue(home.waitForExistence(timeout: 2))
    }
}
