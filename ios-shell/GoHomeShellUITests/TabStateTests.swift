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

    func testHomeKeepsEventsOutOfBodyAndShowsGuardBadge() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestMain", "-uiTestHome"]
        app.launch()

        XCTAssertFalse(app.buttons["home-critical-alert"].exists)
        XCTAssertTrue(app.tabBars.buttons["守护"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.tabBars.buttons["守护"].value as? String, "1 item")
    }

    func testCommunityTabOpensNativeProductRecommendations() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestMain"]
        app.launch()

        app.tabBars.buttons["社区"].tap()

        XCTAssertTrue(app.scrollViews["product-recommendations-content"].waitForExistence(timeout: 2))
        XCTAssertFalse(app.webViews.firstMatch.exists)
    }

    func testMissingHomeLocationCanOpenTheSharedSetupFlow() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestMain", "-uiTestHome", "-uiTestProfile"]
        app.launch()

        let homeSetup = app.buttons["home-location-setup"]
        for _ in 0..<4 where !homeSetup.exists { app.swipeUp() }
        XCTAssertTrue(homeSetup.waitForExistence(timeout: 2))
        homeSetup.tap()
        XCTAssertTrue(app.navigationBars["设置家庭位置"].waitForExistence(timeout: 2))
        XCTAssertTrue(app.buttons["home-location-use-current"].exists)
        app.buttons["取消"].tap()
        XCTAssertTrue(app.navigationBars["设置家庭位置"].waitForNonExistence(timeout: 2))

        app.tabBars.buttons["社区"].tap()
        let communitySetup = app.buttons["community-home-location-setup"]
        XCTAssertTrue(communitySetup.waitForExistence(timeout: 2))
        XCTAssertTrue(communitySetup.isHittable)
        communitySetup.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        XCTAssertTrue(app.navigationBars["设置家庭位置"].waitForExistence(timeout: 2))
        XCTAssertTrue(app.buttons["home-location-use-current"].exists)
    }

    func testCommunityHomeLocationSetupOpensFromFreshLaunch() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestMain", "-uiTestHome", "-uiTestProfile"]
        app.launch()

        app.tabBars.buttons["社区"].tap()
        let communitySetup = app.buttons["community-home-location-setup"]
        XCTAssertTrue(communitySetup.waitForExistence(timeout: 2))
        communitySetup.tap()

        XCTAssertTrue(app.navigationBars["设置家庭位置"].waitForExistence(timeout: 2))
        XCTAssertTrue(app.buttons["home-location-use-current"].waitForExistence(timeout: 2))
    }

    func testHouseholdMemberCannotChangeTheFixedHomeLocation() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestMain", "-uiTestHome", "-uiTestProfile", "-uiTestMember"]
        app.launch()

        for _ in 0..<4 { app.swipeUp() }
        XCTAssertFalse(app.buttons["home-location-setup"].exists)

        app.tabBars.buttons["社区"].tap()
        XCTAssertFalse(app.buttons["community-home-location-setup"].exists)
        XCTAssertTrue(app.staticTexts["家庭位置未设置"].waitForExistence(timeout: 2))
    }

    func testCreatorCanCorrectAnExistingHomeLocationFromHomeAndCommunity() {
        let app = XCUIApplication()
        app.launchArguments = [
            "-uiTestState", "-uiTestMain", "-uiTestHome", "-uiTestProfile", "-uiTestFixedHomeLocation",
        ]
        app.launch()

        let homeEdit = app.buttons["home-location-edit"]
        for _ in 0..<4 where !homeEdit.exists { app.swipeUp() }
        XCTAssertTrue(homeEdit.waitForExistence(timeout: 2))
        homeEdit.tap()
        XCTAssertTrue(app.navigationBars["设置家庭位置"].waitForExistence(timeout: 2))
        app.buttons["取消"].tap()

        app.tabBars.buttons["社区"].tap()
        let communityEdit = app.buttons["community-home-location-edit"]
        XCTAssertTrue(communityEdit.waitForExistence(timeout: 2))
        communityEdit.tap()
        XCTAssertTrue(app.navigationBars["设置家庭位置"].waitForExistence(timeout: 2))
    }

    func testCommunityUsesFixedProfileLocationWithoutOpeningHome() {
        let app = XCUIApplication()
        app.launchArguments = [
            "-uiTestState", "-uiTestMain", "-uiTestProfile", "-uiTestFixedHomeLocation",
        ]
        app.launch()

        app.tabBars.buttons["社区"].tap()

        XCTAssertTrue(app.buttons["community-home-location-edit"].waitForExistence(timeout: 2))
        XCTAssertFalse(app.buttons["community-home-location-setup"].exists)
    }

    func testGuardCombinesLiveTimelineAndEventsWithoutKeepingVideoMounted() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestMain"]
        app.launch()

        app.tabBars.buttons["守护"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["guard-camera-stage"].waitForExistence(timeout: 3))

        app.buttons["轨迹"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["activity-timeline-content"].waitForExistence(timeout: 2))
        XCTAssertFalse(app.descendants(matching: .any)["guard-camera-stage"].exists)

        app.buttons["事件"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["events-list-content"].waitForExistence(timeout: 2))
        XCTAssertFalse(app.descendants(matching: .any)["guard-camera-stage"].exists)
    }
}
