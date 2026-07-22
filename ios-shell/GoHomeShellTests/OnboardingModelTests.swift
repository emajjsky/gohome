import XCTest
@testable import GoHomeShell

final class OnboardingModelTests: XCTestCase {
    func testBootstrapAcceptsNumericCloudIdentifiers() throws {
        let data = Data(#"""
        {
          "user":{"id":7,"phone":"13800000000","display_name":"Test"},
          "families":[{"id":12,"name":"杭州的家"}],
          "active_family_id":12,
          "onboarding":{"next_step":"device","complete":false},
          "unread_count":0,
          "revision":"r1"
        }
        """#.utf8)

        let value = try JSONDecoder().decode(BootstrapResponse.self, from: data)

        XCTAssertEqual(value.user.id, "7")
        XCTAssertEqual(value.families.first?.id, "12")
        XCTAssertEqual(value.activeFamilyID, "12")
        XCTAssertEqual(value.onboarding.nextStep, .device)
    }

    func testBindingAndCameraAcceptNumericIdentifiers() throws {
        let binding = try JSONDecoder().decode(DeviceBinding.self, from: Data(#"""
        {
          "id":3,"family_id":12,"device_id":"edge-1","device_name":"回家盒子","status":"active","last_seen_at":null
        }
        """#.utf8))
        let camera = try JSONDecoder().decode(CameraConfig.self, from: Data(#"""
        {
          "id":9,"family_id":12,"device_id":"edge-1","name":"客厅主视","room":"客厅","status":"pending_edge_sync"
        }
        """#.utf8))

        XCTAssertEqual(binding.id, "3")
        XCTAssertEqual(binding.familyID, "12")
        XCTAssertEqual(camera.id, "9")
        XCTAssertEqual(camera.familyID, "12")
    }

    func testBindingCodeAcceptsNumericIdentifiers() throws {
        let code = try JSONDecoder().decode(DeviceBindingCode.self, from: Data(#"""
        {
          "id":4,"family_id":12,"code":"GH-123456","status":"issued","expires_at":"2026-07-22T11:00:00Z"
        }
        """#.utf8))

        XCTAssertEqual(code.id, "4")
        XCTAssertEqual(code.familyID, "12")
        XCTAssertEqual(code.code, "GH-123456")
    }
}
