import Foundation

@MainActor
final class AuthViewModel: ObservableObject {
    enum Mode: String, CaseIterable, Identifiable {
        case login
        case register

        var id: String { rawValue }
        var title: String { self == .login ? "登录" : "注册" }
    }

    @Published var mode: Mode = .login
    @Published var phone = ""
    @Published var code = ""
    @Published private(set) var isRequestingCode = false
    @Published private(set) var isSubmitting = false
    @Published private(set) var codeSent = false
    @Published private(set) var deliveryMessage: String?
    @Published var errorMessage: String?
    @Published private(set) var challengeID: String?

    private let client: APIClient
    private let authStore: KeychainAuthStore
    private let onAuthenticated: @MainActor () -> Void

    init(client: APIClient, authStore: KeychainAuthStore, onAuthenticated: @escaping @MainActor () -> Void) {
        self.client = client
        self.authStore = authStore
        self.onAuthenticated = onAuthenticated
    }

    var canRequestCode: Bool {
        !isRequestingCode
    }

    var canSubmit: Bool {
        !isSubmitting
    }

    func requestCode() {
        guard !isRequestingCode else { return }
        guard isValidPhone else {
            deliveryMessage = nil
            errorMessage = "请输入完整的 11 位手机号"
            return
        }
        isRequestingCode = true
        errorMessage = nil
        Task {
            defer { isRequestingCode = false }
            do {
                let body = try JSONEncoder().encode(["phone": normalizedPhone])
                let challenge = try await client.send(Endpoint<AuthChallengeResponse>(method: .post, path: "/api/auth/request-code", body: body))
                challengeID = challenge.challengeID
                codeSent = true
                if challenge.delivery == "demo", let demoCode = challenge.demoCode {
                    code = demoCode
                    deliveryMessage = "测试环境验证码：\(demoCode)"
                } else {
                    deliveryMessage = "验证码已发送，请查收短信"
                }
            } catch {
                deliveryMessage = nil
                errorMessage = error.localizedDescription
            }
        }
    }

    func submit() {
        guard !isSubmitting else { return }
        guard isValidPhone else {
            errorMessage = "请输入完整的 11 位手机号"
            return
        }
        guard challengeID != nil else {
            errorMessage = "请先获取验证码"
            return
        }
        guard normalizedCode.count == 6 else {
            errorMessage = "请输入完整验证码"
            return
        }
        isSubmitting = true
        errorMessage = nil
        Task {
            defer { isSubmitting = false }
            do {
                let payload = ["phone": normalizedPhone, "code": normalizedCode, "challenge_id": challengeID ?? ""]
                let body = try JSONEncoder().encode(payload)
                let path = mode == .login ? "/api/auth/login" : "/api/auth/register"
                let session = try await client.send(Endpoint<AuthSessionResponse>(method: .post, path: path, body: body))
                try await authStore.save(token: session.token)
                onAuthenticated()
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    private var normalizedPhone: String {
        phone.filter { $0.isNumber }
    }

    private var normalizedCode: String {
        code.filter { $0.isNumber }
    }

    private var isValidPhone: Bool {
        normalizedPhone.count == 11 && normalizedPhone.hasPrefix("1")
    }
}
