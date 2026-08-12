import SwiftUI

private func parseHomeReturnPlanDate(_ value: String) -> Date? {
    let fractional = ISO8601DateFormatter()
    fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return fractional.date(from: value) ?? ISO8601DateFormatter().date(from: value)
}

struct HomeView: View {
    @ObservedObject var model: HomeViewModel
    @StateObject private var distanceProvider = HomeDistanceLocationProvider()
    @State private var showingReturnPlanEditor = false
    let apiClient: APIClient?
    let onSetHomeLocation: (() -> Void)?
    let onOpenAlert: (String) -> Void
    private let referenceDate: Date

    init(
        model: HomeViewModel,
        apiClient: APIClient? = nil,
        referenceDate: Date = Date(),
        onSetHomeLocation: (() -> Void)? = nil,
        onOpenAlert: @escaping (String) -> Void = { _ in }
    ) {
        self.model = model
        self.apiClient = apiClient
        self.referenceDate = referenceDate
        self.onSetHomeLocation = onSetHomeLocation
        self.onOpenAlert = onOpenAlert
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                welcomeHero
                DistanceMapView(state: distanceProvider.state, onSetHomeLocation: onSetHomeLocation)
                returnHomeSummary
                returnPlanSection
                weatherCard
                if let message = model.careMessage {
                    CareMessageCard(message: message, model: model)
                } else {
                    ContextTopicCard(suggestion: HomePresentation.contextualTopic(model.state.value))
                }
                EditorialFeed(articles: model.state.value?.articles ?? [], apiBaseURL: apiClient?.baseURL)
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
        .task { model.start() }
        .onAppear { distanceProvider.update(home: model.state.value?.homeLocation) }
        .onChange(of: model.state.value?.homeLocation) { location in
            distanceProvider.update(home: location)
        }
        .onDisappear {
            model.cancelInFlightLoad()
            model.cancelInFlightCareAction()
        }
        .sheet(isPresented: $showingReturnPlanEditor) {
            ReturnHomePlanEditor(model: model, plan: model.state.value?.returnPlan)
        }
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 7) {
                Text(dateText)
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(GoHomeTheme.leaf)
                Text("今天")
                    .font(.system(size: 28, weight: .bold, design: .rounded))
                    .foregroundStyle(GoHomeTheme.ink)
                Text(HomePresentation.weatherText(model.state.value?.weather) ?? "家庭状态与天气")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
            Spacer()
        }
    }

    private var welcomeHero: some View {
        GeometryReader { proxy in
            ZStack(alignment: .bottomLeading) {
                GoHomeLocalImage(name: heroImageName)
                    .frame(width: proxy.size.width, height: proxy.size.height, alignment: .top)
                    .clipped()
                Rectangle()
                    .fill(Color.black.opacity(0.30))
                    .frame(width: proxy.size.width, height: proxy.size.height)
                VStack(alignment: .leading, spacing: 5) {
                    Label("家庭状态", systemImage: "house.fill")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(Color.white.opacity(0.86))
                    Text("今天，也有人在牵挂")
                        .font(.system(size: 22, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)
                    Text("看看家里的近况，留一点时间给彼此")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(Color.white.opacity(0.86))
                }
                .padding(16)
            }
            .frame(width: proxy.size.width, height: proxy.size.height, alignment: .bottomLeading)
        }
        .frame(maxWidth: .infinity)
        .frame(height: 220)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("家庭状态，今天也有人在牵挂")
    }

    private var dateText: String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.dateFormat = "M月d日 EEEE"
        return formatter.string(from: referenceDate)
    }

    private var heroImageName: String {
        let catalog = [
            "memory-family-dinner",
            "memory-daughter-walk",
            "memory-garden-sun",
            "memory-generations",
            "memory-outdoor-walk",
            "memory-relax-chat",
        ]
        let day = Calendar(identifier: .gregorian).ordinality(of: .day, in: .year, for: referenceDate) ?? 0
        return catalog[abs(day) % catalog.count]
    }

    private var weatherCard: some View {
        Group {
            if let weather = model.state.value?.weather {
                VStack(alignment: .leading, spacing: 14) {
                    HStack(alignment: .top, spacing: 14) {
                        Image(systemName: weatherSymbol(weather.condition))
                            .font(.system(size: 26, weight: .semibold))
                            .foregroundStyle(GoHomeTheme.leaf)
                            .frame(width: 48, height: 48)
                            .background(GoHomeTheme.paleLeaf, in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
                        VStack(alignment: .leading, spacing: 4) {
                            Text(weather.city.isEmpty ? "家庭所在地" : weather.city)
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundStyle(GoHomeTheme.mutedInk)
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                Text(weather.temperature.formatted(.number.precision(.fractionLength(0))))
                                    .font(.system(size: 30, weight: .bold, design: .rounded))
                                    .foregroundStyle(GoHomeTheme.ink)
                                Text("°")
                                    .font(.system(size: 17, weight: .bold))
                                    .foregroundStyle(GoHomeTheme.mutedInk)
                                Text(weather.condition)
                                    .font(.system(size: 14, weight: .semibold))
                                    .foregroundStyle(GoHomeTheme.ink)
                            }
                        }
                        Spacer(minLength: 0)
                    }
                    HStack(spacing: 18) {
                        if let humidity = weather.humidity {
                            Label("湿度 \(humidity.formatted(.number.precision(.fractionLength(0))))%", systemImage: "drop.fill")
                        }
                        if !weather.wind.isEmpty {
                            Label(weather.wind, systemImage: "wind")
                        }
                        if !weather.advice.isEmpty {
                            Text(weather.advice).lineLimit(1)
                        }
                    }
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(GoHomeTheme.mutedInk)
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(GoHomeTheme.surface, in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
                .overlay { RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous).stroke(GoHomeTheme.softLine, lineWidth: 0.5) }
                .accessibilityIdentifier("home-weather")
            }
        }
    }

    @ViewBuilder
    private var returnHomeSummary: some View {
        if let status = model.state.value?.returnHome {
            HStack(spacing: 12) {
                Image(systemName: status.isAtHome ? "house.fill" : "clock.arrow.circlepath")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(status.isAtHome ? GoHomeTheme.leaf : GoHomeTheme.ginger)
                    .frame(width: 32, height: 32)
                    .background(
                        status.isAtHome ? GoHomeTheme.paleLeaf : GoHomeTheme.paleGinger,
                        in: Circle()
                    )
                VStack(alignment: .leading, spacing: 3) {
                    Text(status.isAtHome ? "已回到家" : "家庭近况")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(GoHomeTheme.ink)
                    if status.isAtHome {
                        Text("手机已连接家庭网络")
                    } else if let days = status.daysSinceLastVisit, days > 0 {
                        Text("距上次回家已 \(days) 天")
                    } else if status.daysSinceLastVisit == 0 {
                        Text("今天已记录回家")
                    } else {
                        Text("尚未记录最近一次回家时间")
                    }
                }
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(GoHomeTheme.mutedInk)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 14)
            .frame(minHeight: 58)
            .background(GoHomeTheme.surface, in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous)
                    .stroke(GoHomeTheme.softLine, lineWidth: 0.5)
            }
            .accessibilityIdentifier("home-return-home-status")
            if let message = model.homeVisitVerificationError {
                Text(message)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(GoHomeTheme.ginger)
            }
        }
    }

    private var returnPlanSection: some View {
        Button { showingReturnPlanEditor = true } label: {
            HStack(spacing: 12) {
                Image(systemName: "calendar.badge.plus")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.ginger)
                    .frame(width: 36, height: 36)
                    .background(GoHomeTheme.paleGinger, in: Circle())
                VStack(alignment: .leading, spacing: 4) {
                    Text("回家计划")
                        .font(.system(size: 14, weight: .bold))
                    if let plan = model.state.value?.returnPlan {
                        Text(returnPlanText(plan.startsAt))
                    } else {
                        Text("设置下一次回家的时间")
                    }
                }
                .foregroundStyle(GoHomeTheme.ink)
                Spacer(minLength: 0)
                Image(systemName: "chevron.right")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
            .padding(.horizontal, 14)
            .frame(minHeight: 62)
            .background(GoHomeTheme.surface, in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
            .overlay { RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius).stroke(GoHomeTheme.softLine, lineWidth: 0.5) }
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("home-return-plan")
    }

    private func returnPlanText(_ value: String) -> String {
        guard let date = parseHomeReturnPlanDate(value) else { return value }
        return date.formatted(
            Date.FormatStyle(date: .abbreviated, time: .shortened)
                .locale(Locale(identifier: "zh_CN"))
        )
    }

    private func weatherSymbol(_ condition: String) -> String {
        let value = condition.lowercased()
        if value.contains("雨") { return "cloud.rain.fill" }
        if value.contains("云") || value.contains("阴") { return "cloud.fill" }
        if value.contains("雾") { return "cloud.fog.fill" }
        if value.contains("雷") { return "cloud.bolt.rain.fill" }
        return "sun.max.fill"
    }

}

