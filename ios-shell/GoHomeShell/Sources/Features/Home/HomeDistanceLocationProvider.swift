import CoreLocation
import Foundation

@MainActor
final class HomeDistanceLocationProvider: NSObject, ObservableObject, @preconcurrency CLLocationManagerDelegate {
    @Published private(set) var state: HomeDistanceState = .homeRequired

    private let manager = CLLocationManager()
    private var homeLocation: HomeLocation?

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
    }

    func update(home: HomeLocation?) {
        guard home != homeLocation else { return }
        homeLocation = home
        guard home != nil else {
            state = .homeRequired
            return
        }
        requestPhoneLocation()
    }

    private func requestPhoneLocation() {
        switch manager.authorizationStatus {
        case .notDetermined:
            state = .permissionRequired
            manager.requestWhenInUseAuthorization()
        case .authorizedAlways, .authorizedWhenInUse:
            manager.requestLocation()
        case .denied, .restricted:
            state = .permissionRequired
        @unknown default:
            state = .permissionRequired
        }
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        guard homeLocation != nil else { return }
        requestPhoneLocation()
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let phone = locations.last, let homeLocation else { return }
        let home = CLLocation(latitude: homeLocation.latitude, longitude: homeLocation.longitude)
        state = .value(
            kilometers: max(0, phone.distance(from: home)) / 1_000,
            travelMinutes: nil,
            user: HomeMapPoint(latitude: phone.coordinate.latitude, longitude: phone.coordinate.longitude),
            home: HomeMapPoint(latitude: homeLocation.latitude, longitude: homeLocation.longitude)
        )
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        state = homeLocation == nil ? .homeRequired : .permissionRequired
    }
}
