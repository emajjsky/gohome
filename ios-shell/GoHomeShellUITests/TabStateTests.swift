import XCTest

final class TabStateTests: XCTestCase {
    func testMainShellHasFivePersistentTabs() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestMain"]
        app.launch()

        XCTAssertTrue(app.tabBars.buttons["首页"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.tabBars.buttons["守护"].exists)
        XCTAssertTrue(app.tabBars.buttons["记忆"].exists)
        XCTAssertTrue(app.tabBars.buttons["社区"].exists)
        XCTAssertTrue(app.tabBars.buttons["我的"].exists)
    }

    func testSwitchingTabsKeepsHomeContentMounted() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestMain"]
        app.launch()

        let home = app.scrollViews["home-content-anchor"]
        XCTAssertTrue(home.waitForExistence(timeout: 5))
        app.tabBars.buttons["守护"].tap()
        XCTAssertTrue(app.scrollViews["guard-content"].waitForExistence(timeout: 2))
        XCTAssertTrue(app.descendants(matching: .any)["guard-camera-stage"].exists)
        app.tabBars.buttons["首页"].tap()
        XCTAssertTrue(home.waitForExistence(timeout: 2))
    }

    func testCommunityTabOpensNativeProductRecommendations() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestMain"]
        app.launch()

        app.tabBars.buttons["社区"].tap()

        XCTAssertTrue(app.scrollViews["product-recommendations-content"].waitForExistence(timeout: 2))
        XCTAssertFalse(app.webViews.firstMatch.exists)
    }
}
