import SwiftUI

struct ActivityTimelineView: View {
    @ObservedObject var model: ActivityTimelineViewModel
    @State private var confirmingClear = false

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            if let overview = model.overviewState.value,
               overview.today.hasData || overview.sevenDayTrend.contains(where: { $0.hasData }) {
                ActivityOverviewHeader(overview: overview)
                if let attentionItems = overview.attentionItems, !attentionItems.isEmpty {
                    ActivityAttentionSection(items: attentionItems)
                }
            }
            if model.state.value == nil {
                Color.clear
                    .frame(height: 96)
                    .overlay(alignment: .top) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
                    .accessibilityHidden(true)
            } else if let intervals = model.state.value?.intervals, !intervals.isEmpty {
                LazyVStack(alignment: .leading, spacing: 0) {
                    ForEach(intervals) { interval in
                        ActivityTimelineRow(interval: interval)
                    }
                }
            } else {
                emptyState
            }
            if model.canManageHistory, hasHistory {
                Button(role: .destructive) { confirmingClear = true } label: {
                    Label(model.clearingHistory ? "正在清空" : "清空活动记录", systemImage: "trash")
                        .font(.system(size: 13, weight: .semibold))
                }
                .disabled(model.clearingHistory)
            }
            if let actionError = model.actionError {
                Label(actionError, systemImage: "exclamationmark.circle")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("activity-timeline-content")
        .overlay(alignment: .bottomLeading) {
            if let reason = model.state.staleReason, model.state.value != nil {
                Label(reason, systemImage: "wifi.exclamationmark")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(GoHomeTheme.mutedInk)
                    .offset(y: 24)
            }
        }
        .confirmationDialog("清空普通活动记录？", isPresented: $confirmingClear, titleVisibility: .visible) {
            Button("清空活动记录", role: .destructive) { model.clearHistory() }
            Button("取消", role: .cancel) {}
        } message: {
            Text("安全事件与告警证据不会被删除。")
        }
        .onDisappear { model.cancelInFlightClear() }
    }

    private var hasHistory: Bool {
        model.state.value?.intervals.isEmpty == false
            || (model.overviewState.value?.sevenDayTrend.contains { $0.hasData }) == true
    }

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: 14) {
            Image(systemName: "point.topleft.down.to.point.bottomright.curvepath")
                .font(.system(size: 26, weight: .medium))
                .foregroundStyle(GoHomeTheme.ginger)
            Text("今日还没有活动轨迹")
                .font(.system(size: 18, weight: .bold))
                .foregroundStyle(GoHomeTheme.ink)
            Text("轨迹只记录房间、时间和可验证的活动区间，不根据一次出现推断吃饭、睡眠或健康状态。")
                .font(.system(size: 13))
                .foregroundStyle(GoHomeTheme.mutedInk)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 28)
        .overlay(alignment: .top) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
        .accessibilityIdentifier("guard-timeline-empty")
    }
}

private struct ActivityOverviewHeader: View {
    let overview: ActivityOverviewResponse

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("今日活动")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                    Text("\(overview.today.activeMinutes) 分钟")
                        .font(.system(size: 26, weight: .bold, design: .rounded))
                        .foregroundStyle(GoHomeTheme.ink)
                }
                Spacer()
                if let room = overview.today.rooms.first {
                    VStack(alignment: .trailing, spacing: 3) {
                        Text("主要区域")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(GoHomeTheme.mutedInk)
                        Text(room.room)
                            .font(.system(size: 15, weight: .bold))
                            .foregroundStyle(GoHomeTheme.ink)
                    }
                }
            }
            ActivityWeekTrend(days: overview.sevenDayTrend)
            if let quality = overview.dataQuality,
               quality.hasTodayActivity,
               !quality.canCompareRoutine {
                Text("规律建立中 · 已有 \(quality.comparableDays) 个可比较日")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            } else if let quality = overview.dataQuality,
                      quality.canCompareRoutine,
                      quality.activityDurationComparisonReady == false {
                Text("今日持续记录中 · 晚间再比较活动时长")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
            ForEach(overview.facts.prefix(2), id: \.self) { fact in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Circle().fill(GoHomeTheme.ginger).frame(width: 5, height: 5)
                    Text(fact)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
            }
        }
        .padding(.vertical, 18)
        .overlay(alignment: .top) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
        .overlay(alignment: .bottom) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
        .accessibilityIdentifier("activity-overview")
    }
}

