import SwiftUI
@preconcurrency import WebKit

struct GoHomeShellWebView: UIViewRepresentable {
    @EnvironmentObject private var runtime: GoHomeShellRuntime

    func makeCoordinator() -> Coordinator {
        Coordinator(runtime: runtime)
    }

    func makeUIView(context: Context) -> WKWebView {
        let contentController = WKUserContentController()
        contentController.add(context.coordinator, name: "gohomeNativeApp")

        let configuration = WKWebViewConfiguration()
        configuration.userContentController = contentController
        configuration.websiteDataStore = .default()
        configuration.allowsInlineMediaPlayback = true
        configuration.mediaTypesRequiringUserActionForPlayback = []
        configuration.applicationNameForUserAgent = "GoHomeIOS/0.1"

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.scrollView.contentInsetAdjustmentBehavior = .automatic
        webView.allowsBackForwardNavigationGestures = true
        webView.scrollView.keyboardDismissMode = .interactive
        webView.isOpaque = false
        webView.backgroundColor = UIColor(red: 0.984, green: 0.976, blue: 0.973, alpha: 1)
        webView.scrollView.backgroundColor = webView.backgroundColor
        context.coordinator.attach(webView)
        context.coordinator.load(ShellConfig.webAppURL, reloadID: runtime.webReloadID)
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        context.coordinator.load(runtime.webAppURL, reloadID: runtime.webReloadID)
    }

    final class Coordinator: NSObject, WKScriptMessageHandler, WKNavigationDelegate, WKUIDelegate {
        private weak var webView: WKWebView?
        private let runtime: GoHomeShellRuntime
        private var lastRequestedURL: URL?
        private var lastReloadID: UUID?

        init(runtime: GoHomeShellRuntime) {
            self.runtime = runtime
        }

        func attach(_ webView: WKWebView) {
            self.webView = webView
        }

        func load(_ url: URL, reloadID: UUID) {
            guard lastRequestedURL != url || lastReloadID != reloadID else { return }
            lastRequestedURL = url
            lastReloadID = reloadID
            var request = URLRequest(url: url, cachePolicy: .reloadRevalidatingCacheData, timeoutInterval: 30)
            request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
            webView?.load(request)
        }

        func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
            Task { @MainActor in
                runtime.markWebContentLoading()
            }
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            Task { @MainActor in
                runtime.markWebContentReady()
            }
        }

        func webView(
            _ webView: WKWebView,
            didFailProvisionalNavigation navigation: WKNavigation!,
            withError error: Error
        ) {
            Task { @MainActor in
                runtime.markWebContentFailed()
            }
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            Task { @MainActor in
                runtime.markWebContentFailed()
            }
        }

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == "gohomeNativeApp" else { return }
            guard
                let payload = message.body as? [String: Any],
                let method = payload["method"] as? String,
                let requestID = payload["requestId"] as? String
            else {
                return
            }
            Task { @MainActor in
                do {
                let callPayload = payload["payload"] as? [String: Any] ?? [:]
                let result = try await call(method: method, payload: callPayload)
                    respond(requestID: requestID, result: result, error: nil)
                } catch {
                    respond(requestID: requestID, result: nil, error: error.localizedDescription)
                }
            }
        }

        private func call(method: String, payload: [String: Any]) async throws -> Any? {
            switch method {
            case "registerForPush":
                return try await runtime.registerForPush()
            case "consumeLaunchPayload":
                return runtime.consumeLaunchPayload()
            case "openExternalURL":
                return try await runtime.openExternalURL(String(payload["url"] as? String ?? ""))
            default:
                throw BridgeError.unsupportedMethod
            }
        }

        func webView(
            _ webView: WKWebView,
            decidePolicyFor navigationAction: WKNavigationAction,
            decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
        ) {
            guard let url = navigationAction.request.url, let scheme = url.scheme?.lowercased() else {
                decisionHandler(.cancel)
                return
            }
            if ["tel", "sms", "weixin"].contains(scheme) {
                Task { @MainActor in _ = try? await runtime.openExternalURL(url.absoluteString) }
                decisionHandler(.cancel)
                return
            }
            if ["http", "https"].contains(scheme) {
                let host = url.host?.lowercased() ?? ""
                let cloudHost = ShellConfig.webAppURL.host?.lowercased() ?? ""
                if host == cloudHost || host == "gohome.local" || host.hasSuffix(".local") {
                    decisionHandler(.allow)
                    return
                }
            }
            decisionHandler(.cancel)
        }

        func webView(
            _ webView: WKWebView,
            createWebViewWith configuration: WKWebViewConfiguration,
            for navigationAction: WKNavigationAction,
            windowFeatures: WKWindowFeatures
        ) -> WKWebView? {
            if navigationAction.targetFrame == nil, let url = navigationAction.request.url {
                webView.load(URLRequest(url: url))
            }
            return nil
        }

        func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
            webView.reload()
        }

        private func respond(requestID: String, result: Any?, error: String?) {
            guard let webView else { return }
            let requestIDJSON = jsonLiteral(requestID)
            let resultJSON = jsonLiteral(result)
            let errorJSON = jsonLiteral(error ?? "")
            let script = """
            window.GoHomeEdge && window.GoHomeEdge.resolveNativeBridgeResult && window.GoHomeEdge.resolveNativeBridgeResult(\(requestIDJSON), \(resultJSON), \(errorJSON));
            """
            webView.evaluateJavaScript(script)
        }

        private func jsonLiteral(_ value: Any?) -> String {
            guard let value else { return "null" }
            if !JSONSerialization.isValidJSONObject(value) {
                if let text = value as? String, let data = try? JSONSerialization.data(withJSONObject: [text]), var literal = String(data: data, encoding: .utf8) {
                    literal.removeFirst()
                    literal.removeLast()
                    return literal
                }
                return "null"
            }
            let data = (try? JSONSerialization.data(withJSONObject: value)) ?? Data("null".utf8)
            return String(data: data, encoding: .utf8) ?? "null"
        }
    }
}

enum BridgeError: LocalizedError {
    case unsupportedMethod

    var errorDescription: String? {
        switch self {
        case .unsupportedMethod:
            return "Unsupported native bridge method"
        }
    }
}