private struct ReturnHomePlanEditor: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var model: HomeViewModel
    let plan: HomeReturnPlan?
    @State private var date: Date
    @State private var note: String

    init(model: HomeViewModel, plan: HomeReturnPlan?) {
        self.model = model
        self.plan = plan
        let parsed = plan.flatMap { parseHomeReturnPlanDate($0.startsAt) }
        _date = State(initialValue: parsed ?? Date().addingTimeInterval(7 * 86_400))
        _note = State(initialValue: plan?.note ?? "")
    }

    var body: some View {
        NavigationStack {
            Form {
                DatePicker("回家时间", selection: $date, in: Date()..., displayedComponents: [.date, .hourAndMinute])
                TextField("备注（可选）", text: $note, axis: .vertical)
                    .lineLimit(2...4)
                if let error = model.returnPlanError {
                    Text(error).foregroundStyle(.red)
                }
                if plan != nil {
                    Button("取消回家计划", role: .destructive) {
                        Task { if await model.cancelReturnPlan() { dismiss() } }
                    }
                }
            }
            .navigationTitle(plan == nil ? "设置回家计划" : "修改回家计划")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("保存") {
                        Task { if await model.saveReturnPlan(date: date, note: note) { dismiss() } }
                    }
                    .disabled(model.isSavingReturnPlan)
                }
            }
        }
    }
}
