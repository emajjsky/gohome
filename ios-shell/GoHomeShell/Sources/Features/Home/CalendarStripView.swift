import SwiftUI

struct CalendarStripView: View {
    let days: [HomeCalendarDay]
    let nextEvent: HomeCalendarEvent?
    @State private var selectedEvent: HomeCalendarEvent?

    var body: some View {
        Group {
            if let nextEvent {
                Button { selectedEvent = nextEvent } label: { content }
                    .buttonStyle(.plain)
                    .accessibilityHint("查看日程详情")
            } else {
                content
            }
        }
        .sheet(item: $selectedEvent) { event in
            CalendarEventDetail(event: event)
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("home-calendar")
    }

    private var content: some View {
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
                    .frame(height: 52)
                    .background(
                        item.isToday ? GoHomeTheme.ink : GoHomeTheme.softLine,
                        in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous)
                    )
                }
            }
        }
    }
}

private struct CalendarEventDetail: View {
    @Environment(\.dismiss) private var dismiss
    let event: HomeCalendarEvent

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 18) {
                Image(systemName: "calendar")
                    .font(.system(size: 28, weight: .medium))
                    .foregroundStyle(GoHomeTheme.ginger)
                Text(event.title)
                    .font(.system(size: 24, weight: .bold, design: .rounded))
                    .foregroundStyle(GoHomeTheme.ink)
                Label(eventDateText, systemImage: "clock")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.mutedInk)
                Spacer()
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 24)
            .background(GoHomeTheme.paper)
            .navigationTitle("日程")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button { dismiss() } label: { Image(systemName: "xmark") }
                        .accessibilityLabel("关闭")
                }
            }
        }
        .presentationDetents([.medium])
    }

    private var eventDateText: String {
        let formatter = ISO8601DateFormatter()
        guard let date = formatter.date(from: event.startsAt) else { return event.startsAt }
        return date.formatted(date: .long, time: .shortened)
    }
}
