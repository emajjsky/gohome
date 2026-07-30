import PhotosUI
import SwiftUI
import UniformTypeIdentifiers
import UIKit

enum MemoryPickedMediaKind: Equatable, Sendable {
    case image
    case video
}

enum MemoryLibrarySelectionMode: Equatable {
    case images
    case video

    var selectionLimit: Int {
        switch self {
        case .images: MemoryMediaPolicy.maximumImageCount
        case .video: 1
        }
    }

    var kind: MemoryPickedMediaKind {
        switch self {
        case .images: .image
        case .video: .video
        }
    }
}

struct MemoryPickedMedia: Identifiable, Sendable {
    let id = UUID()
    let kind: MemoryPickedMediaKind
    let localURL: URL
}

struct MemoryComposerSeed: Sendable {
    let media: [MemoryPickedMedia]

    static let empty = MemoryComposerSeed(media: [])

    func removeStagedFiles() {
        media.forEach { try? FileManager.default.removeItem(at: $0.localURL) }
    }
}

struct MemoryComposerRequest: Identifiable, Sendable {
    let id: UUID
    let memory: FamilyMemory?
    let seed: MemoryComposerSeed

    init(id: UUID = UUID(), memory: FamilyMemory?, seed: MemoryComposerSeed) {
        self.id = id
        self.memory = memory
        self.seed = seed
    }
}

struct MemoryComposerPresentationState {
    private(set) var activeRequest: MemoryComposerRequest?
    private(set) var pendingRequest: MemoryComposerRequest?

    mutating func stage(_ media: [MemoryPickedMedia]) {
        discardPending()
        pendingRequest = MemoryComposerRequest(
            memory: nil,
            seed: MemoryComposerSeed(media: media)
        )
    }

    mutating func promotePending() {
        guard activeRequest == nil, let pendingRequest else { return }
        activeRequest = pendingRequest
        self.pendingRequest = nil
    }

    mutating func presentEditor(for memory: FamilyMemory) {
        discardPending()
        activeRequest = MemoryComposerRequest(memory: memory, seed: .empty)
    }

    mutating func dismissActive() {
        activeRequest = nil
    }

    mutating func discardPending() {
        pendingRequest?.seed.removeStagedFiles()
        pendingRequest = nil
    }
}

enum MemoryMediaSelectionPolicy {
    static func accepts(_ kinds: [MemoryPickedMediaKind]) -> Bool {
        guard !kinds.isEmpty else { return false }
        if kinds.contains(.video) {
            return kinds.count == 1 && kinds[0] == .video
        }
        return kinds.count <= MemoryMediaPolicy.maximumImageCount
    }
}

enum MemoryMediaPickerError: LocalizedError {
    case cameraUnavailable
    case invalidSelection
    case failedToRead

    var errorDescription: String? {
        switch self {
        case .cameraUnavailable: "当前设备无法使用相机"
        case .invalidSelection: "一次可选择最多 9 张照片，或 1 个视频"
        case .failedToRead: "部分内容无法读取，请重新选择"
        }
    }
}

