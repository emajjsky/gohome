import AVFoundation
import CryptoKit
import Foundation
import UIKit

@MainActor
final class MemoryVideoPlaybackStore {
    typealias PosterGenerator = @Sendable (URL) async -> Data?

    static let shared = MemoryVideoPlaybackStore()

    private struct PlaybackCredential {
        let url: URL
        let expiresAt: Date
    }

    private let posterCache = NSCache<NSString, UIImage>()
    private let cacheDirectory: URL
    private let posterGenerator: PosterGenerator
    private var credentials: [String: PlaybackCredential] = [:]
    private var credentialTasks: [String: Task<PlaybackCredential, Error>] = [:]
    private var posterTasks: [String: Task<Data?, Never>] = [:]

    init(cacheDirectory: URL? = nil, posterGenerator: PosterGenerator? = nil) {
        self.cacheDirectory = cacheDirectory ?? Self.defaultCacheDirectory()
        self.posterGenerator = posterGenerator ?? { url in
            await Self.generatePosterData(url: url)
        }
        posterCache.countLimit = 30
        posterCache.totalCostLimit = 24 * 1024 * 1024
        try? FileManager.default.createDirectory(
            at: self.cacheDirectory,
            withIntermediateDirectories: true
        )
    }

    func playbackURL(assetID: String, apiClient: APIClient?) async throws -> URL {
        guard !assetID.isEmpty, let apiClient else { throw APIError.invalidResponse }
        try Task.checkCancellation()

        if let credential = credentials[assetID], credential.expiresAt.timeIntervalSinceNow > 30 {
            return credential.url
        }
        credentials[assetID] = nil

        if let task = credentialTasks[assetID] {
            return try await task.value.url
        }

        let task = Task<PlaybackCredential, Error> {
            let response = try await apiClient.send(Endpoint<MemoryMediaPlaybackResponse>(
                path: "/api/v2/memory-media-playback/\(assetID)"
            ))
            guard
                let url = URL(string: response.url),
                url.scheme == "https",
                let expiresAt = Self.parseDate(response.expiresAt),
                expiresAt.timeIntervalSinceNow > 30
            else {
                throw APIError.invalidResponse
            }
            return PlaybackCredential(url: url, expiresAt: expiresAt)
        }
        credentialTasks[assetID] = task

        do {
            let credential = try await task.value
            credentialTasks[assetID] = nil
            credentials[assetID] = credential
            return credential.url
        } catch {
            credentialTasks[assetID] = nil
            throw error
        }
    }

    func poster(assetID: String, apiClient: APIClient?) async -> UIImage? {
        guard !assetID.isEmpty else { return nil }
        if let cached = posterCache.object(forKey: assetID as NSString) { return cached }

        if let task = posterTasks[assetID] {
            return await decodeAndCache(await task.value, assetID: assetID)
        }

        let diskURL = posterFileURL(assetID: assetID)
        let generator = posterGenerator
        let task = Task<Data?, Never> {
            if let data = await Task.detached(priority: .utility, operation: {
                try? Data(contentsOf: diskURL, options: .mappedIfSafe)
            }).value {
                return data
            }

            guard
                let playbackURL = try? await self.playbackURL(assetID: assetID, apiClient: apiClient),
                let data = await generator(playbackURL)
            else {
                return nil
            }

            await Task.detached(priority: .utility) {
                try? FileManager.default.createDirectory(
                    at: diskURL.deletingLastPathComponent(),
                    withIntermediateDirectories: true
                )
                try? data.write(
                    to: diskURL,
                    options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication]
                )
            }.value
            return data
        }
        posterTasks[assetID] = task
        let data = await task.value
        posterTasks[assetID] = nil
        return await decodeAndCache(data, assetID: assetID)
    }

    func insert(_ image: UIImage, assetID: String) {
        guard !assetID.isEmpty else { return }
        insertIntoMemory(image, assetID: assetID)
        guard let data = image.jpegData(compressionQuality: 0.82) else { return }
        let diskURL = posterFileURL(assetID: assetID)
        Task.detached(priority: .utility) {
            try? FileManager.default.createDirectory(
                at: diskURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            try? data.write(
                to: diskURL,
                options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication]
            )
        }
    }

    private func decodeAndCache(_ data: Data?, assetID: String) async -> UIImage? {
        guard let data else { return nil }
        let image = await Task.detached(priority: .userInitiated) { UIImage(data: data) }.value
        if let image { insertIntoMemory(image, assetID: assetID) }
        return image
    }

    private func insertIntoMemory(_ image: UIImage, assetID: String) {
        let cost = Int(image.size.width * image.size.height * image.scale * image.scale * 4)
        posterCache.setObject(image, forKey: assetID as NSString, cost: cost)
    }

    private func posterFileURL(assetID: String) -> URL {
        let digest = SHA256.hash(data: Data(assetID.utf8)).map { String(format: "%02x", $0) }.joined()
        return cacheDirectory.appendingPathComponent("\(digest).jpg", isDirectory: false)
    }

    private static func defaultCacheDirectory() -> URL {
        let root = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        return root.appendingPathComponent("MemoryVideoPosters", isDirectory: true)
    }

    private static func parseDate(_ value: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractional.date(from: value) { return date }
        return ISO8601DateFormatter().date(from: value)
    }

    nonisolated private static func generatePosterData(url: URL) async -> Data? {
        await Task.detached(priority: .utility) {
            let asset = AVURLAsset(
                url: url,
                options: [AVURLAssetPreferPreciseDurationAndTimingKey: false]
            )
            let generator = AVAssetImageGenerator(asset: asset)
            generator.appliesPreferredTrackTransform = true
            generator.maximumSize = CGSize(width: 960, height: 960)
            generator.requestedTimeToleranceBefore = .positiveInfinity
            generator.requestedTimeToleranceAfter = .positiveInfinity
            let time = CMTime(seconds: 0.1, preferredTimescale: 600)
            guard let image = try? generator.copyCGImage(at: time, actualTime: nil) else { return nil }
            return UIImage(cgImage: image).jpegData(compressionQuality: 0.82)
        }.value
    }
}
