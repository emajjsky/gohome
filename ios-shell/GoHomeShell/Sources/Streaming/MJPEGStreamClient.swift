import Foundation

actor MJPEGStreamClient: CameraStreamClient {
    private let apiClient: APIClient
    private var frameTask: Task<Void, Never>?
    private var frameContinuation: AsyncThrowingStream<Data, Error>.Continuation?
    private var generation = 0

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    func streams(
        cameraID: String,
        profile: String,
        privacyMode: VideoPrivacyMode
    ) async throws -> CameraDisplayStreams {
        generation += 1
        let requestGeneration = generation
        await stopCurrentStream()

        let body = try JSONEncoder().encode([
            "resource_type": "stream",
            "camera_id": cameraID,
            "profile": profile,
            "privacy_mode": privacyMode.rawValue,
        ])
        let playback: CameraPlaybackSession = try await apiClient.send(Endpoint(
            method: .post,
            path: "/api/v1/video/sessions",
            body: body
        ))
        guard requestGeneration == generation else { throw CancellationError() }

        let effectiveMode = playback.privacyMode ?? privacyMode
        guard playback.displayTransport == CameraDisplayTransport.edgeComposedMJPEG else {
            throw APIError.invalidResponse
        }
        let frameURL = try streamURL(
            absolute: playback.streamURL,
            path: playback.streamPath,
            fallbackPath: "/api/v1/video/cameras/\(cameraID)/stream.mjpg",
            playback: playback,
            profile: profile,
            privacyMode: effectiveMode
        )

        let frames = AsyncThrowingStream<Data, Error>(bufferingPolicy: .bufferingNewest(1)) { continuation in
            self.frameContinuation = continuation
            self.frameTask = Task { [weak self] in
                await self?.consumeFrames(url: frameURL, generation: requestGeneration, continuation: continuation)
            }
        }
        return CameraDisplayStreams(frames: frames)
    }

    func stop() async {
        generation += 1
        await stopCurrentStream()
    }

    private func stopCurrentStream() async {
        frameTask?.cancel()
        frameTask = nil
        frameContinuation?.finish()
        frameContinuation = nil
    }

    private func streamURL(
        absolute: String?,
        path: String?,
        fallbackPath: String?,
        playback: CameraPlaybackSession,
        profile: String,
        privacyMode: VideoPrivacyMode
    ) throws -> URL {
        let scheduledURL = absolute.flatMap(URL.init(string:))
        var components = URLComponents(url: scheduledURL ?? apiClient.baseURL, resolvingAgainstBaseURL: false)
        if scheduledURL == nil {
            guard let resolvedPath = path ?? fallbackPath else { throw APIError.invalidResponse }
            components?.path = resolvedPath
        }
        var queryItems = components?.queryItems ?? []
        queryItems.removeAll { ["playback_ticket", "profile", "privacy_mode"].contains($0.name) }
        queryItems.append(contentsOf: [
            URLQueryItem(name: "playback_ticket", value: playback.ticket),
            URLQueryItem(name: "profile", value: profile),
            URLQueryItem(name: "privacy_mode", value: privacyMode.rawValue),
        ])
        components?.queryItems = queryItems
        guard let url = components?.url else { throw APIError.invalidResponse }
        return url
    }

    private func consumeFrames(
        url: URL,
        generation: Int,
        continuation: AsyncThrowingStream<Data, Error>.Continuation
    ) async {
        do {
            var request = URLRequest(url: url)
            request.cachePolicy = .reloadIgnoringLocalCacheData
            request.timeoutInterval = 12
            request.setValue("multipart/x-mixed-replace,image/*,*/*", forHTTPHeaderField: "Accept")

            let delegate = MJPEGFrameDelegate(
                expectedDisplayTransport: CameraDisplayTransport.edgeComposedMJPEG,
                expectedCompositionOwner: "edge"
            )
            let configuration = URLSessionConfiguration.ephemeral
            configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
            configuration.timeoutIntervalForRequest = 12
            configuration.timeoutIntervalForResource = 24 * 60 * 60
            let delegateQueue = OperationQueue()
            delegateQueue.maxConcurrentOperationCount = 1
            let streamSession = URLSession(
                configuration: configuration,
                delegate: delegate,
                delegateQueue: delegateQueue
            )
            let dataTask = streamSession.dataTask(with: request)
            dataTask.resume()
            defer {
                dataTask.cancel()
                streamSession.invalidateAndCancel()
            }

            for try await frame in delegate.frames {
                try Task.checkCancellation()
                guard generation == self.generation else { throw CancellationError() }
                continuation.yield(frame)
            }
            continuation.finish()
        } catch is CancellationError {
            continuation.finish()
        } catch {
            continuation.finish(throwing: error)
        }
    }

}

