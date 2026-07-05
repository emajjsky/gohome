import SwiftUI
import WebKit

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
        configuration.allowsInlineMediaPlayback = true
        configuration.mediaTypesRequiringUserActionForPlayback = []

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        context.coordinator.attach(webView)
        webView.load(cacheBypassingRequest(for: ShellConfig.webAppURL))
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        let current = webView.url?.absoluteString ?? ""
        let target = runtime.webAppURL.absoluteString
        guard current != target else { return }
        webView.load(cacheBypassingRequest(for: runtime.webAppURL))
    }

    private func cacheBypassingRequest(for url: URL) -> URLRequest {
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 30)
        request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
        request.setValue("no-cache", forHTTPHeaderField: "Pragma")
        return request
    }

    final class Coordinator: NSObject, WKScriptMessageHandler, WKNavigationDelegate {
        private weak var webView: WKWebView?
        private let runtime: GoHomeShellRuntime

        init(runtime: GoHomeShellRuntime) {
            self.runtime = runtime
        }

        func attach(_ webView: WKWebView) {
            self.webView = webView
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
                    let result = try await call(method: method)
                    respond(requestID: requestID, result: result, error: nil)
                } catch {
                    respond(requestID: requestID, result: nil, error: error.localizedDescription)
                }
            }
        }

        private func call(method: String) async throws -> Any? {
            switch method {
            case "registerForPush":
                return try await runtime.registerForPush()
            case "consumeLaunchPayload":
                return runtime.consumeLaunchPayload()
            default:
                throw BridgeError.unsupportedMethod
            }
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
