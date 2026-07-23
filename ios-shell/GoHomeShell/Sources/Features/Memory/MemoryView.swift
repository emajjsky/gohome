import ImageIO
import PhotosUI
import SwiftUI
import UIKit

struct MemoryView: View {
    @ObservedObject var model: MemoryViewModel
    let apiClient: APIClient?
    let user: AppUser
    let family: AppFamily
    @State private var editorMemory: FamilyMemory?
    @State private var isComposerPresented = false
    @State private var commentMemory: FamilyMemory?

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
                            canManage: memory.author?.id == user.id || family.role == "creator",
                            isPending: model.pendingIDs.contains(memory.id),
                            onFavorite: { Task { await model.toggleFavorite(memory) } },
                            onComment: { commentMemory = memory },
                            onEdit: {
                                editorMemory = memory
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
        .sheet(isPresented: $isComposerPresented, onDismiss: { editorMemory = nil }) {
            MemoryComposer(memory: editorMemory, model: model, apiClient: apiClient, isPresented: $isComposerPresented)
        }
        .sheet(item: $commentMemory) { memory in
            MemoryCommentComposer(memory: memory, model: model, isPresented: Binding(
                get: { commentMemory != nil },
                set: { if !$0 { commentMemory = nil } }
            ))
        }
        .alert("未能完成", isPresented: Binding(
            get: { model.errorMessage != nil },
            set: { if !$0 { model.errorMessage = nil } }
        )) {
            Button("知道了", role: .cancel) {}
        } message: {
            Text(model.errorMessage ?? "请稍后重试")
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
            Button {
                editorMemory = nil
                isComposerPresented = true
            } label: {
                Image(systemName: "plus")
                    .font(.system(size: 17, weight: .bold))
                    .foregroundStyle(GoHomeTheme.ink)
                    .frame(width: 42, height: 42)
                    .background(GoHomeTheme.ginger, in: Circle())
            }
            .accessibilityLabel("发布记忆")
        }
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
            Button("写下第一条") {
                editorMemory = nil
                isComposerPresented = true
            }
            .font(.system(size: 14, weight: .bold))
            .foregroundStyle(GoHomeTheme.ink)
            .padding(.horizontal, 15)
            .padding(.vertical, 10)
            .background(GoHomeTheme.ginger, in: RoundedRectangle(cornerRadius: GoHomeTheme.controlRadius, style: .continuous))
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
}

private struct AnniversaryStrip: View {
    let memory: FamilyMemory
    let apiClient: APIClient?

    var body: some View {
        HStack(spacing: 14) {
            if let media = memory.media.first {
                AuthenticatedMemoryImage(path: media.imageURL, apiClient: apiClient)
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
    let canManage: Bool
    let isPending: Bool
    let onFavorite: () -> Void
    let onComment: () -> Void
    let onEdit: () -> Void
    let onDelete: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(memory.author?.displayName ?? "家庭成员")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(GoHomeTheme.ink)
                    Text(metaText)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(GoHomeTheme.mutedInk)
                }
                Spacer()
                if canManage {
                    Menu {
                        Button("编辑", systemImage: "pencil", action: onEdit)
                        Button("删除", systemImage: "trash", role: .destructive, action: onDelete)
                    } label: {
                        Image(systemName: "ellipsis")
                            .foregroundStyle(GoHomeTheme.mutedInk)
                            .frame(width: 34, height: 30)
                    }
                }
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
            if !memory.people.isEmpty {
                HStack(spacing: 6) {
                    Image(systemName: "person.2")
                    Text(memory.people.joined(separator: " · "))
                }
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(GoHomeTheme.mutedInk)
            }
            HStack(spacing: 22) {
                Button(action: onFavorite) {
                    Label(memory.favoriteCount > 0 ? "\(memory.favoriteCount)" : "收藏", systemImage: memory.isFavorite ? "bookmark.fill" : "bookmark")
                }
                Button(action: onComment) {
                    Label(memory.comments.isEmpty ? "回应" : "\(memory.comments.count)", systemImage: "bubble.left")
                }
            }
            .buttonStyle(.plain)
            .font(.system(size: 12, weight: .semibold))
            .foregroundStyle(GoHomeTheme.ink)
            .disabled(isPending)
            if !memory.comments.isEmpty {
                VStack(alignment: .leading, spacing: 7) {
                    ForEach(memory.comments.prefix(3)) { comment in
                        Text(comment.body)
                            .font(.system(size: 12))
                            .foregroundStyle(GoHomeTheme.mutedInk)
                    }
                }
                .padding(.leading, 11)
                .overlay(alignment: .leading) { Rectangle().fill(GoHomeTheme.ginger).frame(width: 2) }
            }
        }
    }

