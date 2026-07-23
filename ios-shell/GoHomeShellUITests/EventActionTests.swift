import XCTest

final class EventActionTests: XCTestCase {
    func testEventDetailOffersOptimisticActionsWithoutRawModelOutput() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestMain", "-uiTestEvent"]
        app.launch()

        XCTAssertTrue(app.tabBars.buttons["守护"].waitForExistence(timeout: 5))
        app.tabBars.buttons["守护"].tap()
        XCTAssertTrue(app.buttons["guard-events-entry"].waitForExistence(timeout: 3))
        app.buttons["guard-events-entry"].tap()
        XCTAssertTrue(app.buttons["event-row-ui-test-event-1"].waitForExistence(timeout: 3))
        app.buttons["event-row-ui-test-event-1"].tap()

        XCTAssertTrue(app.buttons["event-confirm-safe"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.buttons["event-mark-false-positive"].exists)
        XCTAssertTrue(app.buttons["event-share"].exists)
        XCTAssertFalse(app.staticTexts["fall_score"].exists)
        XCTAssertFalse(app.staticTexts["threshold"].exists)
        let detailScreenshot = XCTAttachment(screenshot: app.screenshot())
        detailScreenshot.name = "Native event evidence detail"
        detailScreenshot.lifetime = .keepAlways
        add(detailScreenshot)

        app.buttons["event-confirm-safe"].tap()
        XCTAssertTrue(app.staticTexts["已处理"].waitForExistence(timeout: 2))
    }
}
