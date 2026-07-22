import SwiftUI

@main
struct GoHomeShellApp: App {
    @UIApplicationDelegateAdaptor(GoHomeAppDelegate.self) private var appDelegate
    @State private var environment: AppEnvironment?

    init() {
        _environment = State(initialValue: try? AppEnvironment.live())
    }

    var body: some Scene {
        WindowGroup {
            if let environment {
                AppRootView(environment: environment)
            } else {
                Text("暂时无法启动")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }
}