    private var metaText: String {
        let formatter = ISO8601DateFormatter()
        let dateFormatter = DateFormatter()
        dateFormatter.locale = Locale(identifier: "zh_CN")
        dateFormatter.dateFormat = "yyyy年M月d日"
        let date = formatter.date(from: memory.happenedAt).map(dateFormatter.string) ?? ""
        return [date, memory.locationName].filter { !$0.isEmpty }.joined(separator: " · ")
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
                    AuthenticatedMemoryImage(path: item.imageURL, apiClient: apiClient)
                        .aspectRatio(MemoryMediaLayout.aspectRatio(for: visibleMedia.count), contentMode: .fill)
                        .frame(maxWidth: .infinity)
                        .clipped()
                        .clipShape(RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("查看第 \(index + 1) 张照片")
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
                    AuthenticatedMemoryImage(path: item.imageURL, apiClient: apiClient, contentMode: .fit)
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
    var contentMode: ContentMode = .fill
    @State private var image: UIImage?

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
        .task(id: path) {
            guard !path.isEmpty else { return }
            if let cached = MemoryImageCache.shared.image(for: path) {
                image = cached
                return
            }
            guard let apiClient, let data = try? await apiClient.data(path: path), let loaded = UIImage(data: data) else { return }
            MemoryImageCache.shared.insert(loaded, for: path)
            image = loaded
        }
    }
}

private final class MemoryImageCache {
    static let shared = MemoryImageCache()
    private let cache = NSCache<NSString, UIImage>()

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
}

private struct MemoryComposer: View {
    let memory: FamilyMemory?
    @ObservedObject var model: MemoryViewModel
    let apiClient: APIClient?
    @Binding var isPresented: Bool
    @State private var bodyText: String
    @State private var locationName: String
    @State private var peopleText: String
    @State private var happenedAt: Date
    @State private var pickerItems: [PhotosPickerItem] = []
    @State private var imageData: [Data] = []
    @State private var retainedMedia: [MemoryMedia]
    @State private var isPreparingImages = false

    init(memory: FamilyMemory?, model: MemoryViewModel, apiClient: APIClient?, isPresented: Binding<Bool>) {
        self.memory = memory
        self.model = model
        self.apiClient = apiClient
        _isPresented = isPresented
        _bodyText = State(initialValue: memory?.body ?? "")
        _locationName = State(initialValue: memory?.locationName ?? "")
        _peopleText = State(initialValue: memory?.people.joined(separator: "、") ?? "")
        _happenedAt = State(initialValue: memory.flatMap { ISO8601DateFormatter().date(from: $0.happenedAt) } ?? Date())
        _retainedMedia = State(initialValue: memory?.media ?? [])
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    TextEditor(text: $bodyText)
                        .font(.system(size: 18))
                        .scrollContentBackground(.hidden)
                        .frame(minHeight: 150)
                        .padding(12)
                        .background(Color.black.opacity(0.035), in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
                    if !retainedMedia.isEmpty || !imageData.isEmpty {
                        MemoryComposerMediaGrid(
                            retainedMedia: $retainedMedia,
                            newImageData: $imageData,
                            apiClient: apiClient
                        )
                    }
                    if retainedMedia.count < 9 {
                        PhotosPicker(selection: $pickerItems, maxSelectionCount: 9 - retainedMedia.count, matching: .images) {
                            Label(photoPickerTitle, systemImage: "photo.on.rectangle.angled")
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundStyle(GoHomeTheme.ink)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(14)
                                .background(GoHomeTheme.paleGinger.opacity(0.55), in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
                        }
                        .allowsHitTesting(!isPreparingImages)
                    }
                    DatePicker("发生时间", selection: $happenedAt)
                    TextField("地点（选填）", text: $locationName)
                        .textFieldStyle(.roundedBorder)
                    TextField("人物，用顿号分隔（选填）", text: $peopleText)
                        .textFieldStyle(.roundedBorder)
                }
                .padding(GoHomeTheme.pageHorizontalPadding)
            }
            .background(GoHomeTheme.paper)
            .navigationTitle(memory == nil ? "新记忆" : "编辑记忆")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("取消") { isPresented = false } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(model.isPublishing ? "保存中" : "发布") { publish() }
                        .fontWeight(.bold)
                        .disabled(isPreparingImages || model.isPublishing || (bodyText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && imageData.isEmpty && retainedMedia.isEmpty))
                }
            }
            .onChange(of: pickerItems) { items in
                isPreparingImages = true
                Task {
                    let prepared = await MemoryImageProcessor.prepare(items: items)
                    guard !Task.isCancelled else { return }
                    imageData = prepared
                    isPreparingImages = false
                }
            }
        }
    }

    private var photoPickerTitle: String {
        if isPreparingImages { return "正在处理照片" }
        return imageData.isEmpty ? "添加照片" : "已选择 \(imageData.count) 张"
    }

    private func publish() {
        let people = peopleText
            .components(separatedBy: CharacterSet(charactersIn: "、,，"))
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        Task {
            let saved = await model.save(
                existing: memory,
                body: bodyText,
                happenedAt: happenedAt,
                locationName: locationName,
                people: people,
                retainedMediaIDs: retainedMedia.map(\.assetID),
                newImages: imageData.map { ($0, "image/jpeg") }
            )
            if saved { isPresented = false }
        }
    }
}

