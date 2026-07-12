import SwiftUI

@main
struct GoHomeShellApp: App {
    @UIApplicationDelegateAdaptor(GoHomeAppDelegate.self) private var appDelegate
    @StateObject private var runtime = GoHomeShellRuntime()

    var body: some Scene {
        WindowGroup {
            GoHomeShellView()
                .environmentObject(runtime)
                .onAppear {
                    appDelegate.runtime = runtime
                }
                .onOpenURL { url in
                    runtime.handleIncomingURL(url)
                }
        }
    }
}

struct GoHomeShellView: View {
    @EnvironmentObject private var runtime: GoHomeShellRuntime

    var body: some View {
        ZStack {
            Color(red: 0.984, green: 0.976, blue: 0.973)
                .ignoresSafeArea()

            GoHomeShellWebView()
                .environmentObject(runtime)

            if !runtime.hasPresentedWebContent {
                GoHomeLaunchView(
                    errorMessage: runtime.webLoadError,
                    retry: runtime.retryWebContent
                )
                .transition(.opacity)
            }
        }
        .animation(.easeOut(duration: 0.24), value: runtime.hasPresentedWebContent)
    }
}

private struct GoHomeLaunchView: View {
    let errorMessage: String?
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            Spacer()

            Image(systemName: "house.fill")
                .font(.system(size: 29, weight: .semibold))
                .foregroundStyle(Color(red: 0.78, green: 0.25, blue: 0.18))
                .frame(width: 58, height: 58)
                .background(Color.white.opacity(0.84), in: RoundedRectangle(cornerRadius: 16, style: .continuous))

            Text("回家")
                .font(.system(size: 27, weight: .bold, design: .rounded))
                .foregroundStyle(Color(red: 0.16, green: 0.14, blue: 0.13))
                .padding(.top, 18)

            Text("让牵挂随时有回应")
                .font(.system(size: 14, weight: .regular))
                .foregroundStyle(Color(red: 0.43, green: 0.39, blue: 0.37))
                .padding(.top, 7)

            Spacer()

            if let errorMessage {
                VStack(spacing: 13) {
                    Text(errorMessage)
                        .font(.system(size: 13))
                        .foregroundStyle(Color(red: 0.43, green: 0.39, blue: 0.37))

                    Button("重新连接", action: retry)
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(.white)
                        .frame(width: 120, height: 42)
                        .background(Color(red: 0.78, green: 0.25, blue: 0.18), in: RoundedRectangle(cornerRadius: 8))
                }
            } else {
                ProgressView()
                    .tint(Color(red: 0.78, green: 0.25, blue: 0.18))
            }

            Spacer()
                .frame(height: 54)
        }
        .padding(.horizontal, 24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(red: 0.984, green: 0.976, blue: 0.973))
    }
}
