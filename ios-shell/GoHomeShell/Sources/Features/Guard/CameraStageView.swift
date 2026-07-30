import SwiftUI
import UIKit

struct CameraStageView: View {
    let image: UIImage?
    let state: GuardStreamState
    let displayFPS: Double
    let poseUpdatesPerSecond: Double
    let privacyMode: VideoPrivacyMode
    let poseTimeline: PoseTimeline

    var body: some View {
        ZStack {
            Color.black
            if let image {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                VStack(spacing: 10) {
                    Image(systemName: iconName)
                        .font(.system(size: 28, weight: .light))
                        .foregroundStyle(.white.opacity(0.82))
                    Text(emptyText)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.82))
                }
            }
            if privacyMode == .skeleton {
                PoseOverlayView(timeline: poseTimeline)
            }
        }
        .frame(maxWidth: .infinity)
        .aspectRatio(16 / 9, contentMode: .fit)
        .clipShape(RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous))
        .overlay(alignment: .topLeading) {
            Text(statusBadge)
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(.white)
                .padding(.horizontal, 9)
                .frame(height: 26)
                .background(Color.black.opacity(0.55), in: Capsule())
                .padding(10)
        }
        .overlay(alignment: .topTrailing) {
            HStack(spacing: 6) {
                if state == .playing, activeRate > 0 {
                    HStack(spacing: 5) {
                        Circle()
                            .fill(Color(red: 0.31, green: 0.86, blue: 0.49))
                            .frame(width: 6, height: 6)
                        Text(rateText)
                            .monospacedDigit()
                    }
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(Color(red: 0.55, green: 1.0, blue: 0.68))
                    .padding(.horizontal, 8)
                    .frame(height: 24)
                    .background(Color.black.opacity(0.64), in: Capsule())
                    .accessibilityIdentifier("guard-display-fps")
                }
                Label(privacyMode.title, systemImage: privacyMode.symbol)
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 8)
                    .frame(height: 24)
                    .background(Color.black.opacity(0.55), in: Capsule())
            }
            .fixedSize(horizontal: true, vertical: false)
                .padding(10)
        }
        .accessibilityIdentifier("guard-camera-stage")
    }

    private var statusBadge: String {
        switch state {
        case .playing: return "LIVE"
        case .connecting: return "连接中"
        case .failed: return "连接异常"
        case .idle: return "未选择"
        }
    }

    private var activeRate: Double {
        privacyMode == .skeleton ? poseUpdatesPerSecond : displayFPS
    }

    private var rateText: String {
        privacyMode == .skeleton
            ? String(format: "POSE %.1f Hz", activeRate)
            : String(format: "%.1f FPS", activeRate)
    }

    private var iconName: String {
        switch state {
        case .failed: return "wifi.exclamationmark"
        case .connecting: return "dot.radiowaves.left.and.right"
        default: return "video"
        }
    }

    private var emptyText: String {
        switch state {
        case .failed: return "画面暂时不可用"
        case .connecting: return "正在连接画面"
        default: return "暂无画面"
        }
    }
}
