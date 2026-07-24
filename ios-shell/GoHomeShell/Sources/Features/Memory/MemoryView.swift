import SwiftUI
import UIKit
import AVKit

private enum MemoryPickerRoute: String, Identifiable {
    case libraryImages
    case libraryVideo
    case camera

    var id: String { rawValue }
}

struct MemoryView: View {
    @ObservedObject var model: MemoryViewModel
    let apiClient: APIClient?
    let user: AppUser
    let family: AppFamily
    @State private var editorMemory: FamilyMemory?
    @State private var isComposerPresented = false
    @State private var commentMemory: FamilyMemory?
    @State private var pickerRoute: MemoryPickerRoute?
    @State private var pendingComposerSeed: MemoryComposerSeed?
    @State private var composerSeed = MemoryComposerSeed.empty
    @State private var composerSessionID = UUID()
    @State private var mediaPickerError: String?

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                header
                    .padding(.bottom, 26)
                if let anniversary = anniversaryMemory {
                    AnniversaryStrip(memory: anniversary, apiClient: apiClient)
                        .padding(.bottom, 28)
                }
                if model.memories.isEmpty {
                    emptyState
                } else {
                    ForEach(model.memories) { memory in
                        MemoryTimelineItem(
                            memory: memory,
                            apiClient: apiClient,
                            currentUserID: user.id,
                            currentUserDisplayName: user.displayName,
                            canManage: memory.author?.id == user.id || family.role == "creator",
                            isPending: model.pendingIDs.contains(memory.id),
                            onFavorite: { Task { await model.toggleFavorite(memory) } },
                            onComment: { commentMemory = memory },
                            onEdit: {
                                editorMemory = memory
                                composerSessionID = UUID()
                                isComposerPresented = true
                            },
                            onDelete: { Task { _ = await model.delete(memory) } }
                        )
                        Divider().overlay(GoHomeTheme.softLine)
                            .padding(.vertical, 26)
                    }
                }
                if let reason = model.state.staleReason, model.state.value != nil {
                    Text(reason)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
            }
            .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
            .padding(.top, 18)
            .padding(.bottom, 36)
        }
        .background(GoHomeTheme.paper)
        .sheet(item: $pickerRoute, onDismiss: presentPendingComposer) { route in
            Group {
                switch route {
                case .libraryImages:
                    MemoryLibraryPicker(
                        mode: .images,
                        onComplete: receivePickedMedia,
                        onCancel: { pickerRoute = nil },
                        onError: handlePickerError
                    )
                case .libraryVideo:
                    MemoryLibraryPicker(
                        mode: .video,
                        onComplete: receivePickedMedia,
                        onCancel: { pickerRoute = nil },
                        onError: handlePickerError
                    )
                case .camera:
                    MemoryCameraPicker(
                        onComplete: { receivePickedMedia([$0]) },
                        onCancel: { pickerRoute = nil },
                        onError: handlePickerError
                    )
                    .ignoresSafeArea()
                }
            }
        }
        .sheet(isPresented: $isComposerPresented, onDismiss: {
            editorMemory = nil
            composerSeed = .empty
        }) {
            MemoryComposer(
                memory: editorMemory,
                seed: composerSeed,
                model: model,
                apiClient: apiClient,
                isPresented: $isComposerPresented
            )
            .id(composerSessionID)
        }
        .sheet(item: $commentMemory) { memory in
            MemoryCommentComposer(memory: memory, model: model, isPresented: Binding(
                get: { commentMemory != nil },
                set: { if !$0 { commentMemory = nil } }
            ))
        }
        .alert("未能完成", isPresented: Binding(
            get: { mediaPickerError != nil || model.errorMessage != nil },
            set: {
                if !$0 {
                    mediaPickerError = nil
                    model.errorMessage = nil
                }
            }
        )) {
            Button("知道了", role: .cancel) {}
        } message: {
            Text(mediaPickerError ?? model.errorMessage ?? "请稍后重试")
        }
        .accessibilityIdentifier("memory-content-anchor")
    }

    private var header: some View {
        HStack(alignment: .bottom) {
            VStack(alignment: .leading, spacing: 6) {
                Text("FAMILY ARCHIVE")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(GoHomeTheme.ginger)
                Text("记忆")
                    .font(.system(size: 32, weight: .bold, design: .rounded))
                    .foregroundStyle(GoHomeTheme.ink)
                Text("只对家庭成员可见")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
            Spacer()
            MemorySourceMenu(openPhotos: openPhotos, openVideo: openVideo, openCamera: openCamera) {
                Image(systemName: "camera")
                    .symbolVariant(.none)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.ink)
                    .frame(width: 42, height: 42)
                    .background(GoHomeTheme.ginger, in: Circle())
            }
            .accessibilityLabel("发布记忆")
            .accessibilityIdentifier("memory-create-camera")
        }
        .zIndex(20)
    }

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("从一张照片或一句话开始")
                .font(.system(size: 21, weight: .bold))
                .foregroundStyle(GoHomeTheme.ink)
            Text("旅行、团聚、一道熟悉的菜，都可以留在家庭时间流里。")
                .font(.system(size: 14))
                .foregroundStyle(GoHomeTheme.mutedInk)
                .fixedSize(horizontal: false, vertical: true)
            MemorySourceMenu(openPhotos: openPhotos, openVideo: openVideo, openCamera: openCamera) {
                Text("发布第一条")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(GoHomeTheme.ink)
                    .padding(.horizontal, 15)
                    .padding(.vertical, 10)
                    .background(GoHomeTheme.ginger, in: RoundedRectangle(cornerRadius: GoHomeTheme.controlRadius, style: .continuous))
            }
        }
        .padding(.vertical, 30)
    }

    private var anniversaryMemory: FamilyMemory? {
        let formatter = ISO8601DateFormatter()
        let calendar = Calendar.current
        return model.memories.first { memory in
            guard let date = formatter.date(from: memory.happenedAt) else { return false }
            return calendar.component(.month, from: date) == calendar.component(.month, from: Date())
                && calendar.component(.day, from: date) == calendar.component(.day, from: Date())
                && !calendar.isDate(date, equalTo: Date(), toGranularity: .year)
        }
    }

    private func openPhotos() {
        editorMemory = nil
        pickerRoute = .libraryImages
    }

    private func openVideo() {
        editorMemory = nil
        pickerRoute = .libraryVideo
    }

    private func openCamera() {
        guard MemoryCameraPicker.isAvailable else {
            mediaPickerError = MemoryMediaPickerError.cameraUnavailable.localizedDescription
            return
        }
        editorMemory = nil
        pickerRoute = .camera
    }

    private func receivePickedMedia(_ media: [MemoryPickedMedia]) {
        pendingComposerSeed = MemoryComposerSeed(media: media)
        pickerRoute = nil
    }

    private func handlePickerError(_ message: String) {
        mediaPickerError = message
        pickerRoute = nil
    }

    private func presentPendingComposer() {
        guard let seed = pendingComposerSeed else { return }
        pendingComposerSeed = nil
        composerSeed = seed
        composerSessionID = UUID()
        isComposerPresented = true
    }
}

