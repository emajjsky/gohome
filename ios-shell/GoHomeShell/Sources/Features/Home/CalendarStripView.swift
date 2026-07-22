import SwiftUI

struct CalendarStripView: View {
    let days: [HomeCalendarDay]
    let nextEvent: HomeCalendarEvent?

    var body: some View {
        VStack(alignment: .leading, spacing: 15) {
            GoHomeSectionHeader(title: "接下来", detail: nextEvent?.title)
            HStack(spacing: 6) {
                ForEach(days) { item in
                    VStack(spacing: 8) {
                        Text(item.weekday)
                            .font(.system(size: 10, weight: .medium))
                        Text(item.day)
                            .font(.system(size: 15, weight: .bold, design: .rounded))
                    }
                    .foregroundStyle(item.isToday ? Color.white : GoHomeTheme.ink)
                    .frame(maxWidth: .infinity)
                    .frame(height: 58)
                    .background(
                        item.isToday ? GoHomeTheme.ink : GoHomeTheme.softLine,
                        in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous)
                    )
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("home-calendar")
    }
}
