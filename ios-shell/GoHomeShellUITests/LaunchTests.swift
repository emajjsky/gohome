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

    func testAuthenticatedServiceFailureShowsRecoverableStateInsteadOfLogin() {
        let app = XCUIApplication()
        app.launchArguments += ["-uiTestState", "-uiTestSessionUnavailable"]
        app.launch()

        XCTAssertTrue(app.staticTexts["暂时无法连接服务"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["重新加载"].isHittable)
        XCTAssertFalse(app.textFields["phone-input"].exists)
    }
}
