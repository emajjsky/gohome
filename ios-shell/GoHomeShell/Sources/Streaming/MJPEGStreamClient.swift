import Foundation

actor MJPEGStreamClient: CameraStreamClient {
    private let apiClient: APIClient
    private var streamTask: Task<Void, Never>?
    private var continuation: AsyncThrowingStream<Data, Error>.Continuation?
    private var generation = 0

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    func frames(cameraID: String, profile: String) async throws -> AsyncThrowingStream<Data, Error> {
        generation += 1
        let requestGeneration = generation
        await stopCurrentStream()

        let body = try JSONEncoder().encode([
            "resource_type": "stream",
            "camera_id": cameraID,
            "profile": profile,
        ])
        let playback: CameraPlaybackSession = try await apiClient.send(Endpoint(
            method: .post,
            path: "/api/v1/video/sessions",
            body: body
        ))
        guard requestGeneration == generation else { throw CancellationError() }

        let defaultPath = "/api/v1/video/cameras/\(cameraID)/stream.mjpg"
        let scheduledURL = playback.streamURL.flatMap(URL.init(string:))
        var components = URLComponents(
            url: scheduledURL ?? apiClient.baseURL,
            resolvingAgainstBaseURL: false
        )
        if scheduledURL == nil {
            components?.path = playback.streamPath ?? defaultPath
        }
        var queryItems = components?.queryItems ?? []
        queryItems.removeAll { $0.name == "playback_ticket" || $0.name == "profile" }
        queryItems.append(contentsOf: [
            URLQueryItem(name: "playback_ticket", value: playback.ticket),
            URLQueryItem(name: "profile", value: profile),
        ])
        components?.queryItems = queryItems
        guard let url = components?.url else { throw APIError.invalidResponse }

        let stream = AsyncThrowingStream<Data, Error>(bufferingPolicy: .bufferingNewest(1)) { continuation in
            self.continuation = continuation
            continuation.onTermination = { @Sendable [weak self] _ in
                Task { await self?.stopIfCurrent(generation: requestGeneration) }
            }
            self.streamTask = Task { [weak self] in
                await self?.consume(url: url, generation: requestGeneration, continuation: continuation)
            }
        }
        return stream
    }

    func stop() async {
        generation += 1
        await stopCurrentStream()
    }

    private func stopCurrentStream() async {
        streamTask?.cancel()
        streamTask = nil
        continuation?.finish()
        continuation = nil
    }

    private func stopIfCurrent(generation requestGeneration: Int) async {
        guard requestGeneration == generation else { return }
        generation += 1
        await stopCurrentStream()
    }

    private func consume(
        url: URL,
        generation: Int,
        continuation: AsyncThrowingStream<Data, Error>.Continuation
    ) async {
        do {
            var request = URLRequest(url: url)
            request.cachePolicy = .reloadIgnoringLocalCacheData
            request.timeoutInterval = 12
            request.setValue("multipart/x-mixed-replace,image/*,*/*", forHTTPHeaderField: "Accept")

            let delegate = MJPEGDataDelegate()
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

            var parser = MJPEGFrameParser()
            for try await chunk in delegate.chunks {
                try Task.checkCancellation()
                guard generation == self.generation else { throw CancellationError() }
                for frame in parser.append(chunk) {
                    continuation.yield(frame)
                }
            }
            continuation.finish()
        } catch is CancellationError {
            continuation.finish()
        } catch {
            continuation.finish(throwing: error)
        }
    }
}

final class MJPEGDataDelegate: NSObject, URLSessionDataDelegate, @unchecked Sendable {
    private let lock = NSLock()
    private var streamContinuation: AsyncThrowingStream<Data, Error>.Continuation?
    let chunks: AsyncThrowingStream<Data, Error>

    override init() {
        var continuation: AsyncThrowingStream<Data, Error>.Continuation?
        chunks = AsyncThrowingStream(bufferingPolicy: .unbounded) {
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
        completionHandler(.allow)
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        yield(data)
    }

    private func yield(_ data: Data) {
        lock.lock()
        let continuation = streamContinuation
        lock.unlock()
        continuation?.yield(data)
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let error = error as? URLError, error.code == .cancelled {
            finish(nil)
        } else {
            finish(error)
        }
    }

    func receiveForTesting(_ data: Data) {
        yield(data)
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
