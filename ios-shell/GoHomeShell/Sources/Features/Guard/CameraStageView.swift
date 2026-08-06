import SwiftUI

struct CameraStageView: View {
    let surface: WebRTCVideoSurface?
    let state: GuardStreamState
    let displayFPS: Double
    let privacyMode: VideoPrivacyMode

    var body: some View {
        ZStack {
            Color.black
            if let surface {
                WebRTCVideoView(surface: surface)
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
                if shouldShowRate {
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
        case .waiting: return "等待隐私复核"
        case .failed: return "连接异常"
        case .idle: return "未选择"
        }
    }

    var shouldShowRate: Bool {
        state == .playing && displayFPS > 0
    }

    var rateText: String {
        String(format: "%.1f FPS", displayFPS)
    }

    private var iconName: String {
        switch state {
        case .failed: return "wifi.exclamationmark"
        case .connecting: return "dot.radiowaves.left.and.right"
        case .waiting: return "checkmark.shield"
        default: return "video"
        }
    }

    private var emptyText: String {
        switch state {
        case .failed: return "画面暂时不可用"
        case .connecting: return "正在连接画面"
        case let .waiting(message): return message
        default: return "暂无画面"
        }
    }
}
