import Foundation

enum GuardStreamState: Equatable {
    case idle
    case connecting
    case playing
    case failed(String)
}

@MainActor
final class GuardViewModel: ObservableObject {
    @Published private(set) var selectedCameraID: String?
    @Published private(set) var latestFrame: Data?
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
    private var frameTask: Task<Void, Never>?
    private var privacySyncTask: Task<Void, Never>?
    private var selectionGeneration = 0
    private var lastFrameAt = Date.distantPast
    private var currentSessionReceivedFrame = false

    init(
        streamClient: CameraStreamClient,
        privacyService: (any VideoPrivacyServicing)? = nil,
        familyID: String? = nil,
        initialPrivacyMode: VideoPrivacyMode = .original,
        frameTimeoutNanoseconds: UInt64 = 4_000_000_000,
        reconnectDelayNanoseconds: UInt64 = 500_000_000,
        maxReconnectAttempts: Int = 4
    ) {
        self.streamClient = streamClient
        self.privacyService = privacyService
        self.familyID = familyID
        self.selectedPrivacyMode = initialPrivacyMode
        self.frameTimeoutNanoseconds = frameTimeoutNanoseconds
        self.reconnectDelayNanoseconds = reconnectDelayNanoseconds
        self.maxReconnectAttempts = maxReconnectAttempts
    }

    func select(cameraID: String, profile: String = "mobile") {
        if selectedCameraID == cameraID {
            switch streamState {
            case .connecting, .playing:
                return
            case .idle, .failed:
                break
            }
        }
        startStream(cameraID: cameraID, profile: profile, preserveFrame: false)
    }

    private func startStream(cameraID: String, profile: String, preserveFrame: Bool) {
        selectionGeneration += 1
        let generation = selectionGeneration
        frameTask?.cancel()
        selectedCameraID = cameraID
        if !preserveFrame { latestFrame = nil }
        if latestFrame == nil { streamState = .connecting }
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
                    guard failedAttempts <= self.maxReconnectAttempts else {
                        self.streamState = .failed(error.localizedDescription)
                        return
                    }
                    self.streamState = .connecting
                    do {
                        try await Task.sleep(nanoseconds: self.reconnectDelayNanoseconds)
                    } catch {
                        return
                    }
                }
            }
        }
    }

    private func consumeSession(
        cameraID: String,
        profile: String,
        privacyMode: VideoPrivacyMode,
        generation: Int
    ) async throws {
        currentSessionReceivedFrame = false
        let frames = try await streamClient.frames(
            cameraID: cameraID,
            profile: profile,
            privacyMode: privacyMode
        )
        lastFrameAt = Date()
        let watchdog = Task { [weak self, streamClient] in
            guard let self else { return }
            while !Task.isCancelled {
                do {
                    try await Task.sleep(nanoseconds: self.frameTimeoutNanoseconds)
                } catch {
                    return
                }
                guard generation == self.selectionGeneration else { return }
                let timeout = TimeInterval(self.frameTimeoutNanoseconds) / 1_000_000_000
                if Date().timeIntervalSince(self.lastFrameAt) >= timeout {
                    await streamClient.stop()
                    return
                }
            }
        }
        defer { watchdog.cancel() }

        for try await frame in frames {
            guard !Task.isCancelled, generation == selectionGeneration else {
                throw CancellationError()
            }
            lastFrameAt = Date()
            currentSessionReceivedFrame = true
            latestFrame = frame
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
        streamState = .idle
    }

    func clearSelection() {
        stop()
        selectedCameraID = nil
        latestFrame = nil
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
            startStream(cameraID: selectedCameraID, profile: "mobile", preserveFrame: true)
        }
    }

    deinit {
        frameTask?.cancel()
        privacySyncTask?.cancel()
        let streamClient = streamClient
        Task { await streamClient.stop() }
    }
}
