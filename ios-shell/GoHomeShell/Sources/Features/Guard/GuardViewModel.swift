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
    private var frameTask: Task<Void, Never>?
    private var selectionGeneration = 0

    init(streamClient: CameraStreamClient) {
        self.streamClient = streamClient
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
        let previousTask = frameTask
        previousTask?.cancel()
        selectedCameraID = cameraID
        latestFrame = nil
        streamState = .connecting
        frameTask = Task { [weak self, streamClient] in
            await previousTask?.value
            guard
                let self,
                !Task.isCancelled,
                generation == self.selectionGeneration
            else { return }
            await streamClient.stop()
            guard
                !Task.isCancelled,
                generation == self.selectionGeneration
            else { return }
            do {
                let frames = try await streamClient.frames(cameraID: cameraID, profile: profile)
                for try await frame in frames {
                    guard
                        !Task.isCancelled,
                        generation == self.selectionGeneration
                    else { return }
                    self.latestFrame = frame
                    self.streamState = .playing
                }
                if generation == self.selectionGeneration,
                   (self.streamState == .connecting || self.streamState == .playing) {
                    self.streamState = .idle
                }
            } catch is CancellationError {
                return
            } catch {
                guard generation == self.selectionGeneration, !Task.isCancelled else { return }
                self.streamState = .failed(error.localizedDescription)
            }
        }
    }

    func stop() {
        selectionGeneration += 1
        let previousTask = frameTask
        previousTask?.cancel()
        frameTask = Task { [streamClient] in
            await previousTask?.value
            guard !Task.isCancelled else { return }
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
