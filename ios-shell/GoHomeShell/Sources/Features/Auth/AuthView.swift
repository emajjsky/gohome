import SwiftUI

struct AuthView: View {
    @StateObject private var viewModel: AuthViewModel
    @FocusState private var focusedField: Field?

    private enum Field: Hashable {
        case phone
        case code
    }

    init(viewModel: AuthViewModel) {
        _viewModel = StateObject(wrappedValue: viewModel)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Spacer(minLength: 46)

                Image(systemName: "arrow.turn.down.right")
                    .font(.system(size: 20, weight: .bold))
                    .foregroundStyle(Color.black)
                    .frame(width: 44, height: 44)
                    .background(Color.yellow.opacity(0.82), in: Circle())
                    .accessibilityHidden(true)

                Text("回家")
                    .font(.system(size: 38, weight: .bold, design: .rounded))
                    .foregroundStyle(Color.black)
                    .padding(.top, 24)

                Text("让关心变成有回应的日常")
                    .font(.system(size: 16, weight: .regular))
                    .foregroundStyle(Color.black.opacity(0.55))
                    .padding(.top, 8)

                Picker("账户操作", selection: $viewModel.mode) {
                    ForEach(AuthViewModel.Mode.allCases) { mode in
                        Text(mode.title).tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                .padding(.top, 38)
                .accessibilityIdentifier("auth-mode-picker")

                VStack(alignment: .leading, spacing: 9) {
                    Text("手机号")
                        .font(.system(size: 13, weight: .semibold))
                    TextField("输入手机号", text: $viewModel.phone)
                        .keyboardType(.phonePad)
                        .textContentType(.telephoneNumber)
                        .focused($focusedField, equals: .phone)
                        .padding(.horizontal, 16)
                        .frame(height: 52)
                        .background(Color.black.opacity(0.045), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .accessibilityIdentifier("phone-input")
                }
                .padding(.top, 30)

                VStack(alignment: .leading, spacing: 9) {
                    Text("验证码")
                        .font(.system(size: 13, weight: .semibold))
                    HStack(spacing: 10) {
                        TextField("输入验证码", text: $viewModel.code)
                            .keyboardType(.numberPad)
                            .textContentType(.oneTimeCode)
                            .focused($focusedField, equals: .code)
                            .padding(.horizontal, 16)
                            .frame(height: 52)
                            .background(Color.black.opacity(0.045), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                            .accessibilityIdentifier("code-input")

                        Button(viewModel.isRequestingCode ? "发送中" : (viewModel.codeSent ? "重新发送" : "获取验证码")) {
                            viewModel.requestCode()
                        }
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(Color.black)
                        .frame(width: 104, height: 52)
                        .background(Color.yellow.opacity(0.82), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .disabled(!viewModel.canRequestCode)
                        .accessibilityIdentifier("request-code-button")
                    }
                }
                .padding(.top, 18)

                if let deliveryMessage = viewModel.deliveryMessage {
                    Text(deliveryMessage)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(Color.black.opacity(0.62))
                        .padding(.top, 12)
                        .accessibilityIdentifier("auth-delivery-status")
                }

                if let errorMessage = viewModel.errorMessage {
                    Text(errorMessage)
                        .font(.system(size: 13))
                        .foregroundStyle(Color.red.opacity(0.8))
                        .padding(.top, 14)
                        .accessibilityIdentifier("auth-error")
                }

                Spacer(minLength: 24)
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 36)
        }
        .scrollDismissesKeyboard(.interactively)
        .background(Color.white.ignoresSafeArea())
        .safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: 10) {
                Button(viewModel.isSubmitting ? "正在进入" : viewModel.mode.title) {
                    focusedField = nil
                    viewModel.submit()
                }
                .font(.system(size: 16, weight: .bold))
                .foregroundStyle(Color.white)
                .frame(maxWidth: .infinity)
                .frame(height: 54)
                .background(Color.black, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .disabled(!viewModel.canSubmit)
                .opacity(viewModel.canSubmit ? 1 : 0.55)
                .accessibilityIdentifier("auth-submit-button")

                Text("登录即表示你同意隐私政策与服务条款")
                    .font(.system(size: 12))
                    .foregroundStyle(Color.black.opacity(0.38))
            }
            .padding(.horizontal, 24)
            .padding(.top, 10)
            .padding(.bottom, 8)
            .background(Color.white)
        }
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("完成") { focusedField = nil }
                    .fontWeight(.semibold)
                    .foregroundStyle(Color.black)
            }
        }
    }
}
