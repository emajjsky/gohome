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
        GoHomeShellWebView()
            .environmentObject(runtime)
            .background(Color(red: 0.984, green: 0.976, blue: 0.973))
    }
}
