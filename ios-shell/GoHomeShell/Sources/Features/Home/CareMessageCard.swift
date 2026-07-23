import SwiftUI
import UIKit

struct CareMessageCard: View {
    let message: CareMessage
    @ObservedObject var model: HomeViewModel
    @State private var isEditorPresented = false

    var body: some View {
        Button {
            isEditorPresented = true
        } label: {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 8) {
                    Image(systemName: "bubble.left.and.text.bubble.right.fill")
                        .font(.system(size: 13, weight: .semibold))
                    Text("今日关怀")
                        .font(.system(size: 12, weight: .bold))
                    Spacer()
                    Image(systemName: "arrow.up.right")
                        .font(.system(size: 12, weight: .bold))
                }
                .foregroundStyle(GoHomeTheme.ginger)

                Text(message.title)
                    .font(.system(size: 20, weight: .bold))
                    .foregroundStyle(GoHomeTheme.ink)
                    .multilineTextAlignment(.leading)
                if !message.body.isEmpty {
                    Text(message.body)
                        .font(.system(size: 14, weight: .regular))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                }
                HStack(spacing: 7) {
                    ForEach(message.metadata.topics.prefix(3), id: \.self) { topic in
                        Text(topic)
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(GoHomeTheme.ink)
                            .padding(.horizontal, 9)
                            .padding(.vertical, 6)
                            .background(Color.white.opacity(0.7), in: Capsule())
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(18)
            .background(GoHomeTheme.paleGinger.opacity(0.72), in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("home-care-message")
        .sheet(isPresented: $isEditorPresented) {
            CareMessageEditor(message: message, model: model, isPresented: $isEditorPresented)
        }
    }
}

private struct CareMessageEditor: View {
    let message: CareMessage
    @ObservedObject var model: HomeViewModel
    @Binding var isPresented: Bool
    @State private var selectedTopic: String
    @State private var draft: String
    @State private var isSharePresented = false
    @State private var shareText = ""
    @State private var isSnoozeMenuPresented = false

    init(message: CareMessage, model: HomeViewModel, isPresented: Binding<Bool>) {
        self.message = message
        self.model = model
        _isPresented = isPresented
        let topic = message.metadata.topics.first ?? ""
        _selectedTopic = State(initialValue: topic)
        _draft = State(initialValue: message.metadata.messageVariants.first ?? message.body)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(message.title)
                            .font(.system(size: 24, weight: .bold))
                            .foregroundStyle(GoHomeTheme.ink)
                        if !message.subtitle.isEmpty {
                            Text(message.subtitle)
                                .font(.system(size: 13, weight: .medium))
                                .foregroundStyle(GoHomeTheme.mutedInk)
                        }
                    }

                    if !message.metadata.topics.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                ForEach(message.metadata.topics, id: \.self) { topic in
                                    Button(topic) {
                                        selectedTopic = topic
                                    }
                                    .font(.system(size: 13, weight: .semibold))
                                    .foregroundStyle(selectedTopic == topic ? Color.white : GoHomeTheme.ink)
                                    .padding(.horizontal, 13)
                                    .padding(.vertical, 8)
                                    .background(selectedTopic == topic ? GoHomeTheme.ink : GoHomeTheme.softLine, in: Capsule())
                                }
                            }
                        }
                    }

                    VStack(alignment: .leading, spacing: 10) {
                        Text("消息参考")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundStyle(GoHomeTheme.mutedInk)
                        TextEditor(text: $draft)
                            .font(.system(size: 17, weight: .regular))
                            .foregroundStyle(GoHomeTheme.ink)
                            .scrollContentBackground(.hidden)
                            .frame(minHeight: 150)
                            .padding(12)
                            .background(Color.black.opacity(0.035), in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
                    }

                    if let error = model.careActionError {
                        Text(error)
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(.red)
                    }

                    VStack(spacing: 10) {
                        Button {
                            shareText = draft.trimmingCharacters(in: .whitespacesAndNewlines)
                            isSharePresented = !shareText.isEmpty
                        } label: {
                            Label("选择发送方式", systemImage: "square.and.arrow.up")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(CarePrimaryButtonStyle())
                        .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || model.pendingCareAction != nil)

                        HStack(spacing: 8) {
                            actionButton("已联系", icon: "checkmark") { submit("contacted") }
                            actionButton("稍后", icon: "clock") { isSnoozeMenuPresented = true }
                            actionButton("忽略", icon: "xmark") { submit("dismissed") }
                        }
                    }
                }
                .padding(GoHomeTheme.pageHorizontalPadding)
            }
            .background(GoHomeTheme.paper)
            .navigationTitle("关怀建议")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("完成") { isPresented = false }
                        .foregroundStyle(GoHomeTheme.ink)
                }
            }
            .confirmationDialog("稍后提醒", isPresented: $isSnoozeMenuPresented, titleVisibility: .visible) {
                Button("3 小时后") { snooze(until: Date().addingTimeInterval(3 * 60 * 60)) }
                Button("明天上午 9 点") { snooze(until: tomorrowAtNine()) }
                Button("取消", role: .cancel) {}
            }
            .sheet(isPresented: $isSharePresented) {
                ActivityView(activityItems: [shareText]) { completed in
                    guard completed else { return }
                    Task {
                        let saved = await model.recordCareAction(type: "shared", payload: actionPayload(channel: "system-share"))
                        if saved { isPresented = false }
                    }
                }
                .presentationDetents([.medium, .large])
            }
        }
        .onAppear { model.clearCareActionError() }
    }

    private func actionButton(_ title: String, icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: icon)
                .font(.system(size: 12, weight: .semibold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 11)
        }
        .buttonStyle(.plain)
        .foregroundStyle(GoHomeTheme.ink)
        .background(GoHomeTheme.softLine, in: RoundedRectangle(cornerRadius: GoHomeTheme.controlRadius, style: .continuous))
        .disabled(model.pendingCareAction != nil)
    }

    private func submit(_ type: String, extra: [String: String] = [:]) {
        Task {
            let saved = await model.recordCareAction(type: type, payload: actionPayload().merging(extra) { _, new in new })
            if saved { isPresented = false }
        }
    }

    private func snooze(until date: Date) {
        submit("snoozed", extra: ["snoozed_until": ISO8601DateFormatter().string(from: date)])
    }

    private func actionPayload(channel: String? = nil) -> [String: String] {
        var payload = [
            "selected_text": draft.trimmingCharacters(in: .whitespacesAndNewlines),
            "topic": selectedTopic,
        ]
        if let channel { payload["channel"] = channel }
        return payload
    }

    private func tomorrowAtNine() -> Date {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "Asia/Shanghai") ?? .current
        let tomorrow = calendar.date(byAdding: .day, value: 1, to: Date()) ?? Date().addingTimeInterval(24 * 60 * 60)
        return calendar.date(bySettingHour: 9, minute: 0, second: 0, of: tomorrow) ?? tomorrow
    }
}

private struct ActivityView: UIViewControllerRepresentable {
    let activityItems: [Any]
    let completion: (Bool) -> Void

    func makeUIViewController(context: Context) -> UIActivityViewController {
        let controller = UIActivityViewController(activityItems: activityItems, applicationActivities: nil)
        controller.completionWithItemsHandler = { _, completed, _, _ in completion(completed) }
        return controller
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

private struct CarePrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 15, weight: .bold))
            .foregroundStyle(GoHomeTheme.ink)
            .padding(.vertical, 14)
            .background(GoHomeTheme.ginger.opacity(configuration.isPressed ? 0.7 : 1), in: RoundedRectangle(cornerRadius: GoHomeTheme.controlRadius, style: .continuous))
    }
}
