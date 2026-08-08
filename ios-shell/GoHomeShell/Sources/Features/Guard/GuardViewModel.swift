import Foundation

enum GuardStreamState: Equatable {
    case idle
    case connecting
    case waiting(String)
    case playing
    case failed(String)
}

struct FrameRateMeter: Sendable {
    private let windowSeconds: TimeInterval
    private var samples: [TimeInterval] = []

    init(windowSeconds: TimeInterval = 2) {
        self.windowSeconds = max(0.5, windowSeconds)
    }

    mutating func record(at timestamp: TimeInterval) -> Double {
        samples.append(timestamp)
        return current(at: timestamp)
    }

    mutating func current(at timestamp: TimeInterval) -> Double {
        let cutoff = timestamp - windowSeconds
        samples.removeAll { $0 < cutoff }
        guard let first = samples.first, let last = samples.last, samples.count > 1, last > first else {
            return 0
        }
        return Double(samples.count - 1) / (last - first)
    }

    mutating func reset() {
        samples.removeAll(keepingCapacity: true)
    }
}

@MainActor
final class GuardViewModel: ObservableObject {
    @Published private(set) var selectedCameraID: String?
    @Published private(set) var videoSurface: WebRTCVideoSurface?
    @Published private(set) var displayFPS: Double = 0
    @Published private(set) var streamState: GuardStreamState = .idle
    @Published private(set) var selectedPrivacyMode: VideoPrivacyMode
    @Published private(set) var privacyPolicy: VideoPrivacyPolicy?
    @Published private(set) var privacyUpdateInFlight = false
    @Published private(set) var privacyError: String?

    private let streamClient: CameraStreamClient
    private let privacyService: (any VideoPrivacyServicing)?
    private let familyID: String?
    private let frameTimeoutNanoseconds: UInt64
    private let reconnectDelayNanoseconds: UInt64
    private let maxReconnectAttempts: Int
    private let recoveryRetryDelayNanoseconds: UInt64
    private var frameTask: Task<Void, Never>?
    private var privacySyncTask: Task<Void, Never>?
    private var selectionGeneration = 0
    private var lastFrameAt = Date.distantPast
    private var currentSessionReceivedFrame = false
    private var frameRateMeter = FrameRateMeter()

    init(
        streamClient: CameraStreamClient,
        privacyService: (any VideoPrivacyServicing)? = nil,
        familyID: String? = nil,
        initialPrivacyMode: VideoPrivacyMode = .original,
        frameTimeoutNanoseconds: UInt64 = 4_000_000_000,
        reconnectDelayNanoseconds: UInt64 = 500_000_000,
        maxReconnectAttempts: Int = 4,
        recoveryRetryDelayNanoseconds: UInt64 = 5_000_000_000
    ) {
        self.streamClient = streamClient
        self.privacyService = privacyService
        self.familyID = familyID
        self.selectedPrivacyMode = initialPrivacyMode
        self.frameTimeoutNanoseconds = frameTimeoutNanoseconds
        self.reconnectDelayNanoseconds = reconnectDelayNanoseconds
        self.maxReconnectAttempts = maxReconnectAttempts
        self.recoveryRetryDelayNanoseconds = recoveryRetryDelayNanoseconds
    }

    func select(cameraID: String, profile: String = "mobile") {
        if selectedCameraID == cameraID {
            switch streamState {
            case .connecting, .waiting, .playing:
                return
            case .idle, .failed:
                break
            }
        }
        startStream(cameraID: cameraID, profile: profile)
    }

    private func startStream(cameraID: String, profile: String) {
        selectionGeneration += 1
        let generation = selectionGeneration
        frameTask?.cancel()
        selectedCameraID = cameraID
        videoSurface = nil
        frameRateMeter.reset()
        displayFPS = 0
        streamState = .connecting
        let privacyMode = selectedPrivacyMode
        frameTask = Task { [weak self, streamClient] in
            await streamClient.stop()
            guard
                let self,
                !Task.isCancelled,
                generation == self.selectionGeneration
            else { return }
            var failedAttempts = 0
            while !Task.isCancelled, generation == self.selectionGeneration {
                do {
                    try await self.consumeSession(
                        cameraID: cameraID,
                        profile: profile,
                        privacyMode: privacyMode,
                        generation: generation
                    )
                    guard !Task.isCancelled, generation == self.selectionGeneration else { return }
                    throw URLError(.networkConnectionLost)
                } catch is CancellationError {
                    return
                } catch {
                    guard generation == self.selectionGeneration, !Task.isCancelled else { return }
                    if self.currentSessionReceivedFrame {
                        failedAttempts = 0
                    }
                    failedAttempts += 1
                    self.frameRateMeter.reset()
                    self.displayFPS = 0
                    let immediateRetry = failedAttempts <= self.maxReconnectAttempts
                    self.videoSurface = nil
                    self.streamState = self.recoveryState(for: error)
                    do {
                        let delay = immediateRetry
                            ? self.reconnectDelayNanoseconds
                            : self.recoveryDelayNanoseconds(after: failedAttempts)
                        try await Task.sleep(nanoseconds: delay)
                    } catch {
                        return
                    }
                }
            }
        }
    }

