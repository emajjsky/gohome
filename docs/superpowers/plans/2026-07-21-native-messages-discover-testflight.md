# Native Messages, Discover And TestFlight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the return-home notification/contact workflow, add sourced non-medical product recommendations, connect APNs deep links, and produce a release archive suitable for TestFlight.

**Architecture:** Messages are persisted server objects with explicit user actions. Sharing uses `UIActivityViewController` and never fabricates WeChat delivery. Discover reads a server-curated catalog and opens verified HTTPS sources; no transaction objects exist. Native notification routing enters feature navigation through one typed deep-link coordinator.

**Tech Stack:** SwiftUI, UIKit share sheet, UserNotifications, APNs, SafariServices, XCTest/XCUITest, App Store Connect tooling.

---

## File Map

- Create `Sources/Features/Messages/*`.
- Create `Sources/Services/ShareService.swift`.
- Modify `Sources/App/GoHomeAppDelegate.swift`: route APNs callbacks without WebView navigation.
- Create `Sources/App/DeepLinkCoordinator.swift`.
- Create `Sources/Features/Discover/*`.
- Create `Sources/Services/InAppSafariView.swift`.
- Modify entitlements, Info.plist, project settings, and privacy manifest.
- Create `ios-shell/ExportOptions.plist` only with non-secret export configuration.
- Create `scripts/verify-ios-release-policy.sh`.

### Task 1: Native Message Inbox And Detail

**Files:**
- Create: `Sources/Features/Messages/MessageInboxView.swift`
- Create: `Sources/Features/Messages/MessageDetailView.swift`
- Create: `Sources/Features/Messages/MessageViewModel.swift`
- Test: `GoHomeShellTests/MessagePresentationTests.swift`

- [ ] **Step 1: Write message tests**

Assert a `return_home` message renders trigger reason, 2-3 topics, two editable variants, suggested time, and allowed actions. Assert safety alerts use event routing rather than casual contact copy.

- [ ] **Step 2: Run and verify failure**

Expected: FAIL because native message views do not exist.

- [ ] **Step 3: Implement inbox and detail**

Open the inbox from the Home bell. Detail uses editable `TextEditor` content initialized from a selected variant. It records `opened` once with an idempotency key and never displays a generic “sent” state.

- [ ] **Step 4: Run tests**

Run: `ios-shell/scripts/test.sh GoHomeShellTests/MessagePresentationTests`

Expected: PASS; opening the same message twice records one opened action.

- [ ] **Step 5: Commit**

```bash
git add ios-shell/GoHomeShell/Sources/Features/Messages ios-shell/GoHomeShellTests/MessagePresentationTests.swift
git commit -m "feat(ios): add return-home message detail"
```

### Task 2: System Sharing And Contact Outcomes

**Files:**
- Create: `Sources/Services/ShareService.swift`
- Create: `Sources/DesignSystem/ActivityView.swift`
- Modify: `Sources/Features/Messages/MessageDetailView.swift`
- Test: `GoHomeShellTests/MessageActionTests.swift`

- [ ] **Step 1: Write action-state tests**

Inject a share-service spy. Assert share presentation records `shared` only after the activity sheet completion callback, cancellation records no contact success, and `contacted`, `snoozed`, `dismissed`, and `returned_home` send distinct API actions.

- [ ] **Step 2: Run and verify failure**

Expected: FAIL because sharing is absent.

- [ ] **Step 3: Implement `UIActivityViewController` wrapper**

```swift
struct ActivityView: UIViewControllerRepresentable {
    let items: [Any]
    let completion: (Bool) -> Void
    func makeUIViewController(context: Context) -> UIActivityViewController {
        let controller = UIActivityViewController(activityItems: items, applicationActivities: nil)
        controller.completionWithItemsHandler = { _, completed, _, _ in completion(completed) }
        return controller
    }
}
```

Do not call `weixin://` as the primary action and do not infer recipient or delivery.

- [ ] **Step 4: Run tests and physical-device share check**

Run: `ios-shell/scripts/test.sh GoHomeShellTests/MessageActionTests`

Expected: PASS; WeChat appears only when installed and enabled by iOS.

- [ ] **Step 5: Commit**

```bash
git add ios-shell/GoHomeShell/Sources/Services/ShareService.swift ios-shell/GoHomeShell/Sources/DesignSystem/ActivityView.swift ios-shell/GoHomeShell/Sources/Features/Messages/MessageDetailView.swift ios-shell/GoHomeShellTests/MessageActionTests.swift
git commit -m "feat(ios): close message sharing and outcome flow"
```

