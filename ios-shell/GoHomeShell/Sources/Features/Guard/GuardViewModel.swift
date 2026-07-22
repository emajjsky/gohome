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

    private let streamClient: CameraStreamClient
    private let frameTimeoutNanoseconds: UInt64
    private let reconnectDelayNanoseconds: UInt64
    private let maxReconnectAttempts: Int
    private var frameTask: Task<Void, Never>?
    private var selectionGeneration = 0
    private var lastFrameAt = Date.distantPast
    private var currentSessionReceivedFrame = false

    init(
        streamClient: CameraStreamClient,
        frameTimeoutNanoseconds: UInt64 = 4_000_000_000,
        reconnectDelayNanoseconds: UInt64 = 500_000_000,
        maxReconnectAttempts: Int = 4
    ) {
        self.streamClient = streamClient
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
        selectionGeneration += 1
        let generation = selectionGeneration
        frameTask?.cancel()
        selectedCameraID = cameraID
        latestFrame = nil
        streamState = .connecting
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

    private func consumeSession(cameraID: String, profile: String, generation: Int) async throws {
        currentSessionReceivedFrame = false
        let frames = try await streamClient.frames(cameraID: cameraID, profile: profile)
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

    deinit {
        frameTask?.cancel()
        let streamClient = streamClient
        Task { await streamClient.stop() }
    }
}
