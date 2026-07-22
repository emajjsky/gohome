import SwiftUI

struct CameraThumbnailStrip: View {
    let cameras: [HomeCamera]
    let selectedID: String?
    let select: (String) -> Void

    var body: some View {
        if cameras.isEmpty {
            Text("绑定盒子并配置摄像头后显示画面")
                .font(.system(size: 13))
                .foregroundStyle(GoHomeTheme.mutedInk)
        } else {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(cameras) { camera in
                        Button { select(camera.id) } label: {
                            VStack(alignment: .leading, spacing: 8) {
                                ZStack {
                                    Color.black.opacity(0.92)
                                    Image(systemName: "video")
                                        .font(.system(size: 17, weight: .light))
                                        .foregroundStyle(.white.opacity(0.78))
                                }
                                .frame(width: 100, height: 60)
                                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                                Text(camera.name)
                                    .font(.system(size: 12, weight: .semibold))
                                    .foregroundStyle(GoHomeTheme.ink)
                                    .lineLimit(1)
                            }
                            .padding(8)
                            .background(
                                selectedID == camera.id ? GoHomeTheme.paleGinger : GoHomeTheme.softLine,
                                in: RoundedRectangle(cornerRadius: GoHomeTheme.compactRadius, style: .continuous)
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }
}
