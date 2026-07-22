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
        normalizedPhone.count == 11 && !isRequestingCode
    }

    var canSubmit: Bool {
        canRequestCode && code.count >= 4 && challengeID != nil && !isSubmitting
    }

    func requestCode() {
        guard canRequestCode else { return }
        isRequestingCode = true
        errorMessage = nil
        Task {
            defer { isRequestingCode = false }
            do {
                let body = try JSONEncoder().encode(["phone": normalizedPhone])
                let challenge = try await client.send(Endpoint<AuthChallengeResponse>(method: .post, path: "/api/auth/request-code", body: body))
                challengeID = challenge.challengeID
                codeSent = true
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    func submit() {
        guard canSubmit else { return }
        isSubmitting = true
        errorMessage = nil
        Task {
            defer { isSubmitting = false }
            do {
                let payload = ["phone": normalizedPhone, "code": code, "challenge_id": challengeID ?? ""]
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
}