private struct MemorySourceMenu<Label: View>: View {
    let openPhotos: () -> Void
    let openVideo: () -> Void
    let openCamera: () -> Void
    let label: Label
    @State private var isPresented = false

    init(
        openPhotos: @escaping () -> Void,
        openVideo: @escaping () -> Void,
        openCamera: @escaping () -> Void,
        @ViewBuilder label: () -> Label
    ) {
        self.openPhotos = openPhotos
        self.openVideo = openVideo
        self.openCamera = openCamera
        self.label = label()
    }

    var body: some View {
        Button {
            isPresented.toggle()
        } label: {
            label
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .popover(isPresented: $isPresented, attachmentAnchor: .rect(.bounds), arrowEdge: .top) {
            MemorySourcePopover(
                openPhotos: { perform(openPhotos) },
                openVideo: { perform(openVideo) },
                openCamera: { perform(openCamera) }
            )
        }
        .zIndex(20)
    }

    private func perform(_ action: @escaping () -> Void) {
        isPresented = false
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.12, execute: action)
    }
}

private struct MemorySourcePopover: View {
    let openPhotos: () -> Void
    let openVideo: () -> Void
    let openCamera: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            actionButton("选择照片", systemImage: "photo.on.rectangle", action: openPhotos)
            Divider().overlay(GoHomeTheme.softLine)
            actionButton("选择视频", systemImage: "video", action: openVideo)
            Divider().overlay(GoHomeTheme.softLine)
            actionButton("拍摄", systemImage: "camera", action: openCamera)
        }
        .frame(width: 190)
        .padding(.vertical, 6)
        .background(GoHomeTheme.paper)
        .memoryPopoverAdaptation()
    }

    private func actionButton(_ title: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: systemImage)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(GoHomeTheme.ink)
                .frame(maxWidth: .infinity, alignment: .leading)
                .frame(height: 48)
                .padding(.horizontal, 16)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

private extension View {
    @ViewBuilder
    func memoryPopoverAdaptation() -> some View {
        if #available(iOS 16.4, *) {
            presentationCompactAdaptation(.popover)
        } else {
            self
        }
    }
}

private struct AnniversaryStrip: View {
    let memory: FamilyMemory
    let apiClient: APIClient?

