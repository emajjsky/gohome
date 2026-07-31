import CoreLocation
import Foundation

enum LocationSamplePolicy {
    static let maximumAge: TimeInterval = 15
    static let maximumHorizontalAccuracy: CLLocationAccuracy = 200

    static func accepts(_ location: CLLocation, requestedAt: Date, now: Date = Date()) -> Bool {
        let age = now.timeIntervalSince(location.timestamp)
        return location.horizontalAccuracy >= 0
            && location.horizontalAccuracy <= maximumHorizontalAccuracy
            && age >= -5
            && age <= maximumAge
            && location.timestamp >= requestedAt
    }
}
