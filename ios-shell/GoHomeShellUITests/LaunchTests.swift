import XCTest

final class LaunchTests: XCTestCase {
    func testApplicationLaunches() {
        let app = XCUIApplication()
        app.launchArguments.append("-uiTestState")
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 10))
        XCTAssertTrue(app.textFields["phone-input"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["request-code-button"].exists)
        XCTAssertTrue(app.textFields["code-input"].exists)
        XCTAssertTrue(app.buttons["auth-submit-button"].exists)
        XCTAssertFalse(app.webViews.firstMatch.exists)
    }
}
