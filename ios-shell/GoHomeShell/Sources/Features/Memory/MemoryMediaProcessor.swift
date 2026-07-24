import AVFoundation
import CoreTransferable
import PhotosUI
import SwiftUI
import UniformTypeIdentifiers
import UIKit

struct PreparedMemoryVideo: Sendable {
    let upload: MemoryUploadAsset
    let preview: UIImage?
}

enum MemoryVideoPreparationError: LocalizedError {
    case unavailable
    case tooLong
    case tooLarge
    case exportFailed

    var errorDescription: String? {
        switch self {
        case .unavailable: return "无法读取这个视频"
        case .tooLong: return "视频需控制在 60 秒以内"
        case .tooLarge: return "视频压缩后仍然过大，请选择更短的视频"
        case .exportFailed: return "视频处理失败，请重新选择"
        }
    }
}

enum MemoryMediaPolicy {
    static let maximumImageCount = 9
    static let maximumVideoDuration: Double = 60
    static let maximumVideoBytes = 24 * 1024 * 1024

    static func accepts(retained: [MemoryMedia], newMedia: [MemoryUploadAsset]) -> Bool {
        let retainedVideoCount = retained.filter(\.isVideo).count
        let newVideoCount = newMedia.filter(\.isVideo).count
        let total = retained.count + newMedia.count
        if retainedVideoCount + newVideoCount > 0 {
            return retainedVideoCount + newVideoCount == 1 && total == 1
        }
        return total <= maximumImageCount
    }
}

enum MemoryVideoProcessor {
    static func prepare(item: PhotosPickerItem) async throws -> PreparedMemoryVideo {
        guard let imported = try await item.loadTransferable(type: ImportedMemoryVideo.self) else {
            throw MemoryVideoPreparationError.unavailable
        }
        defer { try? FileManager.default.removeItem(at: imported.url) }

        let sourceAsset = AVURLAsset(url: imported.url)
        let sourceDuration = try await sourceAsset.load(.duration)
        let durationSeconds = CMTimeGetSeconds(sourceDuration)
        guard durationSeconds.isFinite, durationSeconds > 0 else {
            throw MemoryVideoPreparationError.unavailable
        }
        guard durationSeconds <= MemoryMediaPolicy.maximumVideoDuration + 0.05 else {
            throw MemoryVideoPreparationError.tooLong
        }

        let outputURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("memory-video-\(UUID().uuidString)")
            .appendingPathExtension("mp4")
        defer { try? FileManager.default.removeItem(at: outputURL) }
        guard let exporter = AVAssetExportSession(asset: sourceAsset, presetName: AVAssetExportPreset1280x720) else {
            throw MemoryVideoPreparationError.exportFailed
        }
        exporter.outputURL = outputURL
        exporter.outputFileType = AVFileType.mp4
        exporter.shouldOptimizeForNetworkUse = true
        await withCheckedContinuation { continuation in
            exporter.exportAsynchronously { continuation.resume() }
        }
        guard exporter.status == AVAssetExportSession.Status.completed else {
            throw MemoryVideoPreparationError.exportFailed
        }

        let data = try Data(contentsOf: outputURL, options: .mappedIfSafe)
        guard data.count <= MemoryMediaPolicy.maximumVideoBytes else {
            throw MemoryVideoPreparationError.tooLarge
        }
        let exportedAsset = AVURLAsset(url: outputURL)
        let dimensions = try await videoDimensions(asset: exportedAsset)
        let preview = firstFrame(asset: exportedAsset)
        return PreparedMemoryVideo(
            upload: MemoryUploadAsset(
                data: data,
                contentType: "video/mp4",
                pixelWidth: dimensions.width,
                pixelHeight: dimensions.height,
                durationSeconds: durationSeconds
            ),
            preview: preview
        )
    }

    private static func videoDimensions(asset: AVAsset) async throws -> (width: Int, height: Int) {
        guard let track = try await asset.loadTracks(withMediaType: .video).first else { return (0, 0) }
        let size = try await track.load(.naturalSize)
        let transform = try await track.load(.preferredTransform)
        let transformed = size.applying(transform)
        return (Int(abs(transformed.width).rounded()), Int(abs(transformed.height).rounded()))
    }

    private static func firstFrame(asset: AVAsset) -> UIImage? {
        let generator = AVAssetImageGenerator(asset: asset)
        generator.appliesPreferredTrackTransform = true
        generator.maximumSize = CGSize(width: 960, height: 960)
        guard let image = try? generator.copyCGImage(at: .zero, actualTime: nil) else { return nil }
        return UIImage(cgImage: image)
    }
}

private struct ImportedMemoryVideo: Transferable {
    let url: URL

    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(contentType: .movie) { video in
            SentTransferredFile(video.url)
        } importing: { received in
            let destination = FileManager.default.temporaryDirectory
                .appendingPathComponent("memory-source-\(UUID().uuidString)")
                .appendingPathExtension(received.file.pathExtension.isEmpty ? "mov" : received.file.pathExtension)
            try FileManager.default.copyItem(at: received.file, to: destination)
            return ImportedMemoryVideo(url: destination)
        }
    }
}
