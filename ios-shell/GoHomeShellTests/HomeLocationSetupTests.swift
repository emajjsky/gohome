import XCTest
@testable import GoHomeShell

final class HomeLocationSetupTests: XCTestCase {
    func testLocationUpdatePreservesExistingCaredForProfileFields() throws {
        let profile = try JSONDecoder().decode(ElderProfile.self, from: Data(#"""
        {
          "id":"profile-1",
          "elder_id":"elder-primary",
          "display_name":"妈妈",
          "relationship":"母亲",
          "age":68,
          "city":"旧城市",
          "district":"旧区域",
          "phone":"13800138000",
          "mobile_phone":"13800138000",
          "home_phone":"021-12345678",
          "home_location_label":""
        }
        """#.utf8))

        let payload = HomeLocationProfileUpdate.payload(
            preserving: profile,
            latitude: 31.2304,
            longitude: 121.4737,
            location: ResolvedLocation(city: "上海市", district: "黄浦区")
        )

        XCTAssertEqual(payload.displayName, "妈妈")
        XCTAssertEqual(payload.relationship, "母亲")
        XCTAssertEqual(payload.phone, "13800138000")
        XCTAssertEqual(payload.mobilePhone, "13800138000")
        XCTAssertEqual(payload.homePhone, "021-12345678")
        XCTAssertEqual(payload.city, "上海市")
        XCTAssertEqual(payload.district, "黄浦区")
        XCTAssertEqual(payload.homeLatitude, 31.2304)
        XCTAssertEqual(payload.homeLongitude, 121.4737)
        XCTAssertEqual(payload.homeLocationLabel, "黄浦区 · 上海市")
    }

    func testLocationUpdateCanSaveCoordinatesWhenAddressResolutionFails() throws {
        let profile = try JSONDecoder().decode(ElderProfile.self, from: Data(#"""
        {
          "id":"profile-1",
          "elder_id":"elder-primary",
          "display_name":"妈妈",
          "relationship":"母亲",
          "city":"杭州市",
          "district":"西湖区",
          "home_location_label":"西湖区 · 杭州市"
        }
        """#.utf8))

        let payload = HomeLocationProfileUpdate.payload(
            preserving: profile,
            latitude: 30.2741,
            longitude: 120.1551,
            location: nil
        )

        XCTAssertEqual(payload.city, "杭州市")
        XCTAssertEqual(payload.district, "西湖区")
        XCTAssertEqual(payload.homeLatitude, 30.2741)
        XCTAssertEqual(payload.homeLongitude, 120.1551)
        XCTAssertEqual(payload.homeLocationLabel, "家庭位置")
    }
}
