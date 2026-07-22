import SwiftUI

struct HomeView: View {
    @ObservedObject var model: HomeViewModel
    let unreadCount: Int
    private let referenceDate: Date

    init(model: HomeViewModel, unreadCount: Int, referenceDate: Date = Date()) {
        self.model = model
        self.unreadCount = unreadCount
        self.referenceDate = referenceDate
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                header
                if let alert = HomePresentation.activeAlert(model.state.value?.criticalAlert) {
                    CriticalAlertStrip(alert: alert)
                }
                CalendarStripView(
                    days: HomePresentation.calendarDays(reference: referenceDate),
                    nextEvent: model.state.value?.calendar.first
                )
                DistanceMapView(state: HomePresentation.distanceState(model.state.value?.distance))
                EditorialFeed(articles: model.state.value?.articles ?? [])
                if let staleReason = model.state.staleReason, model.state.value != nil {
                    Text(staleReason)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 18)
            .padding(.bottom, 28)
        }
        .background(GoHomeTheme.paper)
        .accessibilityIdentifier("home-content-anchor")
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 7) {
                Text(dateText)
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(GoHomeTheme.ginger)
                Text("今天")
                    .font(.system(size: 32, weight: .bold, design: .rounded))
                    .foregroundStyle(GoHomeTheme.ink)
                if let weather = HomePresentation.weatherText(model.state.value?.weather) {
                    Text(weather)
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
            }
            Spacer()
            if unreadCount > 0 {
                Text("\(min(unreadCount, 99))")
                    .font(.system(size: 12, weight: .bold, design: .rounded))
                    .foregroundStyle(GoHomeTheme.ink)
                    .frame(minWidth: 30, minHeight: 30)
                    .background(GoHomeTheme.ginger, in: Circle())
                    .accessibilityLabel("\(unreadCount) 条未读消息")
            }
        }
    }

    private var dateText: String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.dateFormat = "M月d日 EEEE"
        return formatter.string(from: referenceDate)
    }

}

private struct CriticalAlertStrip: View {
    let alert: HomeCriticalAlert

    var body: some View {
        HStack(spacing: 11) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(GoHomeTheme.ginger)
            Text(alert.title)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(GoHomeTheme.ink)
                .lineLimit(2)
            Spacer()
            Image(systemName: "chevron.right")
                .font(.caption.weight(.bold))
                .foregroundStyle(GoHomeTheme.mutedInk)
        }
        .padding(.vertical, 12)
        .overlay(alignment: .bottom) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
        .accessibilityIdentifier("home-critical-alert")
    }
}