    var body: some View {
        HStack(spacing: 14) {
            if let media = memory.media.first {
                Group {
                    if media.isVideo {
                        MemoryVideoPoster(
                            assetID: media.assetID,
                            duration: media.durationSeconds,
                            apiClient: apiClient
                        )
                    } else {
                        AuthenticatedMemoryImage(path: media.imageURL, apiClient: apiClient)
                    }
                }
                    .frame(width: 82, height: 82)
                    .clipShape(RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
            }
            VStack(alignment: .leading, spacing: 5) {
                Text("这一天")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(GoHomeTheme.ginger)
                Text(memory.body.isEmpty ? "一段值得再看的记忆" : memory.body)
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(GoHomeTheme.ink)
                    .lineLimit(2)
            }
            Spacer()
        }
        .padding(14)
        .background(GoHomeTheme.paleGinger.opacity(0.6), in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
    }
}

private struct MemoryTimelineItem: View {
    let memory: FamilyMemory
    let apiClient: APIClient?
    let currentUserID: String
    let currentUserDisplayName: String?
    let canManage: Bool
    let isPending: Bool
    let onFavorite: () -> Void
    let onComment: () -> Void
    let onEdit: () -> Void
    let onDelete: () -> Void
    @State private var isManagementPresented = false

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 11) {
                MemoryAuthorAvatar(initial: authorInitial)
                VStack(alignment: .leading, spacing: 3) {
                    Text(authorDisplayName)
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(GoHomeTheme.ink)
                    Text(publishedTimeText)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
                Spacer()
            }
            if !memory.body.isEmpty {
                Text(memory.body)
                    .font(.system(size: 17, weight: .regular))
                    .foregroundStyle(GoHomeTheme.ink)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !memory.media.isEmpty {
                MemoryMediaGrid(media: memory.media, apiClient: apiClient)
            }
            HStack(spacing: 22) {
                Button {
                    UIImpactFeedbackGenerator(style: .light).impactOccurred()
                    onFavorite()
                } label: {
                    Label(
                        memory.favoriteCount > 0 ? "\(memory.favoriteCount)" : "喜欢",
                        systemImage: memory.isFavorite ? "heart.fill" : "heart"
                    )
                }
                .foregroundStyle(memory.isFavorite ? GoHomeTheme.ginger : GoHomeTheme.ink)
                .accessibilityIdentifier("memory-like-\(memory.id)")
                Button(action: onComment) {
                    Label(memory.comments.isEmpty ? "评论" : "\(memory.comments.count)", systemImage: "bubble.left")
                }
                .foregroundStyle(GoHomeTheme.ink)
                .accessibilityIdentifier("memory-comment-\(memory.id)")
                Spacer()
                if canManage {
                    Button {
                        isManagementPresented.toggle()
                    } label: {
                        Image(systemName: "ellipsis")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundStyle(GoHomeTheme.mutedInk)
                            .frame(width: 44, height: 36)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .disabled(isPending)
                    .popover(isPresented: $isManagementPresented, attachmentAnchor: .rect(.bounds), arrowEdge: .bottom) {
                        MemoryManagementPopover(
                            onEdit: { performManagementAction(onEdit) },
                            onDelete: { performManagementAction(onDelete) }
                        )
                    }
                    .zIndex(20)
                    .accessibilityLabel("管理记忆")
                    .accessibilityIdentifier("memory-actions-\(memory.id)")
                }
            }
            .buttonStyle(.plain)
            .font(.system(size: 12, weight: .semibold))
            .disabled(isPending)
            if !memory.locationName.isEmpty {
                Label(memory.locationName, systemImage: "mappin.and.ellipse")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(GoHomeTheme.mutedInk)
            }
            if !memory.comments.isEmpty {
                VStack(alignment: .leading, spacing: 7) {
                    ForEach(memory.comments.prefix(3)) { comment in
                        HStack(alignment: .firstTextBaseline, spacing: 4) {
                            Text(comment.authorUserID == currentUserID ? "我" : "家庭成员")
                                .fontWeight(.semibold)
                                .foregroundStyle(GoHomeTheme.ink)
                            Text(comment.body)
                                .foregroundStyle(GoHomeTheme.mutedInk)
                        }
                        .font(.system(size: 12))
                    }
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.black.opacity(0.032), in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
            }
        }
        .zIndex(isManagementPresented ? 10 : 0)
    }

    private var publishedTimeText: String {
        MemoryDateFormatting.publishedText(memory.createdAt ?? memory.updatedAt ?? memory.happenedAt)
    }

    private var authorDisplayName: String {
        guard let author = memory.author else { return "家庭成员" }
        if author.id == currentUserID { return "我" }

        let name = author.displayName.trimmingCharacters(in: .whitespacesAndNewlines)
        let genericNames: Set<String> = ["家属", "回家用户", "家庭成员"]
        return name.isEmpty || genericNames.contains(name) ? "家庭成员" : name
    }

    private var authorInitial: String? {
        let rawName: String
        if memory.author?.id == currentUserID {
            rawName = currentUserDisplayName ?? memory.author?.displayName ?? ""
        } else {
            rawName = memory.author?.displayName ?? ""
        }
        let name = rawName.trimmingCharacters(in: .whitespacesAndNewlines)
        let genericNames: Set<String> = ["家属", "回家用户", "家庭成员"]
        guard !name.isEmpty, !genericNames.contains(name), let first = name.first else { return nil }
        return String(first)
    }

    private func performManagementAction(_ action: @escaping () -> Void) {
        isManagementPresented = false
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.12, execute: action)
    }
}

private struct MemoryAuthorAvatar: View {
    let initial: String?

    var body: some View {
        ZStack {
            Circle().fill(GoHomeTheme.paleGinger)
            if let initial {
                Text(initial)
                    .font(.system(size: 15, weight: .bold, design: .rounded))
                    .foregroundStyle(GoHomeTheme.ink)
            } else {
                Image(systemName: "person.fill")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.ink.opacity(0.72))
            }
        }
        .frame(width: 38, height: 38)
        .accessibilityHidden(true)
    }
}

enum MemoryDateFormatting {
    static func publishedText(
        _ value: String?,
        now: Date = Date(),
        calendar: Calendar = .current
    ) -> String {
        guard let value, let date = date(from: value) else { return "发布时间未知" }

        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.timeZone = calendar.timeZone
        if calendar.isDate(date, inSameDayAs: now) {
            formatter.dateFormat = "HH:mm"
            return "发布于 今天 \(formatter.string(from: date))"
        }
        if let yesterday = calendar.date(byAdding: .day, value: -1, to: now),
           calendar.isDate(date, inSameDayAs: yesterday) {
            formatter.dateFormat = "HH:mm"
            return "发布于 昨天 \(formatter.string(from: date))"
        }
        formatter.dateFormat = calendar.component(.year, from: date) == calendar.component(.year, from: now)
            ? "M月d日 HH:mm"
            : "yyyy年M月d日 HH:mm"
        return "发布于 \(formatter.string(from: date))"
    }

