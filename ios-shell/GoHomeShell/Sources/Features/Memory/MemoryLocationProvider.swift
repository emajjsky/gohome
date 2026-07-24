import CoreLocation
import Foundation

@MainActor
final class MemoryLocationProvider: NSObject, ObservableObject, @preconcurrency CLLocationManagerDelegate {
    @Published private(set) var placeName: String?
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

        geocoder.reverseGeocodeLocation(location, preferredLocale: Locale(identifier: "zh_CN")) { [weak self] placemarks, error in
            Task { @MainActor in
                guard let self else { return }
                guard error == nil, let placemark = placemarks?.first else {
                    self.finishWithError("位置名称获取失败")
                    return
                }
                let components = [placemark.subLocality, placemark.locality, placemark.administrativeArea]
                    .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
                    .filter { !$0.isEmpty }
                    .reduce(into: [String]()) { result, value in
                        if !result.contains(value) { result.append(value) }
                    }
                guard !components.isEmpty else {
                    self.finishWithError("位置名称获取失败")
                    return
                }
                self.placeName = components.prefix(2).joined(separator: " · ")
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
