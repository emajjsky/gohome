import Foundation

struct PosePacket: Decodable, Equatable, Sendable {
    let schemaVersion: String
    let cameraID: Int
    let frameID: String
    let capturedAt: String
    let state: String
    let imageWidth: Double
    let imageHeight: Double
    let poses: [PoseTrack]
    let displayOnly: Bool
    let formalEvidenceEligible: Bool

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case cameraID = "camera_id"
        case frameID = "frame_id"
        case capturedAt = "captured_at"
        case state
        case imageWidth = "image_width"
        case imageHeight = "image_height"
        case poses
        case displayOnly = "display_only"
        case formalEvidenceEligible = "formal_evidence_eligible"
    }

    var isDisplaySafe: Bool {
        displayOnly && !formalEvidenceEligible && ["observed", "tracked", "coasting"].contains(state)
    }
}

struct PoseTrack: Decodable, Equatable, Sendable {
    let trackID: String
    let confidence: Double
    let bbox: [Double]
    let keypoints: [PoseKeypoint]

    enum CodingKeys: String, CodingKey {
        case trackID = "track_id"
        case confidence, bbox, keypoints
    }
}

struct PoseKeypoint: Decodable, Equatable, Sendable {
    let name: String
    let x: Double
    let y: Double
    let confidence: Double
    let visible: Bool
}

struct TimedPosePacket: Equatable, Sendable {
    let packet: PosePacket
    let receivedAt: Date
    let sourceAt: Date?

    init(packet: PosePacket, receivedAt: Date) {
        self.packet = packet
        self.receivedAt = receivedAt
        sourceAt = PoseTimestamp.parse(packet.capturedAt)
    }
}

struct PoseTimeline: Equatable, Sendable {
    let previous: TimedPosePacket?
    let current: TimedPosePacket?

    static let empty = PoseTimeline(previous: nil, current: nil)

    func interpolated(at displayDate: Date, delay: TimeInterval = 0.067) -> PosePacket? {
        guard let current, current.packet.isDisplaySafe else { return nil }
        guard
            let previous,
            previous.packet.isDisplaySafe,
            previous.packet.cameraID == current.packet.cameraID,
            previous.receivedAt < current.receivedAt
        else { return current.packet }
        let useSourceTimeline = previous.sourceAt.map { previousSource in
            current.sourceAt.map { $0 > previousSource } ?? false
        } ?? false
        let previousTime = useSourceTimeline ? (previous.sourceAt ?? previous.receivedAt) : previous.receivedAt
        let currentTime = useSourceTimeline ? (current.sourceAt ?? current.receivedAt) : current.receivedAt
        let transportOffset = useSourceTimeline
            ? current.receivedAt.timeIntervalSince(currentTime)
            : 0
        let target = displayDate.addingTimeInterval(-(delay + transportOffset))
        let duration = currentTime.timeIntervalSince(previousTime)
        let progress = max(0, min(1, target.timeIntervalSince(previousTime) / duration))
        return current.packet.interpolated(from: previous.packet, progress: progress)
    }
}

private enum PoseTimestamp {
    private static let fractionalFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()
    private static let standardFormatter = ISO8601DateFormatter()

    static func parse(_ value: String) -> Date? {
        let text = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return nil }
        return fractionalFormatter.date(from: text) ?? standardFormatter.date(from: text)
    }
}

extension PosePacket {
    fileprivate func interpolated(from previous: PosePacket, progress: Double) -> PosePacket {
        var previousTracks: [String: PoseTrack] = [:]
        for track in previous.poses where !track.trackID.isEmpty {
            previousTracks[track.trackID] = track
        }
        let renderedTracks = poses.map { currentTrack -> PoseTrack in
            guard !currentTrack.trackID.isEmpty, let previousTrack = previousTracks[currentTrack.trackID] else {
                return currentTrack
            }
            var previousPoints: [String: PoseKeypoint] = [:]
            for point in previousTrack.keypoints { previousPoints[point.name] = point }
            return PoseTrack(
                trackID: currentTrack.trackID,
                confidence: lerp(previousTrack.confidence, currentTrack.confidence, progress),
                bbox: zip(previousTrack.bbox, currentTrack.bbox).map { lerp($0, $1, progress) },
                keypoints: currentTrack.keypoints.map { point in
                    guard let old = previousPoints[point.name] else { return point }
                    return PoseKeypoint(
                        name: point.name,
                        x: lerp(old.x, point.x, progress),
                        y: lerp(old.y, point.y, progress),
                        confidence: lerp(old.confidence, point.confidence, progress),
                        visible: point.visible && old.visible
                    )
                }
            )
        }
        return PosePacket(
            schemaVersion: schemaVersion,
            cameraID: cameraID,
            frameID: frameID,
            capturedAt: capturedAt,
            state: state,
            imageWidth: imageWidth,
            imageHeight: imageHeight,
            poses: renderedTracks,
            displayOnly: displayOnly,
            formalEvidenceEligible: formalEvidenceEligible
        )
    }
}

private func lerp(_ start: Double, _ end: Double, _ progress: Double) -> Double {
    start + (end - start) * progress
}

struct PoseSSEParser: Sendable {
    private var buffer = Data()
    private let maxBufferSize = 256 * 1024

    mutating func append(_ data: Data) -> [PosePacket] {
        guard !data.isEmpty else { return [] }
        buffer.append(data)
        if buffer.count > maxBufferSize {
            buffer = Data(buffer.suffix(maxBufferSize))
        }
        var packets: [PosePacket] = []
        let delimiter = Data("\n\n".utf8)
        while let range = buffer.range(of: delimiter) {
            let event = Data(buffer[..<range.lowerBound])
            buffer.removeSubrange(buffer.startIndex..<range.upperBound)
            let dataLines = String(decoding: event, as: UTF8.self)
                .split(separator: "\n")
                .filter { $0.hasPrefix("data:") }
                .map { $0.dropFirst(5).trimmingCharacters(in: .whitespaces) }
            guard !dataLines.isEmpty else { continue }
            let payload = Data(dataLines.joined(separator: "\n").utf8)
            if let packet = try? JSONDecoder().decode(PosePacket.self, from: payload),
               packet.displayOnly,
               !packet.formalEvidenceEligible {
                packets.append(packet)
            }
        }
        return packets
    }
}