private struct ActivityAttentionSection: View {
    let items: [ActivityAttentionItem]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 8) {
                Image(systemName: "waveform.path.ecg")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.ginger)
                Text("需要留意")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(GoHomeTheme.ink)
            }
            ForEach(items) { item in
                VStack(alignment: .leading, spacing: 8) {
                    Text(title(item.type))
                        .font(.system(size: 16, weight: .bold))
                        .foregroundStyle(GoHomeTheme.ink)
                    ForEach(item.facts.prefix(2), id: \.self) { fact in
                        Text(fact)
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(GoHomeTheme.mutedInk)
                    }
                    if !item.suggestedTopic.isEmpty {
                        Text(item.suggestedTopic)
                            .font(.system(size: 14, weight: .medium))
                            .foregroundStyle(GoHomeTheme.ink)
                            .padding(.top, 2)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.leading, 13)
                .overlay(alignment: .leading) {
                    Rectangle().fill(GoHomeTheme.ginger).frame(width: 2)
                }
            }
        }
        .padding(.vertical, 18)
        .overlay(alignment: .bottom) { Rectangle().fill(GoHomeTheme.line).frame(height: 1) }
        .accessibilityIdentifier("activity-attention-items")
    }

    private func title(_ type: String) -> String {
        switch type {
        case "night_activity": return "夜间活动"
        case "activity_reduced": return "活动比近期少"
        case "routine_shift": return "活动时间变化"
        default: return "活动变化"
        }
    }
}

private struct ActivityWeekTrend: View {
    let days: [ActivityDaySummary]

    var body: some View {
        let maximum = max(1, days.map(\.activeMinutes).max() ?? 1)
        HStack(alignment: .bottom, spacing: 8) {
            ForEach(days) { day in
                VStack(spacing: 6) {
                    Spacer(minLength: 0)
                    RoundedRectangle(cornerRadius: 2)
                        .fill(day.hasData ? GoHomeTheme.ginger : GoHomeTheme.softLine)
                        .frame(height: day.hasData ? max(4, 42 * CGFloat(day.activeMinutes) / CGFloat(maximum)) : 2)
                    Text(weekday(day.date))
                        .font(.system(size: 10, weight: .semibold, design: .rounded))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
                .frame(maxWidth: .infinity, minHeight: 62, maxHeight: 62)
            }
        }
    }

    private func weekday(_ date: String) -> String {
        guard let value = Self.dateFormatter.date(from: date) else { return "-" }
        return Self.weekdayFormatter.string(from: value)
    }

    private static let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "Asia/Shanghai")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()

    private static let weekdayFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.timeZone = TimeZone(identifier: "Asia/Shanghai")
        formatter.dateFormat = "EE"
        return formatter
    }()
}

private struct ActivityTimelineRow: View {
    let interval: ActivityInterval

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            VStack(spacing: 0) {
                Circle().fill(GoHomeTheme.ginger).frame(width: 9, height: 9)
                Rectangle().fill(GoHomeTheme.line).frame(width: 1).frame(minHeight: 58)
            }
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text(interval.room.isEmpty ? "监控区域" : interval.room)
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(GoHomeTheme.ink)
                    Spacer()
                    Text(timeRange)
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
                Text(activityDescription)
                    .font(.system(size: 13))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
            .padding(.bottom, 18)
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("activity-interval-\(interval.id)")
    }

    private var activityDescription: String {
        let people = interval.personCountMax > 1 ? "最多 \(interval.personCountMax) 人活动" : "有人活动"
        let postures = interval.postures.compactMap(postureLabel)
        return postures.isEmpty ? people : "\(people) · \(postures.joined(separator: "、"))"
    }

    private var timeRange: String {
        "\(time(interval.startedAt))–\(time(interval.endedAt))"
    }

    private func time(_ value: String) -> String {
        guard let date = ISO8601DateFormatter().date(from: value) else { return "--:--" }
        let formatter = DateFormatter()
        formatter.timeZone = TimeZone(identifier: "Asia/Shanghai")
        formatter.dateFormat = "HH:mm"
        return formatter.string(from: date)
    }

    private func postureLabel(_ value: String) -> String? {
        switch value.lowercased() {
        case "standing": return "站立"
        case "sitting": return "坐姿"
        case "squatting": return "蹲姿"
        case "bending": return "弯腰"
        case "lying": return "躺姿"
        case "upper_body": return "上半身可见"
        default: return nil
        }
    }
}