    static func date(from value: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return fractional.date(from: value) ?? ISO8601DateFormatter().date(from: value)
    }
}

private struct MemoryManagementPopover: View {
    let onEdit: () -> Void
    let onDelete: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            actionButton("编辑", systemImage: "pencil", color: GoHomeTheme.ink, action: onEdit)
            Divider().overlay(GoHomeTheme.softLine)
            actionButton("删除", systemImage: "trash", color: .red, action: onDelete)
        }
        .frame(width: 176)
        .padding(.vertical, 6)
        .background(GoHomeTheme.paper)
        .memoryPopoverAdaptation()
    }

    private func actionButton(
        _ title: String,
        systemImage: String,
        color: Color,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Label(title, systemImage: systemImage)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(color)
                .frame(maxWidth: .infinity, alignment: .leading)
                .frame(height: 46)
                .padding(.horizontal, 16)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

private struct MemoryMediaGrid: View {
    let media: [MemoryMedia]
    let apiClient: APIClient?
    @State private var previewIndex: Int?

    var body: some View {
        let visibleMedia = Array(media.prefix(9))
        let columns = Array(
            repeating: GridItem(.flexible(), spacing: MemoryMediaLayout.spacing),
            count: MemoryMediaLayout.columnCount(for: visibleMedia.count)
        )
        LazyVGrid(columns: columns, spacing: 4) {
            ForEach(Array(visibleMedia.enumerated()), id: \.element.id) { index, item in
                Button { previewIndex = index } label: {
                    MemoryImageTile(aspectRatio: MemoryMediaLayout.aspectRatio(for: visibleMedia.count)) {
                        if item.isVideo {
                            MemoryVideoPoster(
                                assetID: item.assetID,
                                duration: item.durationSeconds,
                                apiClient: apiClient
                            )
                        } else {
                            AuthenticatedMemoryImage(path: item.imageURL, apiClient: apiClient, variant: "grid")
                        }
                    }
                }
                .buttonStyle(.plain)
                .contentShape(Rectangle())
                .clipped()
                .accessibilityLabel(item.isVideo ? "播放视频" : "查看第 \(index + 1) 张照片")
            }
        }
        .fullScreenCover(isPresented: Binding(
            get: { previewIndex != nil },
            set: { if !$0 { previewIndex = nil } }
        )) {
            MemoryMediaPreview(media: visibleMedia, apiClient: apiClient, selectedIndex: previewIndex ?? 0)
        }
    }
}

private func memoryImageCacheKey(path: String, variant: String? = nil) -> String {
    variant.map { "\(path)|variant=\($0)" } ?? path
}

enum MemoryMediaLayout {
    static let spacing: CGFloat = 4

    static func columnCount(for count: Int) -> Int {
        if count <= 1 { return 1 }
        if count == 2 || count == 4 { return 2 }
        return 3
    }

    static func aspectRatio(for count: Int) -> CGFloat {
        count == 1 ? 4 / 3 : 1
    }
}

private struct MemoryMediaPreview: View {
    let media: [MemoryMedia]
    let apiClient: APIClient?
    @State var selectedIndex: Int
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Color.black.ignoresSafeArea()
            TabView(selection: $selectedIndex) {
                ForEach(Array(media.enumerated()), id: \.element.id) { index, item in
                    Group {
                        if item.isVideo {
                            AuthenticatedMemoryVideo(assetID: item.assetID, apiClient: apiClient)
                        } else {
                            AuthenticatedMemoryImage(path: item.imageURL, apiClient: apiClient, contentMode: .fit)
                        }
                    }
                    .padding(.vertical, 70)
                    .tag(index)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: media.count > 1 ? .automatic : .never))
            Button { dismiss() } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(.white)
                    .frame(width: 40, height: 40)
                    .background(.black.opacity(0.55), in: Circle())
            }
            .padding(.top, 12)
            .padding(.trailing, 14)
            .accessibilityLabel("关闭预览")
        }
    }
}

