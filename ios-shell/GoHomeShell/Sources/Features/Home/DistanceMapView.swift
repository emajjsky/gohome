import MapKit
import SwiftUI

struct DistanceMapView: View {
    let state: HomeDistanceState

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            GoHomeSectionHeader(title: "回家距离")
            switch state {
            case let .value(kilometers, travelMinutes, user, home):
                if let user, let home {
                    HomeRouteMap(user: user, home: home)
                        .frame(height: 148)
                        .clipShape(RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
                        .allowsHitTesting(false)
                } else {
                    RouteBand()
                }
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(kilometers.formatted(.number.precision(.fractionLength(kilometers < 10 ? 1 : 0))))
                        .font(.system(size: 28, weight: .bold, design: .rounded))
                    Text("公里")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                    Spacer()
                    if let travelMinutes {
                        Label("约 \(travelMinutes) 分钟", systemImage: "car.fill")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(GoHomeTheme.mutedInk)
                    }
                }
            case .permissionRequired:
                RouteBand()
                Label("开启位置后查看回家距离", systemImage: "location")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
        }
        .accessibilityIdentifier("home-distance")
    }
}

private struct RouteBand: View {
    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: "location.fill")
                .foregroundStyle(GoHomeTheme.ginger)
            Rectangle()
                .fill(GoHomeTheme.line)
                .frame(height: 1)
                .overlay {
                    HStack(spacing: 5) {
                        ForEach(0..<7, id: \.self) { _ in
                            Circle().fill(GoHomeTheme.ginger.opacity(0.65)).frame(width: 3, height: 3)
                        }
                    }
                }
            Image(systemName: "house.fill")
                .foregroundStyle(GoHomeTheme.ink)
        }
        .padding(.horizontal, 18)
        .frame(height: 72)
        .background(GoHomeTheme.paleGinger.opacity(0.55), in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
    }
}

private struct HomeRouteMap: View {
    struct Point: Identifiable {
        let id: String
        let coordinate: CLLocationCoordinate2D
        let color: Color
    }

    @State private var region: MKCoordinateRegion
    let points: [Point]

    init(user: HomeMapPoint, home: HomeMapPoint) {
        let userCoordinate = CLLocationCoordinate2D(latitude: user.latitude, longitude: user.longitude)
        let homeCoordinate = CLLocationCoordinate2D(latitude: home.latitude, longitude: home.longitude)
        let center = CLLocationCoordinate2D(
            latitude: (user.latitude + home.latitude) / 2,
            longitude: (user.longitude + home.longitude) / 2
        )
        let span = MKCoordinateSpan(
            latitudeDelta: max(abs(user.latitude - home.latitude) * 1.8, 0.03),
            longitudeDelta: max(abs(user.longitude - home.longitude) * 1.8, 0.03)
        )
        _region = State(initialValue: MKCoordinateRegion(center: center, span: span))
        points = [
            Point(id: "user", coordinate: userCoordinate, color: GoHomeTheme.ginger),
            Point(id: "home", coordinate: homeCoordinate, color: GoHomeTheme.ink),
        ]
    }

    var body: some View {
        Map(coordinateRegion: $region, annotationItems: points) { point in
            MapMarker(coordinate: point.coordinate, tint: point.color)
        }
    }
}
