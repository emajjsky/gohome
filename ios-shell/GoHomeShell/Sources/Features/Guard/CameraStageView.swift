import SwiftUI
import UIKit

struct CameraStageView: View {
    let frameData: Data?
    let state: GuardStreamState

    var body: some View {
        ZStack {
            Color.black
            if let frameData, let image = UIImage(data: frameData) {
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