final class MJPEGFrameDelegate: NSObject, URLSessionDataDelegate, @unchecked Sendable {
    private let lock = NSLock()
    private var parser = MJPEGFrameParser()
    private var streamContinuation: AsyncThrowingStream<Data, Error>.Continuation?
    private let expectedDisplayTransport: String?
    private let expectedCompositionOwner: String?
    let frames: AsyncThrowingStream<Data, Error>

    init(
        expectedDisplayTransport: String? = nil,
        expectedCompositionOwner: String? = nil
    ) {
        self.expectedDisplayTransport = expectedDisplayTransport
        self.expectedCompositionOwner = expectedCompositionOwner
        var continuation: AsyncThrowingStream<Data, Error>.Continuation?
        frames = AsyncThrowingStream(bufferingPolicy: .bufferingNewest(1)) {
            continuation = $0
        }
        streamContinuation = continuation
        super.init()
    }

    func urlSession(
        _ session: URLSession,
        dataTask: URLSessionDataTask,
        didReceive response: URLResponse,
        completionHandler: @escaping (URLSession.ResponseDisposition) -> Void
    ) {
        guard let response = response as? HTTPURLResponse else {
            finish(APIError.invalidResponse)
            completionHandler(.cancel)
            return
        }
        guard (200..<300).contains(response.statusCode) else {
            finish(APIError.server(statusCode: response.statusCode, detail: "视频流连接失败"))
            completionHandler(.cancel)
            return
        }
        if let expectedDisplayTransport,
           response.value(forHTTPHeaderField: "X-GoHome-Display-Transport") != expectedDisplayTransport {
            finish(APIError.invalidResponse)
            completionHandler(.cancel)
            return
        }
        if let expectedCompositionOwner,
           response.value(forHTTPHeaderField: "X-GoHome-Composition-Owner") != expectedCompositionOwner {
            finish(APIError.invalidResponse)
            completionHandler(.cancel)
            return
        }
        completionHandler(.allow)
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        receive(data)
    }

    private func receive(_ data: Data) {
        lock.lock()
        let parsedFrames = parser.append(data)
        let continuation = streamContinuation
        lock.unlock()
        for frame in parsedFrames {
            continuation?.yield(frame)
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let error = error as? URLError, error.code == .cancelled {
            finish(nil)
        } else {
            finish(error)
        }
    }

    func receiveForTesting(_ data: Data) {
        receive(data)
    }

    func finish(_ error: Error?) {
        lock.lock()
        let continuation = streamContinuation
        streamContinuation = nil
        lock.unlock()
        if let error {
            continuation?.finish(throwing: error)
        } else {
            continuation?.finish()
        }
    }
}

struct MJPEGFrameParser: Sendable {
    private var buffer = Data()
    private let maxBufferSize = 4 * 1024 * 1024

    mutating func append(_ byte: UInt8) -> Data? {
        append(Data([byte])).first
    }

    mutating func append(_ data: Data) -> [Data] {
        guard !data.isEmpty else { return [] }
        buffer.append(data)
        if buffer.count > maxBufferSize {
            buffer = Data(buffer.suffix(maxBufferSize))
        }

        var frames: [Data] = []
        while let start = buffer.range(of: Data([0xff, 0xd8]))?.lowerBound {
            if start > buffer.startIndex {
                buffer.removeSubrange(buffer.startIndex..<start)
            }
            guard let endRange = buffer.range(
                of: Data([0xff, 0xd9]),
                in: buffer.startIndex..<buffer.endIndex
            ) else { break }
            let end = endRange.upperBound
            frames.append(Data(buffer[buffer.startIndex..<end]))
            buffer.removeSubrange(buffer.startIndex..<end)
        }

        if frames.isEmpty, buffer.range(of: Data([0xff, 0xd8])) == nil, buffer.count > 1 {
            buffer = buffer.last == 0xff ? Data([0xff]) : Data()
        }
        return frames
    }
}