struct MemoryLibraryPicker: UIViewControllerRepresentable {
    let mode: MemoryLibrarySelectionMode
    let onComplete: ([MemoryPickedMedia]) -> Void
    let onCancel: () -> Void
    let onError: (String) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(mode: mode, onComplete: onComplete, onCancel: onCancel, onError: onError)
    }

    func makeUIViewController(context: Context) -> PHPickerViewController {
        var configuration = PHPickerConfiguration(photoLibrary: .shared())
        configuration.filter = mode == .images ? .images : .videos
        configuration.selection = .ordered
        configuration.selectionLimit = mode.selectionLimit
        configuration.preferredAssetRepresentationMode = .current
        let picker = PHPickerViewController(configuration: configuration)
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: PHPickerViewController, context: Context) {}

    final class Coordinator: NSObject, PHPickerViewControllerDelegate {
        private let mode: MemoryLibrarySelectionMode
        private let onComplete: ([MemoryPickedMedia]) -> Void
        private let onCancel: () -> Void
        private let onError: (String) -> Void

        init(
            mode: MemoryLibrarySelectionMode,
            onComplete: @escaping ([MemoryPickedMedia]) -> Void,
            onCancel: @escaping () -> Void,
            onError: @escaping (String) -> Void
        ) {
            self.mode = mode
            self.onComplete = onComplete
            self.onCancel = onCancel
            self.onError = onError
        }

        func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
            guard !results.isEmpty else {
                onCancel()
                return
            }

            let selections = results.compactMap { Self.selection(from: $0, mode: mode) }
            let kinds = selections.map(\.kind)
            guard selections.count == results.count, MemoryMediaSelectionPolicy.accepts(kinds) else {
                onError(MemoryMediaPickerError.invalidSelection.localizedDescription)
                return
            }

            let group = DispatchGroup()
            let storageQueue = DispatchQueue(label: "com.gohome.memory-picker.results")
            var staged = Array<MemoryPickedMedia?>(repeating: nil, count: selections.count)

            for (index, selection) in selections.enumerated() {
                group.enter()
                Self.stage(selection) { localURL in
                    defer { group.leave() }
                    guard let localURL else { return }
                    storageQueue.sync {
                        staged[index] = MemoryPickedMedia(kind: selection.kind, localURL: localURL)
                    }
                }
            }

            group.notify(queue: .main) { [onComplete, onError] in
                let media = staged.compactMap { $0 }
                guard media.count == selections.count else {
                    media.forEach { try? FileManager.default.removeItem(at: $0.localURL) }
                    onError(MemoryMediaPickerError.failedToRead.localizedDescription)
                    return
                }
                onComplete(media)
            }
        }

        private struct Selection {
            let provider: NSItemProvider
            let kind: MemoryPickedMediaKind
            let typeIdentifier: String
        }

        private static func selection(from result: PHPickerResult, mode: MemoryLibrarySelectionMode) -> Selection? {
            let provider = result.itemProvider
            let requiredType: UTType = mode == .images ? .image : .movie
            guard let type = provider.registeredTypeIdentifiers.first(where: {
                UTType($0)?.conforms(to: requiredType) == true
            }) else { return nil }
            return Selection(provider: provider, kind: mode.kind, typeIdentifier: type)
        }

        private static func stage(_ selection: Selection, completion: @escaping (URL?) -> Void) {
            if selection.kind == .image {
                selection.provider.loadDataRepresentation(forTypeIdentifier: selection.typeIdentifier) { data, _ in
                    guard let data else {
                        completion(nil)
                        return
                    }
                    completion(try? writeImageDataToTemporaryStorage(data, typeIdentifier: selection.typeIdentifier))
                }
                return
            }

            selection.provider.loadFileRepresentation(forTypeIdentifier: selection.typeIdentifier) { url, _ in
                guard let url else {
                    completion(nil)
                    return
                }
                completion(try? copyToTemporaryStorage(url, kind: selection.kind))
            }
        }

        private static func writeImageDataToTemporaryStorage(_ data: Data, typeIdentifier: String) throws -> URL {
            let pathExtension = UTType(typeIdentifier)?.preferredFilenameExtension ?? "jpg"
            let destination = FileManager.default.temporaryDirectory
                .appendingPathComponent("memory-selection-\(UUID().uuidString)")
                .appendingPathExtension(pathExtension)
            try data.write(to: destination, options: .atomic)
            return destination
        }

        private static func copyToTemporaryStorage(_ source: URL, kind: MemoryPickedMediaKind) throws -> URL {
            let fallbackExtension = kind == .video ? "mov" : "jpg"
            let pathExtension = source.pathExtension.isEmpty ? fallbackExtension : source.pathExtension
            let destination = FileManager.default.temporaryDirectory
                .appendingPathComponent("memory-selection-\(UUID().uuidString)")
                .appendingPathExtension(pathExtension)
            try FileManager.default.copyItem(at: source, to: destination)
            return destination
        }
    }
}

struct MemoryCameraPicker: UIViewControllerRepresentable {
    static var isAvailable: Bool { UIImagePickerController.isSourceTypeAvailable(.camera) }

    let onComplete: (MemoryPickedMedia) -> Void
    let onCancel: () -> Void
    let onError: (String) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onComplete: onComplete, onCancel: onCancel, onError: onError)
    }

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.mediaTypes = [UTType.image.identifier, UTType.movie.identifier]
        picker.videoMaximumDuration = MemoryMediaPolicy.maximumVideoDuration
        picker.videoQuality = .typeHigh
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    final class Coordinator: NSObject, UINavigationControllerDelegate, UIImagePickerControllerDelegate {
        private let onComplete: (MemoryPickedMedia) -> Void
        private let onCancel: () -> Void
        private let onError: (String) -> Void

        init(
            onComplete: @escaping (MemoryPickedMedia) -> Void,
            onCancel: @escaping () -> Void,
            onError: @escaping (String) -> Void
        ) {
            self.onComplete = onComplete
            self.onCancel = onCancel
            self.onError = onError
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            onCancel()
        }

        func imagePickerController(
            _ picker: UIImagePickerController,
            didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]
        ) {
            if let source = info[.mediaURL] as? URL {
                finishCopying(source, kind: .video, fallbackExtension: "mov")
                return
            }
            guard let image = info[.originalImage] as? UIImage,
                  let data = image.jpegData(compressionQuality: 0.92) else {
                onError(MemoryMediaPickerError.failedToRead.localizedDescription)
                return
            }
            let destination = FileManager.default.temporaryDirectory
                .appendingPathComponent("memory-camera-\(UUID().uuidString)")
                .appendingPathExtension("jpg")
            do {
                try data.write(to: destination, options: .atomic)
                onComplete(MemoryPickedMedia(kind: .image, localURL: destination))
            } catch {
                onError(MemoryMediaPickerError.failedToRead.localizedDescription)
            }
        }

        private func finishCopying(_ source: URL, kind: MemoryPickedMediaKind, fallbackExtension: String) {
            let pathExtension = source.pathExtension.isEmpty ? fallbackExtension : source.pathExtension
            let destination = FileManager.default.temporaryDirectory
                .appendingPathComponent("memory-camera-\(UUID().uuidString)")
                .appendingPathExtension(pathExtension)
            do {
                try FileManager.default.copyItem(at: source, to: destination)
                onComplete(MemoryPickedMedia(kind: kind, localURL: destination))
            } catch {
                onError(MemoryMediaPickerError.failedToRead.localizedDescription)
            }
        }
    }
}
