import SwiftUI

struct ActivityTimelineView: View {
    @ObservedObject var model: ActivityTimelineViewModel

    var body: some View {
        Group {
            if let intervals = model.state.value?.intervals, !intervals.isEmpty {
                LazyVStack(alignment: .leading, spacing: 0) {
                    ForEach(intervals) { interval in
                        ActivityTimelineRow(interval: interval)
                    }
                }
            } else {
                emptyState
            }
        }
        .overlay(alignment: .bottomLeading) {
            if let reason = model.state.staleReason, model.state.value != nil {
                Label(reason, systemImage: "wifi.exclamationmark")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(GoHomeTheme.mutedInk)
                    .offset(y: 24)
            }
        }
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
