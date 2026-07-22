import XCTest

final class OnboardingFlowTests: XCTestCase {
    func testFamilyStepIsTheOnlyVisibleFirstStep() {
        let app = launch(step: "family")
        XCTAssertTrue(app.staticTexts["先建立一个家庭"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.staticTexts["添加家庭成员"].exists)
        XCTAssertTrue(app.segmentedControls.firstMatch.exists)
    }

    func testProfileStepRequiresProfileBeforeContinuing() {
        let app = launch(step: "profile")
        XCTAssertTrue(app.staticTexts["添加家庭成员"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.textFields.firstMatch.exists)
        XCTAssertFalse(app.staticTexts["连接守护盒子"].exists)
    }

    func testDeviceStepShowsLocalDiscoverySurface() {
        let app = launch(step: "device")
        XCTAssertTrue(app.staticTexts["连接守护盒子"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["演示守护盒子"].waitForExistence(timeout: 5))
    }

    func testCameraStepIsReachableOnlyAsItsOwnStep() {
        let app = launch(step: "camera")
        XCTAssertTrue(app.staticTexts["添加第一路画面"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["测试并保存"].exists)
    }

    private func launch(step: String) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTestState", "-uiTestOnboardingStep=\(step)"]
        app.launch()
        return app
    }
}
