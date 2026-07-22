# Native Foundation And Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the WebView root with a tested native SwiftUI application foundation that restores sessions, renders cached state immediately, and completes registration through camera onboarding.

**Architecture:** XcodeGen owns the project. A Keychain-backed auth store, typed API client, actor disk cache, repository, and main-actor session coordinator isolate transport from SwiftUI views. The existing WebView files remain outside the root during migration and are deleted only after native parity.

**Tech Stack:** SwiftUI, XCTest, XCUITest, URLSession, Security, Codable, Network/Bonjour, iOS 16.

---

## File Map

- Modify `ios-shell/project.yml`: app, unit-test, and UI-test targets.
- Replace `ios-shell/GoHomeShell/Sources/GoHomeShellApp.swift`: native root.
- Create `Sources/App/AppEnvironment.swift`, `AppModel.swift`, `AppRootView.swift`.
- Create `Sources/Networking/APIClient.swift`, `APIError.swift`, `Endpoint.swift`.
- Create `Sources/Storage/KeychainAuthStore.swift`, `DiskCache.swift`.
- Create `Sources/Repository/AppRepository.swift`.
- Create `Sources/Models/AppModels.swift`.
- Create `Sources/Features/Auth/*` and `Sources/Features/Onboarding/*`.
- Create `Sources/Services/BoxDiscoveryService.swift`.
- Create `GoHomeShellTests/*` and `GoHomeShellUITests/*`.

### Task 1: Generate Testable Native Project

**Files:**
- Modify: `ios-shell/project.yml`
- Create: `ios-shell/scripts/test.sh`
- Create: `ios-shell/GoHomeShellTests/AppSmokeTests.swift`
- Create: `ios-shell/GoHomeShellUITests/LaunchTests.swift`

- [x] **Step 1: Add test targets and failing smoke tests**

```swift
import XCTest
@testable import GoHomeShell

final class AppSmokeTests: XCTestCase {
    func testNativeRootHasNoWebViewDependency() {
        XCTAssertEqual(AppRoute.signedOut, .signedOut)
    }
}
```

Add `GoHomeShellTests` and `GoHomeShellUITests` targets to `project.yml`, with the app as host/target dependency. Add this shared test runner:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
xcodegen generate
args=()
if [ "${1:-}" != "" ]; then args+=("-only-testing:$1"); fi
xcodebuild test -project GoHomeShell.xcodeproj -scheme GoHomeShell \
  -destination 'platform=iOS Simulator,name=iPhone 16 Pro' "${args[@]}"
```

- [x] **Step 2: Generate and verify failure**

Run:

```bash
cd ios-shell
xcodegen generate
xcodebuild test -project GoHomeShell.xcodeproj -scheme GoHomeShell \
  -destination 'platform=iOS Simulator,name=iPhone 16 Pro'
```

Expected: FAIL because `AppRoute` is undefined.

- [x] **Step 3: Add the minimal route type**

Create `Sources/App/AppRoute.swift`:

```swift
enum AppRoute: Equatable {
    case launching
    case signedOut
    case onboarding(OnboardingStep)
    case main
}

enum OnboardingStep: String, Codable, Equatable {
    case family, profile, device, camera, complete
}
```

- [x] **Step 4: Regenerate and pass smoke test**

Run: `ios-shell/scripts/test.sh GoHomeShellTests/AppSmokeTests`  
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add ios-shell/project.yml ios-shell/scripts/test.sh ios-shell/GoHomeShellTests ios-shell/GoHomeShellUITests ios-shell/GoHomeShell/Sources/App/AppRoute.swift ios-shell/GoHomeShell.xcodeproj
git commit -m "test(ios): add native unit and UI targets"
```

### Task 2: Typed API Client

**Files:**
- Create: `ios-shell/GoHomeShell/Sources/Networking/APIClient.swift`
- Create: `ios-shell/GoHomeShell/Sources/Networking/APIError.swift`
- Create: `ios-shell/GoHomeShell/Sources/Networking/Endpoint.swift`
- Test: `ios-shell/GoHomeShellTests/APIClientTests.swift`

- [x] **Step 1: Write transport tests with URLProtocol**

Test authorization, JSON decode, 401 mapping, server detail mapping, cancellation, and ETag 304 handling.