private struct AuthenticatedMemoryImage: View {
    let path: String
    let apiClient: APIClient?
    var variant: String? = nil
    var contentMode: ContentMode = .fill
    @State private var image: UIImage?

    private var cacheKey: String {
        memoryImageCacheKey(path: path, variant: variant)
    }

    var body: some View {
        ZStack {
            Color.black.opacity(0.035)
            if let image {
                Image(uiImage: image).resizable().aspectRatio(contentMode: contentMode)
            } else {
                Image(systemName: "photo")
                    .foregroundStyle(GoHomeTheme.mutedInk.opacity(0.5))
            }
        }
        .task(id: cacheKey) {
            guard !path.isEmpty else { return }
            image = await MemoryImageCache.shared.load(path: path, variant: variant, apiClient: apiClient)
        }
    }
}

@MainActor
private final class MemoryImageCache {
    static let shared = MemoryImageCache()
    private let cache = NSCache<NSString, UIImage>()
    private var inFlight: [String: Task<UIImage?, Never>] = [:]

    private init() {
        cache.countLimit = 80
        cache.totalCostLimit = 48 * 1024 * 1024
    }

    func image(for path: String) -> UIImage? {
        cache.object(forKey: path as NSString)
    }

    func insert(_ image: UIImage, for path: String) {
        let cost = Int(image.size.width * image.size.height * image.scale * image.scale * 4)
        cache.setObject(image, forKey: path as NSString, cost: cost)
    }

    func insert(data: Data, for paths: [String]) {
        guard let image = UIImage(data: data) else { return }
        for path in paths where !path.isEmpty { insert(image, for: path) }
    }

    func load(path: String, variant: String? = nil, apiClient: APIClient?) async -> UIImage? {
        let key = memoryImageCacheKey(path: path, variant: variant)
        if let cached = image(for: key) { return cached }
        if let task = inFlight[key] { return await task.value }
        guard let apiClient else { return nil }
        let task = Task<UIImage?, Never> {
            let queryItems = variant.map { [URLQueryItem(name: "variant", value: $0)] } ?? []
            guard let data = try? await apiClient.data(path: path, queryItems: queryItems) else { return nil }
            return await Task.detached(priority: .userInitiated) { UIImage(data: data) }.value
        }
        inFlight[key] = task
        let loaded = await task.value
        inFlight[key] = nil
        if let loaded { insert(loaded, for: key) }
        return loaded
    }
}

private struct MemoryVideoPoster: View {
    let assetID: String
    let duration: Double?
    let apiClient: APIClient?
    @State private var image: UIImage?

    var body: some View {
        ZStack {
            Color.black.opacity(0.82)
            if let image {
                Image(uiImage: image).resizable().scaledToFill()
            }
            Image(systemName: "play.fill")
                .font(.system(size: 18, weight: .bold))
                .foregroundStyle(.white)
                .frame(width: 42, height: 42)
                .background(.black.opacity(0.58), in: Circle())
            if let duration, duration > 0 {
                Text(videoDurationText(duration))
                    .font(.system(size: 11, weight: .bold, design: .monospaced))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 7)
                    .padding(.vertical, 4)
                    .background(.black.opacity(0.62), in: Capsule())
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
                    .padding(8)
            }
        }
        .task(id: assetID) {
            image = await MemoryVideoPlaybackStore.shared.poster(assetID: assetID, apiClient: apiClient)
        }
    }
}

private struct AuthenticatedMemoryVideo: View {
    let assetID: String
    let apiClient: APIClient?
    @State private var player: AVPlayer?
    @State private var failed = false

    var body: some View {
        ZStack {
            Color.black
            if let player {
                VideoPlayer(player: player)
            } else if failed {
                Image(systemName: "exclamationmark.triangle")
                    .foregroundStyle(.white.opacity(0.8))
            } else {
                ProgressView().tint(.white)
            }
        }
        .task(id: assetID) { await load() }
        .onDisappear { cleanup() }
    }

    private func load() async {
        guard player == nil, let apiClient, !assetID.isEmpty else { return }
        failed = false
        do {
            let url = try await MemoryVideoPlaybackStore.shared.playbackURL(
                assetID: assetID,
                apiClient: apiClient
            )
            try Task.checkCancellation()
            let nextPlayer = AVPlayer(url: url)
            nextPlayer.automaticallyWaitsToMinimizeStalling = true
            player = nextPlayer
            nextPlayer.play()
        } catch is CancellationError {
            cleanup()
        } catch {
            failed = true
        }
    }

