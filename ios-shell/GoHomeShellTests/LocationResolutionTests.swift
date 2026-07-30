import XCTest
@testable import GoHomeShell

final class LocationResolutionTests: XCTestCase {
    func testChineseMunicipalityKeepsDistrictAndCityInProductOrder() throws {
        let location = try XCTUnwrap(ResolvedLocation.resolve(
            subLocality: "徐汇区",
            locality: "上海市",
            administrativeArea: "上海市"
        ))

        XCTAssertEqual(location.city, "上海市")
        XCTAssertEqual(location.district, "徐汇区")
        XCTAssertEqual(location.displayName, "徐汇区 · 上海市")
    }

    func testProvinceFallbackWorksWhenGeocoderOmitsLocality() throws {
        let location = try XCTUnwrap(ResolvedLocation.resolve(
            subLocality: "余杭区",
            locality: nil,
            administrativeArea: "浙江省"
        ))

        XCTAssertEqual(location.city, "浙江省")
        XCTAssertEqual(location.district, "余杭区")
    }

    func testDuplicateLocalityIsNotPresentedAsDistrict() throws {
        let location = try XCTUnwrap(ResolvedLocation.resolve(
            subLocality: "北京市",
            locality: "北京市",
            administrativeArea: "北京市"
        ))

        XCTAssertEqual(location.city, "北京市")
        XCTAssertEqual(location.district, "")
        XCTAssertEqual(location.displayName, "北京市")
    }
}
