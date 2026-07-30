import AVFoundation
import ImageIO
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
        case .tooLarge: return "视频压缩后仍超过 24 MB，请裁剪后重试"
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

enum MemoryVideoCompressionPlan {
    static func presets(for durationSeconds: Double) -> [String] {
        if durationSeconds <= 18 {
            return [AVAssetExportPreset1280x720, AVAssetExportPresetMediumQuality, AVAssetExportPresetLowQuality]
        }
        return [AVAssetExportPresetMediumQuality, AVAssetExportPresetLowQuality]
    }
}

enum MemoryVideoProcessor {
    static func prepare(sourceURL: URL) async throws -> PreparedMemoryVideo {
        let sourceAsset = AVURLAsset(url: sourceURL)
        let sourceDuration = try await sourceAsset.load(.duration)
        let durationSeconds = CMTimeGetSeconds(sourceDuration)
        guard durationSeconds.isFinite, durationSeconds > 0 else {
            throw MemoryVideoPreparationError.unavailable
        }
        guard durationSeconds <= MemoryMediaPolicy.maximumVideoDuration + 0.05 else {
            throw MemoryVideoPreparationError.tooLong
        }

        let outputURL = try await exportWithinSizeLimit(
            asset: sourceAsset,
            presets: MemoryVideoCompressionPlan.presets(for: durationSeconds)
        )
        defer { try? FileManager.default.removeItem(at: outputURL) }

        let data = try Data(contentsOf: outputURL, options: .mappedIfSafe)
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

    private static func exportWithinSizeLimit(asset: AVAsset, presets: [String]) async throws -> URL {
        var completedOversizedExport = false

        for preset in presets {
            let outputURL = FileManager.default.temporaryDirectory
                .appendingPathComponent("memory-video-\(UUID().uuidString)")
                .appendingPathExtension("mp4")
            guard let exporter = AVAssetExportSession(asset: asset, presetName: preset),
                  exporter.supportedFileTypes.contains(.mp4) else {
                continue
            }
            exporter.outputURL = outputURL
            exporter.outputFileType = .mp4
            exporter.shouldOptimizeForNetworkUse = true
            await withCheckedContinuation { continuation in
                exporter.exportAsynchronously { continuation.resume() }
            }
            guard exporter.status == .completed else {
                try? FileManager.default.removeItem(at: outputURL)
                continue
            }

            let fileSize = (try? outputURL.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? Int.max
            if fileSize <= MemoryMediaPolicy.maximumVideoBytes {
                return outputURL
            }
            completedOversizedExport = true
            try? FileManager.default.removeItem(at: outputURL)
        }

        throw completedOversizedExport ? MemoryVideoPreparationError.tooLarge : MemoryVideoPreparationError.exportFailed
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

enum MemoryImageProcessor {
    static func prepare(sourceURL: URL) async -> MemoryUploadAsset? {
        await Task.detached(priority: .userInitiated) {
            guard let source = CGImageSourceCreateWithURL(sourceURL as CFURL, [
                kCGImageSourceShouldCache: false,
            ] as CFDictionary) else { return nil }
            return downsampledJPEG(source)
        }.value
    }

    private static func downsampledJPEG(_ source: CGImageSource) -> MemoryUploadAsset? {
        let thumbnailOptions = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: 1280,
            kCGImageSourceShouldCacheImmediately: true,
        ] as CFDictionary
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, thumbnailOptions) else { return nil }
        guard let jpeg = UIImage(cgImage: image).jpegData(compressionQuality: 0.7) else { return nil }
        return MemoryUploadAsset(
            data: jpeg,
            contentType: "image/jpeg",
            pixelWidth: image.width,
            pixelHeight: image.height,
            durationSeconds: nil
        )
    }
}