    private func cleanup() {
        player?.pause()
        player?.replaceCurrentItem(with: nil)
        player = nil
    }
}

private func videoDurationText(_ duration: Double) -> String {
    let seconds = max(0, Int(duration.rounded()))
    return String(format: "%d:%02d", seconds / 60, seconds % 60)
}

private struct MemoryImageTile<Content: View>: View {
    let aspectRatio: CGFloat
    let content: Content

    init(aspectRatio: CGFloat, @ViewBuilder content: () -> Content) {
        self.aspectRatio = aspectRatio
        self.content = content()
    }

    var body: some View {
        Color.black.opacity(0.035)
            .aspectRatio(aspectRatio, contentMode: .fit)
            .overlay {
                content
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .clipped()
            }
            .clipShape(RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
    }
}

private struct MemoryDraftImage: Identifiable {
    let id = UUID()
    let sourceURL: URL?
    var upload: MemoryUploadAsset?
    var preview: UIImage?
}

private struct MemoryDraftVideo {
    let upload: MemoryUploadAsset
    let preview: UIImage?
}

private struct MemoryComposer: View {
    let memory: FamilyMemory?
    let seed: MemoryComposerSeed
    @ObservedObject var model: MemoryViewModel
    let apiClient: APIClient?
    @Binding var isPresented: Bool
    @State private var bodyText: String
    @State private var locationName: String
    @State private var newImages: [MemoryDraftImage] = []
    @State private var newVideo: MemoryDraftVideo?
    @State private var pendingVideoURL: URL?
    @State private var retainedMedia: [MemoryMedia]
    @State private var isPreparingImages = false
    @State private var isPreparingVideo = false
    @State private var mediaPreparationError: String?
    @State private var imageSelectionGeneration = UUID()
    @State private var didPrepareSeed = false
    @StateObject private var locationProvider = MemoryLocationProvider()

