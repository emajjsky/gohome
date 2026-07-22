import XCTest

final class AuthFlowTests: XCTestCase {
    func testSignedOutAuthControlsAndModeSwitchAreNative() {
        let app = XCUIApplication()
        app.launchArguments.append("-uiTestState")
        app.launch()

        XCTAssertTrue(app.textFields["phone-input"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.textFields["code-input"].exists)
        XCTAssertTrue(app.buttons["request-code-button"].exists)
        XCTAssertTrue(app.buttons["auth-submit-button"].exists)
        XCTAssertTrue(app.segmentedControls["auth-mode-picker"].exists)
        XCTAssertFalse(app.webViews.firstMatch.exists)

        app.textFields["code-input"].tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 2))
        XCTAssertTrue(app.buttons["auth-submit-button"].isHittable)
    }
}
