import SwiftUI

struct ActivityDataSettingsView: View {
    @ObservedObject var model: ProfileViewModel
    private let retentionOptions = [7, 14, 30, 90, 180, 365]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                HStack(spacing: 10) {
                    Image(systemName: model.canEditRules ? "checkmark.shield.fill" : "lock.fill")
                    Text(model.canEditRules ? "家庭创建者可调整" : "当前账号仅可查看")
                        .font(.system(size: 13, weight: .semibold))
                }
                .foregroundStyle(GoHomeTheme.mutedInk)

                if let preferences = model.state.value?.carePreferences {
                    let settings = preferences.metadata.activityHistory
                    ProfileSection(title: "活动记录") {
                        settingToggle("记录活动轨迹", symbol: "point.topleft.down.to.point.bottomright.curvepath", value: settings.trackingEnabled) { enabled in
                            update(preferences, value: enabled) { $0.trackingEnabled = $1 }
                        }
                        HStack {
                            Label("保留时间", systemImage: "calendar.badge.clock")
                                .font(.system(size: 15, weight: .semibold))
                                .foregroundStyle(GoHomeTheme.ink)
                            Spacer()
                            Picker("保留时间", selection: retentionBinding(preferences)) {
                                ForEach(retentionOptions, id: \.self) { days in
                                    Text("\(days) 天").tag(days)
                                }
                            }
                            .labelsHidden()
                            .tint(GoHomeTheme.ink)
                            .disabled(!model.canEditRules || model.savingPreferences)
                        }
                        .frame(minHeight: 50)
                    }
                } else {
                    ProfileEmptyRow(symbol: "chart.xyaxis.line", title: "活动数据设置暂不可用")
                }

                if let error = model.inlineError {
                    Label(error, systemImage: "exclamationmark.circle")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 18)
            .padding(.bottom, 28)
        }
        .background(GoHomeTheme.paper)
        .profileNavigationTitle("活动数据与报告")
    }

    private func settingToggle(
        _ title: String,
        symbol: String,
        value: Bool,
        update: @escaping (Bool) -> Void
    ) -> some View {
        Toggle(isOn: Binding(get: { value }, set: update)) {
            Label(title, systemImage: symbol)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(GoHomeTheme.ink)
        }
        .tint(GoHomeTheme.ginger)
        .frame(minHeight: 50)
        .disabled(!model.canEditRules || model.savingPreferences)
    }

    private func update(
        _ preferences: CarePreferences,
        value: Bool,
        mutation: (inout ActivityHistorySettings, Bool) -> Void
    ) {
        var next = preferences
        mutation(&next.metadata.activityHistory, value)
        model.savePreferences(next)
    }

    private func retentionBinding(_ preferences: CarePreferences) -> Binding<Int> {
        Binding(
            get: { preferences.metadata.activityHistory.retentionDays },
            set: { days in
                guard model.canEditRules, !model.savingPreferences else { return }
                var next = preferences
                next.metadata.activityHistory.retentionDays = days
                model.savePreferences(next)
            }
        )
    }
}