    init(
        memory: FamilyMemory?,
        seed: MemoryComposerSeed,
        model: MemoryViewModel,
        apiClient: APIClient?,
        isPresented: Binding<Bool>
    ) {
        self.memory = memory
        self.seed = seed
        self.model = model
        self.apiClient = apiClient
        _isPresented = isPresented
        _bodyText = State(initialValue: memory?.body ?? "")
        _locationName = State(initialValue: memory?.locationName ?? "")
        _retainedMedia = State(initialValue: memory?.media ?? [])
        _newImages = State(initialValue: seed.media.compactMap { item in
            guard item.kind == .image else { return nil }
            return MemoryDraftImage(sourceURL: item.localURL, upload: nil, preview: nil)
        })
        _pendingVideoURL = State(initialValue: seed.media.first(where: { $0.kind == .video })?.localURL)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    if hasMedia {
                        MemoryComposerMediaGrid(
                            retainedMedia: $retainedMedia,
                            newImages: $newImages,
                            newVideo: $newVideo,
                            pendingVideoURL: $pendingVideoURL,
                            isProcessing: isPreparingImages || isPreparingVideo,
                            apiClient: apiClient
                        )
                        .padding(.bottom, 22)
                    }
                    ZStack(alignment: .topLeading) {
                        if bodyText.isEmpty {
                            Text("这一刻的想法...")
                                .font(.system(size: 17))
                                .foregroundStyle(GoHomeTheme.mutedInk.opacity(0.72))
                                .padding(.top, 8)
                                .allowsHitTesting(false)
                        }
                        TextEditor(text: $bodyText)
                            .font(.system(size: 17))
                            .foregroundStyle(GoHomeTheme.ink)
                            .scrollContentBackground(.hidden)
                            .frame(minHeight: 132)
                            .padding(.horizontal, -5)
                    }
                    if let mediaPreparationError {
                        Text(mediaPreparationError)
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(.red)
                            .padding(.bottom, 12)
                    }
                    MemoryComposerDetails(
                        locationName: $locationName,
                        isLocating: locationProvider.isLocating,
                        locationError: locationProvider.errorMessage,
                        requestLocation: locationProvider.requestLocation
                    )
                }
                .padding(GoHomeTheme.pageHorizontalPadding)
            }
            .scrollDismissesKeyboard(.interactively)
            .background(GoHomeTheme.paper)
            .navigationTitle(memory == nil ? "发布记忆" : "编辑记忆")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("取消") { isPresented = false } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(model.isPublishing ? model.publishPhase.toolbarTitle : "发布") { publish() }
                        .fontWeight(.bold)
                        .disabled(isPreparingImages || isPreparingVideo || model.isPublishing || (bodyText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && newImages.isEmpty && newVideo == nil && retainedMedia.isEmpty))
                }
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                if model.isPublishing {
                    HStack(spacing: 12) {
                        ProgressView()
                            .tint(GoHomeTheme.ginger)
                        Text(model.publishPhase.statusText)
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(GoHomeTheme.ink)
                        Spacer()
                    }
                    .padding(.horizontal, GoHomeTheme.pageHorizontalPadding)
                    .frame(height: 52)
                    .background(.ultraThinMaterial)
                    .overlay(alignment: .top) { Divider().overlay(GoHomeTheme.softLine) }
                        .accessibilityIdentifier("memory-publish-status")
                }
            }
            .task {
                await prepareSeedMediaIfNeeded()
            }
            .onChange(of: locationProvider.placeName) { placeName in
                guard let placeName else { return }
                locationName = placeName
            }
            .onDisappear {
                cleanupSeedFiles()
            }
        }
    }

    private var hasMedia: Bool {
        !retainedMedia.isEmpty || !newImages.isEmpty || newVideo != nil || pendingVideoURL != nil
    }

    private func prepareSeedMediaIfNeeded() async {
        guard !didPrepareSeed else { return }
        didPrepareSeed = true
        mediaPreparationError = nil
        if !newImages.isEmpty {
            let generation = UUID()
            imageSelectionGeneration = generation
            let drafts = newImages
            isPreparingImages = true
            await withTaskGroup(of: (UUID, MemoryUploadAsset?).self) { group in
                for draft in drafts {
                    group.addTask {
                        guard let sourceURL = draft.sourceURL else { return (draft.id, nil) }
                        defer { try? FileManager.default.removeItem(at: sourceURL) }
                        return (draft.id, await MemoryImageProcessor.prepare(sourceURL: sourceURL))
                    }
                }
                for await (draftID, prepared) in group {
                    guard imageSelectionGeneration == generation,
                          let index = newImages.firstIndex(where: { $0.id == draftID }) else { continue }
                    newImages[index].upload = prepared
                    newImages[index].preview = prepared.flatMap { UIImage(data: $0.data) }
                }
            }
            guard imageSelectionGeneration == generation else { return }
            let failedCount = newImages.filter { $0.upload == nil }.count
            newImages.removeAll { $0.upload == nil }
            isPreparingImages = false
            if failedCount > 0 {
                mediaPreparationError = "有 \(failedCount) 张照片无法读取，请重新选择"
            }
        }
        if let sourceURL = pendingVideoURL {
            isPreparingVideo = true
            do {
                defer { try? FileManager.default.removeItem(at: sourceURL) }
                let prepared = try await MemoryVideoProcessor.prepare(sourceURL: sourceURL)
                newVideo = MemoryDraftVideo(upload: prepared.upload, preview: prepared.preview)
                pendingVideoURL = nil
                isPreparingVideo = false
            } catch {
                pendingVideoURL = nil
                newVideo = nil
                isPreparingVideo = false
                mediaPreparationError = (error as? LocalizedError)?.errorDescription ?? "视频处理失败，请重新选择"
            }
        }
    }

    private func cleanupSeedFiles() {
        seed.media.forEach { try? FileManager.default.removeItem(at: $0.localURL) }
    }

    private func publish() {
        Task {
            let uploads = newVideo.map { [$0.upload] } ?? newImages.compactMap(\.upload)
            let outcome = await model.save(
                existing: memory,
                body: bodyText,
                happenedAt: memory.flatMap { MemoryDateFormatting.date(from: $0.happenedAt) } ?? Date(),
                locationName: locationName,
                people: memory?.people ?? [],
                retainedMediaIDs: retainedMedia.map(\.assetID),
                newMedia: uploads
            )
            if let outcome {
                for (asset, upload) in zip(outcome.uploadedAssets, uploads) where !upload.isVideo {
                    MemoryImageCache.shared.insert(
                        data: upload.data,
                        for: [
                            asset.imageURL,
                            memoryImageCacheKey(path: asset.imageURL, variant: "grid"),
                        ]
                    )
                }
                if let video = newVideo, let asset = outcome.uploadedAssets.first, let preview = video.preview {
                    MemoryVideoPlaybackStore.shared.insert(preview, assetID: asset.id)
                }
                isPresented = false
            }
        }
    }
}

private struct MemoryComposerDetails: View {
    @Binding var locationName: String
    let isLocating: Bool
    let locationError: String?
    let requestLocation: () -> Void

    var body: some View {
        locationRow
        .padding(.horizontal, 14)
        .background(Color.black.opacity(0.032), in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
    }

    private var locationRow: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Image(systemName: "mappin.and.ellipse")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(GoHomeTheme.ginger)
                    .frame(width: 22)
                Text("地点")
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(GoHomeTheme.ink)
                TextField("添加地点", text: $locationName)
                    .font(.system(size: 14))
                    .multilineTextAlignment(.trailing)
                    .foregroundStyle(GoHomeTheme.ink)
                Button(action: requestLocation) {
                    Group {
                        if isLocating {
                            ProgressView().tint(GoHomeTheme.ginger)
                        } else {
                            Image(systemName: "location.fill")
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundStyle(GoHomeTheme.ginger)
                        }
                    }
                    .frame(width: 32, height: 32)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(isLocating)
                .accessibilityLabel("获取当前位置")
            }
            .frame(minHeight: 52)
            if let locationError {
                Text(locationError)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(.red)
                    .frame(maxWidth: .infinity, alignment: .trailing)
                    .padding(.bottom, 9)
            }
        }
    }

}

