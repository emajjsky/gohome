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
    private var requestStartedAt: Date?
    private var requestID: UUID?
    private var timeoutTask: Task<Void, Never>?

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyNearestTenMeters
    }

    func requestLocation() {
        timeoutTask?.cancel()
        manager.stopUpdatingLocation()
        geocoder.cancelGeocode()
        errorMessage = nil
        placeName = nil
        resolvedLocation = nil
        coordinate = nil
        requestStartedAt = nil
        requestID = UUID()

        switch manager.authorizationStatus {
        case .notDetermined:
            isLocating = true
            manager.requestWhenInUseAuthorization()
        case .authorizedAlways, .authorizedWhenInUse:
            isLocating = true
            beginLocationUpdates()
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
            beginLocationUpdates()
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
        guard isLocating, let requestStartedAt, let requestID else { return }
        guard let location = locations.reversed().first(where: {
            LocationSamplePolicy.accepts($0, requestedAt: requestStartedAt)
        }) else { return }
        manager.stopUpdatingLocation()
        timeoutTask?.cancel()
        self.requestStartedAt = nil
        coordinate = location.coordinate
        isLocating = false
        errorMessage = nil

        geocoder.reverseGeocodeLocation(location, preferredLocale: Locale(identifier: "zh_CN")) { [weak self] placemarks, error in
            Task { @MainActor in
                guard let self, self.requestID == requestID else { return }
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
                self.requestID = nil
            }
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        if (error as? CLError)?.code == .locationUnknown { return }
        finishWithError("暂时无法获取位置")
    }

    private func beginLocationUpdates() {
        requestStartedAt = Date()
        manager.startUpdatingLocation()
        timeoutTask?.cancel()
        timeoutTask = Task { [weak self] in
            do {
                try await Task.sleep(nanoseconds: 12_000_000_000)
            } catch {
                return
            }
            guard let self, self.isLocating, self.coordinate == nil else { return }
            self.finishWithError("没有取得可用的新位置，请移到窗边后重试")
        }
    }

    private func finishWithError(_ message: String) {
        manager.stopUpdatingLocation()
        timeoutTask?.cancel()
        requestStartedAt = nil
        requestID = nil
        isLocating = false
        errorMessage = message
    }
}
