import SwiftUI

struct HomeView: View {
    @ObservedObject var model: HomeViewModel
    @StateObject private var distanceProvider = HomeDistanceLocationProvider()
    let apiClient: APIClient?
    let onOpenAlert: (String) -> Void
    private let referenceDate: Date

    init(
        model: HomeViewModel,
        apiClient: APIClient? = nil,
        referenceDate: Date = Date(),
        onOpenAlert: @escaping (String) -> Void = { _ in }
    ) {
        self.model = model
        self.apiClient = apiClient
        self.referenceDate = referenceDate
        self.onOpenAlert = onOpenAlert
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                if let alert = HomePresentation.activeAlert(model.state.value?.criticalAlert) {
                    CriticalAlertStrip(alert: alert) { onOpenAlert(alert.id) }
                }
                if let message = model.careMessage {
                    CareMessageCard(message: message, model: model)
                } else {
                    ContextTopicCard(suggestion: HomePresentation.contextualTopic(model.state.value))
                }
                EditorialFeed(articles: model.state.value?.articles ?? [], apiBaseURL: apiClient?.baseURL)
                CalendarStripView(
                    days: HomePresentation.calendarDays(reference: referenceDate),
                    nextEvent: model.state.value?.calendar.first
                )
                DistanceMapView(state: distanceProvider.state)
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
        .onAppear { distanceProvider.update(home: model.state.value?.homeLocation) }
        .onChange(of: model.state.value?.homeLocation) { location in
            distanceProvider.update(home: location)
        }
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 7) {
                Text(dateText)
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(GoHomeTheme.ginger)
                Text("今天")
                    .font(.system(size: 28, weight: .bold, design: .rounded))
                    .foregroundStyle(GoHomeTheme.ink)
                if let weather = HomePresentation.weatherText(model.state.value?.weather) {
                    Text(weather)
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
            }
            Spacer()
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
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 11) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(GoHomeTheme.ginger)
                Text(alert.title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.ink)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(.vertical, 12)
        .overlay(alignment: .bottom) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
        .accessibilityLabel(alert.title)
        .accessibilityHint("查看事件证据")
        .accessibilityIdentifier("home-critical-alert")
    }
}