private struct MemoryComposerMediaGrid: View {
    @Binding var retainedMedia: [MemoryMedia]
    @Binding var newImages: [MemoryDraftImage]
    @Binding var newVideo: MemoryDraftVideo?
    @Binding var pendingVideoURL: URL?
    let isProcessing: Bool
    let apiClient: APIClient?

    var body: some View {
        let videoCount = newVideo == nil && pendingVideoURL == nil ? 0 : 1
        let count = min(9, retainedMedia.count + newImages.count + videoCount)
        let columns = Array(
            repeating: GridItem(.flexible(), spacing: MemoryMediaLayout.spacing),
            count: MemoryMediaLayout.columnCount(for: count)
        )
        LazyVGrid(columns: columns, spacing: MemoryMediaLayout.spacing) {
            ForEach(Array(retainedMedia.enumerated()), id: \.element.id) { index, media in
                mediaTile(index: index, count: count) {
                    if media.isVideo {
                        MemoryVideoPoster(
                            assetID: media.assetID,
                            duration: media.durationSeconds,
                            apiClient: apiClient
                        )
                    } else {
                        AuthenticatedMemoryImage(path: media.imageURL, apiClient: apiClient, variant: "grid")
                    }
                } onRemove: {
                    retainedMedia.removeAll { $0.id == media.id }
                }
            }
            ForEach(Array(newImages.enumerated()), id: \.element.id) { index, draft in
                mediaTile(index: retainedMedia.count + index, count: count) {
                    if let image = draft.preview {
                        Image(uiImage: image).resizable().scaledToFill()
                    } else {
                        ProgressView().tint(GoHomeTheme.ginger)
                    }
                } onRemove: {
                    newImages.removeAll { $0.id == draft.id }
                }
            }
            if let video = newVideo {
                mediaTile(index: retainedMedia.count + newImages.count, count: count) {
                    ZStack {
                        if let preview = video.preview {
                            Image(uiImage: preview).resizable().scaledToFill()
                        } else {
                            Color.black.opacity(0.82)
                        }
                        Image(systemName: "play.fill")
                            .foregroundStyle(.white)
                            .frame(width: 42, height: 42)
                            .background(.black.opacity(0.58), in: Circle())
                    }
                } onRemove: {
                    newVideo = nil
                }
            } else if pendingVideoURL != nil {
                mediaTile(index: retainedMedia.count + newImages.count, count: count) {
                    ZStack {
                        Color.black.opacity(0.78)
                        ProgressView().tint(.white)
                    }
                } onRemove: {
                    if let url = pendingVideoURL {
                        try? FileManager.default.removeItem(at: url)
                    }
                    pendingVideoURL = nil
                }
            }
        }
    }

    private func mediaTile<Content: View>(
        index: Int,
        count: Int,
        @ViewBuilder content: () -> Content,
        onRemove: @escaping () -> Void
    ) -> some View {
        ZStack(alignment: .topTrailing) {
            MemoryImageTile(aspectRatio: MemoryMediaLayout.aspectRatio(for: count)) {
                content()
            }
            Button(action: onRemove) {
                Image(systemName: "xmark")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(.white)
                    .frame(width: 26, height: 26)
                    .background(.black.opacity(0.72), in: Circle())
            }
            .buttonStyle(.plain)
            .frame(width: 36, height: 36)
            .padding(4)
            .contentShape(Rectangle())
            .disabled(isProcessing)
            .accessibilityLabel("移除第 \(index + 1) 个媒体")
        }
        .contentShape(Rectangle())
    }
}

private struct MemoryCommentComposer: View {
    let memory: FamilyMemory
    @ObservedObject var model: MemoryViewModel
    @Binding var isPresented: Bool
    @State private var bodyText = ""
    @FocusState private var isFocused: Bool

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 14) {
                if !memory.body.isEmpty {
                    Text(memory.body)
                        .font(.system(size: 13))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                        .lineLimit(2)
                }
                TextField("写下评论", text: $bodyText, axis: .vertical)
                    .font(.system(size: 16))
                    .lineLimit(2...4)
                    .focused($isFocused)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 12)
                    .background(Color.black.opacity(0.04), in: RoundedRectangle(cornerRadius: GoHomeTheme.controlRadius, style: .continuous))
                Spacer()
            }
            .padding(GoHomeTheme.pageHorizontalPadding)
            .navigationTitle("评论")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("取消") { isPresented = false } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("发布") {
                        let submittedBody = bodyText
                        UIImpactFeedbackGenerator(style: .light).impactOccurred()
                        isPresented = false
                        Task {
                            _ = await model.addComment(submittedBody, to: memory)
                        }
                    }
                    .fontWeight(.bold)
                    .disabled(bodyText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
            .onAppear { isFocused = true }
        }
        .presentationDetents([.height(230)])
        .presentationDragIndicator(.visible)
    }
}