private struct MemoryComposerMediaGrid: View {
    @Binding var retainedMedia: [MemoryMedia]
    @Binding var newImageData: [Data]
    let apiClient: APIClient?

    var body: some View {
        let count = min(9, retainedMedia.count + newImageData.count)
        let columns = Array(
            repeating: GridItem(.flexible(), spacing: MemoryMediaLayout.spacing),
            count: MemoryMediaLayout.columnCount(for: count)
        )
        LazyVGrid(columns: columns, spacing: MemoryMediaLayout.spacing) {
            ForEach(Array(retainedMedia.enumerated()), id: \.element.id) { index, media in
                mediaTile(index: index, count: count) {
                    AuthenticatedMemoryImage(path: media.imageURL, apiClient: apiClient)
                } onRemove: {
                    retainedMedia.removeAll { $0.id == media.id }
                }
            }
            ForEach(Array(newImageData.enumerated()), id: \.offset) { index, data in
                mediaTile(index: retainedMedia.count + index, count: count) {
                    if let image = UIImage(data: data) {
                        Image(uiImage: image).resizable().scaledToFill()
                    }
                } onRemove: {
                    guard newImageData.indices.contains(index) else { return }
                    newImageData.remove(at: index)
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
            content()
                .aspectRatio(MemoryMediaLayout.aspectRatio(for: count), contentMode: .fill)
                .frame(maxWidth: .infinity)
                .clipped()
                .background(Color.black.opacity(0.04))
                .clipShape(RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
            Button(action: onRemove) {
                Image(systemName: "xmark")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(.white)
                    .frame(width: 26, height: 26)
                    .background(.black.opacity(0.72), in: Circle())
            }
            .buttonStyle(.plain)
            .padding(6)
            .accessibilityLabel("移除第 \(index + 1) 张照片")
        }
    }
}

private enum MemoryImageProcessor {
    static func prepare(items: [PhotosPickerItem]) async -> [Data] {
        await withTaskGroup(of: (Int, Data?).self) { group in
            for (index, item) in items.prefix(9).enumerated() {
                group.addTask {
                    guard let source = try? await item.loadTransferable(type: Data.self) else { return (index, nil) }
                    let jpeg = await Task.detached(priority: .userInitiated) { downsampledJPEG(source) }.value
                    return (index, jpeg)
                }
            }
            var ordered = Array<Data?>(repeating: nil, count: min(9, items.count))
            for await (index, data) in group { ordered[index] = data }
            return ordered.compactMap { $0 }
        }
    }

    private static func downsampledJPEG(_ data: Data) -> Data? {
        let options = [kCGImageSourceShouldCache: false] as CFDictionary
        guard let source = CGImageSourceCreateWithData(data as CFData, options) else { return nil }
        let thumbnailOptions = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: 1920,
            kCGImageSourceShouldCacheImmediately: true,
        ] as CFDictionary
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, thumbnailOptions) else { return nil }
        return UIImage(cgImage: image).jpegData(compressionQuality: 0.8)
    }
}

private struct MemoryCommentComposer: View {
    let memory: FamilyMemory
    @ObservedObject var model: MemoryViewModel
    @Binding var isPresented: Bool
    @State private var bodyText = ""

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 16) {
                Text(memory.body)
                    .font(.system(size: 15))
                    .foregroundStyle(GoHomeTheme.mutedInk)
                    .lineLimit(3)
                TextEditor(text: $bodyText)
                    .font(.system(size: 17))
                    .scrollContentBackground(.hidden)
                    .padding(10)
                    .background(Color.black.opacity(0.035), in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
                Spacer()
            }
            .padding(GoHomeTheme.pageHorizontalPadding)
            .navigationTitle("回应")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("取消") { isPresented = false } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("发布") {
                        Task {
                            if await model.addComment(bodyText, to: memory) { isPresented = false }
                        }
                    }
                    .fontWeight(.bold)
                    .disabled(bodyText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
        .presentationDetents([.medium])
    }
}
