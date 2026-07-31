import CoreLocation
import Foundation

@MainActor
final class HomeDistanceLocationProvider: NSObject, ObservableObject, @preconcurrency CLLocationManagerDelegate {
    @Published private(set) var state: HomeDistanceState = .homeRequired

    private let manager = CLLocationManager()
    private var homeLocation: HomeLocation?
    private var requestStartedAt: Date?
    private var timeoutTask: Task<Void, Never>?

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyNearestTenMeters
    }

    func update(home: HomeLocation?) {
        let didChange = home != homeLocation
        homeLocation = home
        guard home != nil else {
            stopLocationRequest()
            state = .homeRequired
            return
        }
        if didChange { stopLocationRequest() }
        requestPhoneLocation()
    }

    private func requestPhoneLocation() {
        switch manager.authorizationStatus {
        case .notDetermined:
            state = .permissionRequired
            manager.requestWhenInUseAuthorization()
        case .authorizedAlways, .authorizedWhenInUse:
            beginLocationRequest()
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
        guard let requestedAt = requestStartedAt, let homeLocation else { return }
        guard let phone = locations.reversed().first(where: {
            LocationSamplePolicy.accepts($0, requestedAt: requestedAt)
        }) else { return }
        stopLocationRequest()
        let home = CLLocation(latitude: homeLocation.latitude, longitude: homeLocation.longitude)
        state = .value(
            kilometers: max(0, phone.distance(from: home)) / 1_000,
            travelMinutes: nil,
            user: HomeMapPoint(latitude: phone.coordinate.latitude, longitude: phone.coordinate.longitude),
            home: HomeMapPoint(latitude: homeLocation.latitude, longitude: homeLocation.longitude)
        )
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        if (error as? CLError)?.code == .locationUnknown { return }
        stopLocationRequest()
        state = homeLocation == nil ? .homeRequired : .permissionRequired
    }

    private func beginLocationRequest() {
        guard requestStartedAt == nil else { return }
        requestStartedAt = Date()
        manager.startUpdatingLocation()
        timeoutTask?.cancel()
        timeoutTask = Task { [weak self] in
            do {
                try await Task.sleep(nanoseconds: 12_000_000_000)
            } catch {
                return
            }
            guard let self, self.requestStartedAt != nil else { return }
            self.stopLocationRequest()
            self.state = self.homeLocation == nil ? .homeRequired : .permissionRequired
        }
    }

    private func stopLocationRequest() {
        manager.stopUpdatingLocation()
        timeoutTask?.cancel()
        timeoutTask = nil
        requestStartedAt = nil
    }
}
