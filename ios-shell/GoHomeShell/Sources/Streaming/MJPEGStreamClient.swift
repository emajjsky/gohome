import Foundation

actor MJPEGStreamClient: CameraStreamClient {
    private let apiClient: APIClient
    private let session: URLSession
    private var streamTask: Task<Void, Never>?
    private var continuation: AsyncThrowingStream<Data, Error>.Continuation?
    private var generation = 0

    init(apiClient: APIClient, session: URLSession = .shared) {
        self.apiClient = apiClient
        self.session = session
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
            request.setValue("multipart/x-mixed-replace,image/*,*/*", forHTTPHeaderField: "Accept")
            let (bytes, response) = try await session.bytes(for: request)
            guard let response = response as? HTTPURLResponse, (200..<300).contains(response.statusCode) else {
                throw APIError.server(statusCode: (response as? HTTPURLResponse)?.statusCode ?? 0, detail: "视频流连接失败")
            }

            var parser = MJPEGFrameParser()
            for try await byte in bytes {
                try Task.checkCancellation()
                guard generation == self.generation else { throw CancellationError() }
                if let frame = parser.append(byte) {
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

struct MJPEGFrameParser: Sendable {
    private var buffer = Data()
    private let maxBufferSize = 4 * 1024 * 1024

    mutating func append(_ byte: UInt8) -> Data? {
        buffer.append(byte)
        guard buffer.count <= maxBufferSize else {
            buffer.removeAll(keepingCapacity: true)
            return nil
        }
        guard let start = buffer.range(of: Data([0xff, 0xd8]))?.lowerBound else {
            trimIfNeeded()
            return nil
        }
        guard let endRange = buffer.range(of: Data([0xff, 0xd9]), in: start..<buffer.endIndex) else {
            trimIfNeeded(keepingFrom: start)
            return nil
        }
        let end = endRange.upperBound
        let frame = Data(buffer[start..<end])
        buffer.removeSubrange(..<end)
        return frame
    }

    private mutating func trimIfNeeded(keepingFrom start: Data.Index? = nil) {
        if let start {
            if start > 0 { buffer.removeSubrange(..<start) }
        } else if buffer.count > maxBufferSize {
            buffer.removeFirst(buffer.count - maxBufferSize)
        }
    }
}