```swift
let response: BootstrapResponse = try await client.send(.bootstrap)
XCTAssertEqual(response.user.phone, "13800000000")
XCTAssertEqual(URLProtocolStub.lastRequest?.value(forHTTPHeaderField: "Authorization"), "Bearer token")
```

- [x] **Step 2: Run and verify failure**

Run:

```bash
cd ios-shell
xcodebuild test -project GoHomeShell.xcodeproj -scheme GoHomeShell \
  -destination 'platform=iOS Simulator,name=iPhone 16 Pro' \
  -only-testing:GoHomeShellTests/APIClientTests
```

Expected: FAIL because `APIClient` is undefined.

- [x] **Step 3: Implement actor client**

```swift
actor APIClient {
    private let baseURL: URL
    private let session: URLSession
    private let token: @Sendable () async -> String?

    func send<Response: Decodable>(_ endpoint: Endpoint<Response>) async throws -> Response {
        var request = endpoint.request(baseURL: baseURL)
        if let value = await token() { request.setValue("Bearer \(value)", forHTTPHeaderField: "Authorization") }
        let (data, response) = try await session.data(for: request)
        return try endpoint.decode(data: data, response: response)
    }
}
```

Use `GoHomeAPIBaseURL` from `Info.plist`; do not reuse `GoHomeWebAppURL`.

- [x] **Step 4: Run tests**

Run: `ios-shell/scripts/test.sh GoHomeShellTests/APIClientTests`

Expected: all API client tests PASS.

- [x] **Step 5: Commit**

```bash
git add ios-shell/GoHomeShell/Sources/Networking ios-shell/GoHomeShellTests/APIClientTests.swift ios-shell/GoHomeShell/Config/Info.plist
git commit -m "feat(ios): add typed cloud API client"
```

### Task 3: Keychain And Account-Scoped Cache

**Files:**
- Create: `Sources/Storage/KeychainAuthStore.swift`
- Create: `Sources/Storage/DiskCache.swift`
- Test: `GoHomeShellTests/AuthAndCacheTests.swift`

- [x] **Step 1: Write failing isolation tests**

Assert token round-trip, logout deletion, user/family cache key separation, expired-entry rejection, and prior-account data not returned after switching scope.

- [x] **Step 2: Run and verify failure**

Run: `ios-shell/scripts/test.sh GoHomeShellTests/AuthAndCacheTests`  
Expected: FAIL because stores do not exist.

- [x] **Step 3: Implement stores**

```swift
struct CacheScope: Hashable, Codable {
    let userID: String
    let familyID: String
}

actor DiskCache {
    func read<Value: Decodable>(_ type: Value.Type, key: String, scope: CacheScope) throws -> Value?
    func write<Value: Encodable>(_ value: Value, key: String, scope: CacheScope) throws
    func clear(scope: CacheScope) throws
}
```

Store Keychain items under service `com.gohome.family.auth`; use `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`.

- [x] **Step 4: Run tests and inspect filesystem protection**

Run: `ios-shell/scripts/test.sh GoHomeShellTests/AuthAndCacheTests`

Expected: PASS; cache files use complete-unless-open data protection and contain no token.

- [x] **Step 5: Commit**

```bash
git add ios-shell/GoHomeShell/Sources/Storage ios-shell/GoHomeShellTests/AuthAndCacheTests.swift
git commit -m "feat(ios): add secure auth and scoped cache"
```

### Task 4: Repository And Session Coordinator

**Files:**
- Create: `Sources/Models/AppModels.swift`
- Create: `Sources/Repository/AppRepository.swift`
- Create: `Sources/App/AppModel.swift`
- Create: `Sources/App/AppEnvironment.swift`
- Test: `GoHomeShellTests/AppRepositoryTests.swift`

- [x] **Step 1: Write stale-while-revalidate tests**

Seed cached bootstrap/home data, delay the network response, and assert the first emitted state is cached while the second is refreshed. Assert a refresh error preserves content and sets only `staleReason`.

- [x] **Step 2: Run and verify failure**

Expected: FAIL because repository types are undefined.

- [x] **Step 3: Implement state contract**

```swift
struct Loadable<Value: Equatable>: Equatable {
    var value: Value?
    var isRefreshing = false
    var staleReason: String?
}

@MainActor final class AppModel: ObservableObject {
    @Published private(set) var route: AppRoute = .launching
    @Published private(set) var bootstrap = Loadable<BootstrapResponse>()
}
```

`AppRepository.bootstrap()` reads cache first and revalidates once. Concurrent views share the same in-flight task.