### Task 3: APNs Registration And Typed Deep Links

**Files:**
- Create: `Sources/App/DeepLinkCoordinator.swift`
- Modify: `Sources/App/GoHomeAppDelegate.swift`
- Modify: `Sources/GoHomeShellApp.swift`
- Modify: `Config/GoHomeShell.entitlements`
- Modify: `Config/Info.plist`
- Test: `GoHomeShellTests/DeepLinkCoordinatorTests.swift`

- [ ] **Step 1: Write deep-link tests**

Test `gohome://message/:id`, `gohome://event/:id`, and APNs payload equivalents. Reject arbitrary web URLs and cross-family identifiers. Assert notification permission is requested only after onboarding completion.

- [ ] **Step 2: Run and verify failure**

Expected: FAIL because routing still points into WebView paths.

- [ ] **Step 3: Implement native notification routing**

Convert AppDelegate callbacks into typed `AppDestination.message(id:)` or `.event(id:)` and publish them to the active tab's navigation path. Add `aps-environment` entitlement through Xcode signing and set `GoHomePushEnabled` per build configuration rather than a hardcoded production claim.

- [ ] **Step 4: Run local notification and payload tests**

Run: `ios-shell/scripts/test.sh GoHomeShellTests/DeepLinkCoordinatorTests`

Expected: PASS; tapping a test notification opens the correct native detail without loading HTML.

- [ ] **Step 5: Commit**

```bash
git add ios-shell/GoHomeShell/Sources/App/DeepLinkCoordinator.swift ios-shell/GoHomeShell/Sources/App/GoHomeAppDelegate.swift ios-shell/GoHomeShell/Sources/GoHomeShellApp.swift ios-shell/GoHomeShell/Config ios-shell/GoHomeShellTests/DeepLinkCoordinatorTests.swift
git commit -m "feat(ios): route APNs into native destinations"
```

### Task 4: Discover Feed Policy And Layout

**Files:**
- Create: `Sources/Features/Discover/DiscoverView.swift`
- Create: `Sources/Features/Discover/DiscoverViewModel.swift`
- Create: `Sources/Features/Discover/ProductCard.swift`
- Test: `GoHomeShellTests/DiscoverPolicyTests.swift`

- [ ] **Step 1: Write client policy tests**

Reject products with prohibited categories, non-HTTPS links, missing source/brand/image, or expired verification. Assert camera event fields are absent from recommendation reasons.

- [ ] **Step 2: Run and verify failure**

Expected: FAIL because Discover models are absent.

- [ ] **Step 3: Implement categories and feed**

Categories: household safety, lighting, daily living, storage, communication, and non-medical travel. Use a compact two-column layout with image, brand/name, suitability labels, and source. Do not display Add to Cart, Buy, Order, stock, or delivery controls.

- [ ] **Step 4: Run tests and empty/error visual audit**

Run: `ios-shell/scripts/test.sh GoHomeShellTests/DiscoverPolicyTests`

Expected: PASS; empty catalog provides one “调整偏好” action and no fake product.

- [ ] **Step 5: Commit**

```bash
git add ios-shell/GoHomeShell/Sources/Features/Discover ios-shell/GoHomeShellTests/DiscoverPolicyTests.swift
git commit -m "feat(ios): add sourced non-medical recommendations"
```

### Task 5: Product Detail And Verified External Navigation

**Files:**
- Create: `Sources/Features/Discover/ProductDetailView.swift`
- Create: `Sources/Services/InAppSafariView.swift`
- Test: `GoHomeShellUITests/DiscoverNavigationTests.swift`

- [ ] **Step 1: Write navigation tests**

Assert product detail displays source, verification date, suitability, limitations, and disclosure. Reject an expired or non-HTTPS source without routing elsewhere.

- [ ] **Step 2: Run and verify failure**

Expected: FAIL because product detail is absent.

- [ ] **Step 3: Implement in-app Safari action**

Use `SFSafariViewController` for valid HTTPS URLs. Label the action “查看来源” rather than “购买” when price/merchant transaction semantics are not guaranteed. Preserve tab state on return.

- [ ] **Step 4: Run UI tests**

Run: `ios-shell/scripts/test.sh GoHomeShellUITests/DiscoverNavigationTests`

Expected: PASS; no unrelated event or home navigation occurs.

