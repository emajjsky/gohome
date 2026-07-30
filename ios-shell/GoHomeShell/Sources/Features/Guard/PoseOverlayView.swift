import SwiftUI

struct PoseOverlayView: View {
    let timeline: PoseTimeline

    private let edges: [(String, String)] = [
        ("left_ear", "left_eye"), ("left_eye", "nose"),
        ("nose", "right_eye"), ("right_eye", "right_ear"),
        ("left_shoulder", "right_shoulder"),
        ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
        ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"),
        ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip"),
        ("left_hip", "right_hip"),
        ("left_hip", "left_knee"), ("left_knee", "left_ankle"),
        ("right_hip", "right_knee"), ("right_knee", "right_ankle"),
    ]

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 30, paused: false)) { context in
            Canvas(rendersAsynchronously: true) { graphics, size in
                guard let packet = timeline.interpolated(at: context.date) else { return }
                let transform = AspectFillTransform(
                    sourceWidth: packet.imageWidth,
                    sourceHeight: packet.imageHeight,
                    destination: size
                )
                for pose in packet.poses where pose.confidence >= 0.2 {
                    draw(pose: pose, transform: transform, in: &graphics)
                }
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    private func draw(
        pose: PoseTrack,
        transform: AspectFillTransform,
        in graphics: inout GraphicsContext
    ) {
        var points: [String: CGPoint] = [:]
        for point in pose.keypoints where point.visible && point.confidence >= 0.22 {
            points[point.name] = transform.point(x: point.x, y: point.y)
        }
        for edge in edges {
            guard let start = points[edge.0], let end = points[edge.1] else { continue }
            var shadow = Path()
            shadow.move(to: start)
            shadow.addLine(to: end)
            graphics.stroke(shadow, with: .color(.black.opacity(0.7)), lineWidth: 5)
            graphics.stroke(shadow, with: .color(Color(red: 0.13, green: 0.82, blue: 0.86)), lineWidth: 2.5)
        }
        for point in points.values {
            let outer = CGRect(x: point.x - 3.5, y: point.y - 3.5, width: 7, height: 7)
            graphics.fill(Path(ellipseIn: outer), with: .color(.black.opacity(0.72)))
            let inner = CGRect(x: point.x - 2, y: point.y - 2, width: 4, height: 4)
            graphics.fill(Path(ellipseIn: inner), with: .color(.white))
        }
    }
}

private struct AspectFillTransform {
    let scale: Double
    let xOffset: Double
    let yOffset: Double

    init(sourceWidth: Double, sourceHeight: Double, destination: CGSize) {
        let width = max(1, sourceWidth)
        let height = max(1, sourceHeight)
        scale = max(destination.width / width, destination.height / height)
        xOffset = (destination.width - width * scale) / 2
        yOffset = (destination.height - height * scale) / 2
    }

    func point(x: Double, y: Double) -> CGPoint {
        CGPoint(x: x * scale + xOffset, y: y * scale + yOffset)
    }
}