- [x] **Step 4: Run repository tests**

Run: `ios-shell/scripts/test.sh GoHomeShellTests/AppRepositoryTests`

Expected: PASS; no state transition clears a non-nil value during refresh.

- [x] **Step 5: Commit**

```bash
git add ios-shell/GoHomeShell/Sources/Models ios-shell/GoHomeShell/Sources/Repository ios-shell/GoHomeShell/Sources/App ios-shell/GoHomeShellTests/AppRepositoryTests.swift
git commit -m "feat(ios): add cached app repository and session state"
```

### Task 5: Native Root, Login, And Registration

**Files:**
- Replace: `Sources/GoHomeShellApp.swift`
- Create: `Sources/App/GoHomeAppDelegate.swift`
- Create: `Sources/App/AppRootView.swift`
- Create: `Sources/Features/Auth/AuthView.swift`
- Create: `Sources/Features/Auth/AuthViewModel.swift`
- Test: `GoHomeShellUITests/AuthFlowTests.swift`

- [x] **Step 1: Write UI tests**

Launch with `-uiTestState signedOut`; assert phone input, request-code button, code input, and login/create segmented mode. Assert the view hierarchy contains no `WKWebView` accessibility element.

- [x] **Step 2: Run and verify failure**

Expected: FAIL because WebView launch UI is still the root.

- [x] **Step 3: Replace root with native routing**

```swift
struct AppRootView: View {
    @EnvironmentObject private var model: AppModel
    var body: some View {
        switch model.route {
        case .launching: NativeLaunchView()
        case .signedOut: AuthView()
        case .onboarding(let step): OnboardingCoordinatorView(step: step)
        case .main: MainTabView()
        }
    }
}
```

Move `GoHomeAppDelegate` out of `GoHomeShellRuntime.swift` into its own file so push callbacks can be connected to the native coordinator later. Use labeled native text fields and inline validation. Do not show a full-screen spinner after cached bootstrap exists.

- [x] **Step 4: Run unit and UI tests**

Run: `ios-shell/scripts/test.sh GoHomeShellUITests/AuthFlowTests`

Expected: PASS for signed-out launch and authentication routing.

- [ ] **Step 5: Commit**

```bash
git add ios-shell/GoHomeShell/Sources/GoHomeShellApp.swift ios-shell/GoHomeShell/Sources/App ios-shell/GoHomeShell/Sources/Features/Auth ios-shell/GoHomeShellUITests/AuthFlowTests.swift
git commit -m "feat(ios): replace web root with native authentication"
```

### Task 6: Native Onboarding Coordinator

**Files:**
- Create: `Sources/Features/Onboarding/OnboardingCoordinatorView.swift`
- Create: `Sources/Features/Onboarding/FamilySetupView.swift`
- Create: `Sources/Features/Onboarding/ProfileSetupView.swift`
- Create: `Sources/Features/Onboarding/DeviceBindingView.swift`
- Create: `Sources/Features/Onboarding/CameraSetupView.swift`
- Create: `Sources/Services/BoxDiscoveryService.swift`
- Test: `GoHomeShellUITests/OnboardingFlowTests.swift`

- [ ] **Step 1: Write one UI test per server next step**

Stub bootstrap responses for `family`, `profile`, `device`, `camera`, and `complete`; assert each opens exactly its matching native screen and incomplete users cannot access tabs.

- [ ] **Step 2: Run and verify failure**

Expected: FAIL because onboarding views do not exist.

- [ ] **Step 3: Implement native steps**

Family supports create/join. Profile requires display name and at least one validated contact number. Device binding uses `NWBrowser` for `_gohome._tcp` and exchanges the cloud one-time credential. Camera setup writes cloud configuration and waits for versioned edge sync without blocking navigation.

- [ ] **Step 4: Run onboarding and legacy cloud verification**

Run:

```bash
cd ios-shell && xcodebuild test -project GoHomeShell.xcodeproj -scheme GoHomeShell -destination 'platform=iOS Simulator,name=iPhone 16 Pro'
cd .. && npm run verify:cloud-onboarding
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ios-shell/GoHomeShell/Sources/Features/Onboarding ios-shell/GoHomeShell/Sources/Services/BoxDiscoveryService.swift ios-shell/GoHomeShellUITests/OnboardingFlowTests.swift
git commit -m "feat(ios): add native household onboarding"
```