- [ ] **Step 5: Commit**

```bash
git add ios-shell/GoHomeShell/Sources/Features/Discover/ProductDetailView.swift ios-shell/GoHomeShell/Sources/Services/InAppSafariView.swift ios-shell/GoHomeShellUITests/DiscoverNavigationTests.swift
git commit -m "feat(ios): add verified product source detail"
```

### Task 6: Accessibility, Privacy, And Release Configuration

**Files:**
- Create: `ios-shell/GoHomeShell/Resources/PrivacyInfo.xcprivacy`
- Create: `scripts/verify-ios-release-policy.sh`
- Modify: `ios-shell/project.yml`
- Modify: `ios-shell/GoHomeShell/Config/Info.plist`
- Modify: `ios-shell/GoHomeShell/Config/GoHomeShell.entitlements`
- Test: `ios-shell/GoHomeShellUITests/AccessibilityTests.swift`

- [ ] **Step 1: Add failing release-policy checks**

Add a script test that scans Release plist/source configuration and fails on `GoHomeWebAppURL`, `000000`, empty privacy manifest, missing location purpose, or a root `GoHomeShellWebView()` reference.

- [ ] **Step 2: Run and verify failure**

Expected: FAIL on current remote-web configuration.

- [ ] **Step 3: Add privacy manifest and release settings**

Delete `GoHomeShellWebView.swift` and the obsolete web-state parts of `GoHomeShellRuntime.swift` after all native parity tests pass; if no native functionality remains in the runtime file, delete it completely. Declare only used required-reason APIs. Keep location When In Use. Add push/background capabilities only when used. Ensure product/article browsing stays in SafariServices and no unrestricted URL scheme allowlist remains.

- [ ] **Step 4: Run Dynamic Type, VoiceOver, and build checks**

Run `ios-shell/scripts/test.sh GoHomeShellUITests/AccessibilityTests` once with the UI test launch argument `-UIPreferredContentSizeCategoryName UICTContentSizeCategoryL` and once with `UICTContentSizeCategoryAccessibilityXXXL`, then:

```bash
xcodebuild build -project ios-shell/GoHomeShell.xcodeproj -scheme GoHomeShell \
  -configuration Release -destination 'generic/platform=iOS'
```

Expected: BUILD SUCCEEDED and accessibility tests PASS.

- [ ] **Step 5: Commit**

```bash
git add -A ios-shell/GoHomeShell/Sources/GoHomeShellWebView.swift ios-shell/GoHomeShell/Sources/GoHomeShellRuntime.swift ios-shell/GoHomeShell/Resources/PrivacyInfo.xcprivacy ios-shell/project.yml ios-shell/GoHomeShell/Config ios-shell/GoHomeShellUITests/AccessibilityTests.swift scripts/verify-ios-release-policy.sh
git commit -m "chore(ios): prepare privacy and release configuration"
```

### Task 7: Physical Device And TestFlight Acceptance

**Files:**
- Create: `ios-shell/ExportOptions.plist`
- Create: `docs/ios/testflight-checklist.md`
- Modify: `想家了吗-Implement.md`

- [ ] **Step 1: Create explicit acceptance checklist**

Include cold/warm launch, five-tab switching, account isolation, onboarding, one-stream Guard, event actions, notification deep links, share completion/cancellation, Discover source links, location denial, offline cache, logout, and relaunch.

- [ ] **Step 2: Run full automated gates**

```bash
npm test
npm run test:native-server
cd ios-shell && xcodegen generate
xcodebuild test -project GoHomeShell.xcodeproj -scheme GoHomeShell \
  -destination 'platform=iOS Simulator,name=iPhone 16 Pro'
```

Expected: all PASS.

- [ ] **Step 3: Run physical-device acceptance**

Install on the trusted iPhone, execute every checklist item, capture screenshots and timings, and record APNs as blocked rather than passed if credentials are unavailable.

- [ ] **Step 4: Archive and upload**

Archive, validate, and upload through Xcode Organizer or `xcrun altool/notarytool` successor supported by installed Xcode. Resolve signing/privacy failures rather than bypassing validation.

- [ ] **Step 5: Commit verified delivery evidence**

```bash
git add ios-shell/ExportOptions.plist docs/ios/testflight-checklist.md 想家了吗-Implement.md
git commit -m "docs(ios): record TestFlight acceptance"
```

Do not remove the public household Web entry until this task is complete and the user confirms the TestFlight build works on the target iPhone.
