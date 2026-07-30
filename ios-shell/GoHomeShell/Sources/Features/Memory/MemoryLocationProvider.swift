import CoreLocation
import Foundation

struct ResolvedLocation: Equatable, Sendable {
    let city: String
    let district: String

    var displayName: String {
        [district, city].filter { !$0.isEmpty }.joined(separator: " · ")
    }

    static func resolve(subLocality: String?, locality: String?, administrativeArea: String?) -> ResolvedLocation? {
        let district = normalized(subLocality)
        let locality = normalized(locality)
        let administrativeArea = normalized(administrativeArea)
        let city = locality ?? administrativeArea ?? ""
        let resolvedDistrict = district == city ? "" : district ?? ""
        guard !city.isEmpty || !resolvedDistrict.isEmpty else { return nil }
        return ResolvedLocation(city: city, district: resolvedDistrict)
    }

    private static func normalized(_ value: String?) -> String? {
        let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return trimmed.isEmpty ? nil : trimmed
    }
}

@MainActor
final class MemoryLocationProvider: NSObject, ObservableObject, @preconcurrency CLLocationManagerDelegate {
    @Published private(set) var placeName: String?
    @Published private(set) var resolvedLocation: ResolvedLocation?
    @Published private(set) var coordinate: CLLocationCoordinate2D?
    @Published private(set) var isLocating = false
    @Published private(set) var errorMessage: String?

    private let manager = CLLocationManager()
    private let geocoder = CLGeocoder()

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
    }

    func requestLocation() {
        errorMessage = nil
        placeName = nil
        resolvedLocation = nil
        coordinate = nil

        switch manager.authorizationStatus {
        case .notDetermined:
            isLocating = true
            manager.requestWhenInUseAuthorization()
        case .authorizedAlways, .authorizedWhenInUse:
            isLocating = true
            manager.requestLocation()
        case .denied, .restricted:
            isLocating = false
            errorMessage = "请在系统设置中开启位置权限"
        @unknown default:
            isLocating = false
            errorMessage = "暂时无法获取位置"
        }
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        switch manager.authorizationStatus {
        case .authorizedAlways, .authorizedWhenInUse:
            guard isLocating else { return }
            manager.requestLocation()
        case .denied, .restricted:
            isLocating = false
            errorMessage = "请在系统设置中开启位置权限"
        case .notDetermined:
            break
        @unknown default:
            isLocating = false
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else {
            finishWithError("暂时无法获取位置")
            return
        }
        coordinate = location.coordinate

        geocoder.reverseGeocodeLocation(location, preferredLocale: Locale(identifier: "zh_CN")) { [weak self] placemarks, error in
            Task { @MainActor in
                guard let self else { return }
                guard error == nil, let placemark = placemarks?.first else {
                    self.finishWithError("位置名称获取失败")
                    return
                }
                guard let location = ResolvedLocation.resolve(
                    subLocality: placemark.subLocality,
                    locality: placemark.locality,
                    administrativeArea: placemark.administrativeArea
                ) else {
                    self.finishWithError("位置名称获取失败")
                    return
                }
                self.resolvedLocation = location
                self.placeName = location.displayName
                self.isLocating = false
                self.errorMessage = nil
            }
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        finishWithError("暂时无法获取位置")
    }

    private func finishWithError(_ message: String) {
        isLocating = false
        errorMessage = message
    }
}
