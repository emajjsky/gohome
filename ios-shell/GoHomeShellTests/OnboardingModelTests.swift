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

    func testFamilyInvitationConsumeResponseAcceptsNumericFamilyIdentifier() throws {
        let data = Data(#"""
        {"joined":true,"family":{"id":12,"name":"杭州的家","member_count":2}}
        """#.utf8)

        let value = try JSONDecoder().decode(FamilyInvitationConsumeResponse.self, from: data)

        XCTAssertTrue(value.joined)
        XCTAssertEqual(value.family.id, "12")
        XCTAssertEqual(value.family.memberCount, 2)
    }

    func testBindingAndCameraAcceptNumericIdentifiers() throws {
        let binding = try JSONDecoder().decode(DeviceBinding.self, from: Data(#"""
        {
          "id":3,"family_id":12,"device_id":"edge-1","device_name":"回家盒子","status":"active","last_seen_at":null
        }
        """#.utf8))
        let camera = try JSONDecoder().decode(CameraConfig.self, from: Data(#"""
        {
          "id":9,"family_id":12,"device_id":"edge-1","name":"客厅主视","room":"客厅","status":"pending_edge_sync",
          "connection":{"scheme":"rtsp","host":"192.168.1.7","port":554,"path":"/1/2","username_set":true}
        }
        """#.utf8))

        XCTAssertEqual(binding.id, "3")
        XCTAssertEqual(binding.familyID, "12")
        XCTAssertEqual(camera.id, "9")
        XCTAssertEqual(camera.familyID, "12")
        XCTAssertEqual(camera.connection?.host, "192.168.1.7")
        XCTAssertEqual(camera.connection?.path, "/1/2")
        XCTAssertEqual(camera.connection?.usernameSet, true)
        XCTAssertTrue(camera.enabled)
        XCTAssertFalse(camera.passwordSet)
    }

    func testCameraMutationPayloadsExposeOnlyIntendedFields() throws {
        let create = CameraCreateRequest(
            familyID: "family-1",
            deviceID: "edge-1",
            name: "客厅主视",
            room: "客厅",
            streamURL: "rtsp://192.168.1.20:554/1/2",
            username: "admin",
            password: "secret",
            enabled: true
        )
        let createObject = try jsonObject(create)
        XCTAssertEqual(createObject["family_id"] as? String, "family-1")
        XCTAssertEqual(createObject["device_id"] as? String, "edge-1")
        XCTAssertEqual(createObject["stream_url"] as? String, "rtsp://192.168.1.20:554/1/2")
        XCTAssertEqual(Set(createObject.keys), ["family_id", "device_id", "name", "room", "stream_url", "username", "password", "enabled"])

        let updateObject = try jsonObject(CameraUpdateRequest(
            name: "卧室主视",
            room: "卧室",
            streamURL: "rtsp://192.168.1.7:554/1/2",
            username: nil,
            password: nil,
            enabled: false
        ))
        XCTAssertEqual(Set(updateObject.keys), ["name", "room", "stream_url", "enabled"])
        XCTAssertNil(updateObject["family_id"])
        XCTAssertNil(updateObject["device_id"])
        XCTAssertEqual(updateObject["stream_url"] as? String, "rtsp://192.168.1.7:554/1/2")
    }

    func testCameraStreamAddressBuildsValidatedRTSPURL() {
        XCTAssertEqual(
            CameraStreamAddress.makeURL(scheme: "rtsp", host: "192.168.1.7", port: "554", path: "1/2"),
            "rtsp://192.168.1.7:554/1/2"
        )
        XCTAssertEqual(
            CameraStreamAddress.makeURL(scheme: "rtsps", host: "camera.local", port: "322", path: "/live?channel=1"),
            "rtsps://camera.local:322/live?channel=1"
        )
        XCTAssertNil(CameraStreamAddress.makeURL(scheme: "http", host: "192.168.1.7", port: "554", path: "/1/2"))
        XCTAssertNil(CameraStreamAddress.makeURL(scheme: "rtsp", host: "", port: "554", path: "/1/2"))
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

    private func jsonObject<Value: Encodable>(_ value: Value) throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(value)) as? [String: Any])
    }
}
