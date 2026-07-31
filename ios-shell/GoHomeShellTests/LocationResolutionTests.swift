import XCTest
import CoreLocation
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

    func testLocationSampleRejectsCoordinatesFromBeforeTheCurrentRequest() {
        let requestedAt = Date(timeIntervalSince1970: 1_000)
        let stale = CLLocation(
            coordinate: CLLocationCoordinate2D(latitude: 31.2304, longitude: 121.4737),
            altitude: 0,
            horizontalAccuracy: 20,
            verticalAccuracy: 20,
            timestamp: requestedAt.addingTimeInterval(-60)
        )

        XCTAssertFalse(LocationSamplePolicy.accepts(stale, requestedAt: requestedAt, now: requestedAt))

        let justBeforeRequest = CLLocation(
            coordinate: CLLocationCoordinate2D(latitude: 31.2304, longitude: 121.4737),
            altitude: 0,
            horizontalAccuracy: 20,
            verticalAccuracy: 20,
            timestamp: requestedAt.addingTimeInterval(-0.1)
        )
        XCTAssertFalse(LocationSamplePolicy.accepts(justBeforeRequest, requestedAt: requestedAt, now: requestedAt))
    }

    func testLocationSampleRequiresUsefulAccuracyAndAcceptsFreshCoordinates() {
        let requestedAt = Date(timeIntervalSince1970: 1_000)
        let inaccurate = CLLocation(
            coordinate: CLLocationCoordinate2D(latitude: 31.2304, longitude: 121.4737),
            altitude: 0,
            horizontalAccuracy: 500,
            verticalAccuracy: 20,
            timestamp: requestedAt.addingTimeInterval(1)
        )
        let fresh = CLLocation(
            coordinate: CLLocationCoordinate2D(latitude: 31.2304, longitude: 121.4737),
            altitude: 0,
            horizontalAccuracy: 30,
            verticalAccuracy: 20,
            timestamp: requestedAt.addingTimeInterval(1)
        )

        XCTAssertFalse(LocationSamplePolicy.accepts(inaccurate, requestedAt: requestedAt, now: requestedAt.addingTimeInterval(2)))
        XCTAssertTrue(LocationSamplePolicy.accepts(fresh, requestedAt: requestedAt, now: requestedAt.addingTimeInterval(2)))
    }
}