    private func recoveryDelayNanoseconds(after failedAttempts: Int) -> UInt64 {
        let recoveryAttempt = max(0, failedAttempts - maxReconnectAttempts - 1)
        let multiplier = UInt64(1 << min(recoveryAttempt, 3))
        let cappedDelay = recoveryRetryDelayNanoseconds.multipliedReportingOverflow(by: multiplier)
        return cappedDelay.overflow
            ? 30_000_000_000
            : min(cappedDelay.partialValue, 30_000_000_000)
    }

    private func recoveryState(for error: Error) -> GuardStreamState {
        if case let APIError.server(statusCode, detail) = error, statusCode == 409 {
            return .waiting(detail)
        }
        return .connecting
    }

    private func consumeSession(
        cameraID: String,
        profile: String,
        privacyMode: VideoPrivacyMode,
        generation: Int
    ) async throws {
        currentSessionReceivedFrame = false
        frameRateMeter.reset()
        displayFPS = 0
        let streams = try await streamClient.streams(
            cameraID: cameraID,
            profile: profile,
            privacyMode: privacyMode
        )
        videoSurface = streams.surface
        lastFrameAt = Date()
        let meterRefreshNanoseconds = min(frameTimeoutNanoseconds, 500_000_000)
        let watchdog = Task { [weak self, streamClient] in
            guard let self else { return }
            while !Task.isCancelled {
                do {
                    try await Task.sleep(nanoseconds: meterRefreshNanoseconds)
                } catch {
                    return
                }
                guard generation == self.selectionGeneration else { return }
                self.displayFPS = self.frameRateMeter.current(at: ProcessInfo.processInfo.systemUptime)
                let timeout = TimeInterval(self.frameTimeoutNanoseconds) / 1_000_000_000
                if Date().timeIntervalSince(self.lastFrameAt) >= timeout {
                    await streamClient.stop()
                    return
                }
            }
        }
        defer {
            watchdog.cancel()
        }

        for try await timestamp in streams.renderedFrames {
            guard !Task.isCancelled, generation == selectionGeneration else {
                throw CancellationError()
            }
            lastFrameAt = Date()
            currentSessionReceivedFrame = true
            displayFPS = frameRateMeter.record(at: timestamp)
            streamState = .playing
        }
    }

    func stop() {
        privacySyncTask?.cancel()
        privacySyncTask = nil
        selectionGeneration += 1
        frameTask?.cancel()
        frameTask = Task { [streamClient] in
            await streamClient.stop()
        }
        videoSurface = nil
        streamState = .idle
        frameRateMeter.reset()
        displayFPS = 0
    }

    func clearSelection() {
        stop()
        selectedCameraID = nil
        displayFPS = 0
    }

    func retry() {
        guard let selectedCameraID else { return }
        select(cameraID: selectedCameraID)
    }

    func startPrivacySync() {
        guard privacySyncTask == nil, let privacyService, let familyID else { return }
        privacySyncTask = Task { [weak self] in
            while !Task.isCancelled {
                do {
                    let policy = try await privacyService.fetch(familyID: familyID)
                    guard let self, !Task.isCancelled else { return }
                    self.applyPrivacyPolicy(policy)
                } catch is CancellationError {
                    return
                } catch {
                    self?.privacyError = error.localizedDescription
                }
                do {
                    try await Task.sleep(nanoseconds: 1_000_000_000)
                } catch {
                    return
                }
            }
        }
    }

    func setPrivacyMode(_ mode: VideoPrivacyMode) {
        guard mode != selectedPrivacyMode, !privacyUpdateInFlight else { return }
        guard privacyPolicy?.canManage == true, let privacyService, let familyID else { return }
        privacyUpdateInFlight = true
        privacyError = nil
        Task { [weak self] in
            do {
                let policy = try await privacyService.update(familyID: familyID, minimumMode: mode)
                guard let self else { return }
                self.applyPrivacyPolicy(policy)
                self.privacyUpdateInFlight = false
            } catch is CancellationError {
                self?.privacyUpdateInFlight = false
            } catch {
                self?.privacyError = error.localizedDescription
                self?.privacyUpdateInFlight = false
            }
        }
    }

    private func applyPrivacyPolicy(_ policy: VideoPrivacyPolicy) {
        privacyPolicy = policy
        privacyError = nil
        guard selectedPrivacyMode != policy.minimumMode else { return }
        selectedPrivacyMode = policy.minimumMode
        if let selectedCameraID {
            startStream(cameraID: selectedCameraID, profile: "mobile")
        }
    }

    deinit {
        frameTask?.cancel()
        privacySyncTask?.cancel()
        let streamClient = streamClient
        Task { await streamClient.stop() }
    }
}
