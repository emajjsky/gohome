# Native Primary Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement native Home, Guard, Events, and Profile surfaces with immediate tab switching, real data, one selected video stream, and preserved navigation state.

**Architecture:** Each tab owns a `NavigationStack` and feature model while sharing one repository. Views consume cached view-state structs and never issue network calls. Guard isolates stream transport behind a protocol so current MJPEG can later be replaced without changing product views.

**Tech Stack:** SwiftUI, custom `Layout`, MapKit, CoreLocation, URLSession streaming, XCTest, XCUITest, SF Symbols.

---

## File Map

- Create `Sources/DesignSystem/*`: color, type, spacing, buttons, async image, module states.
- Create `Sources/Features/Main/MainTabView.swift`.
- Create `Sources/Features/Home/*`.
- Create `Sources/Features/Guard/*` and `Sources/Streaming/*`.
- Create `Sources/Features/Events/*`.
- Create `Sources/Features/Profile/*`.
- Create matching unit and UI tests.

### Task 1: Design Tokens And Persistent Tab Shell

**Files:**
- Create: `Sources/DesignSystem/GoHomeTheme.swift`
- Create: `Sources/DesignSystem/Components.swift`
- Create: `Sources/Features/Main/MainTabView.swift`
- Test: `GoHomeShellUITests/TabStateTests.swift`

- [ ] **Step 1: Write tab persistence UI test**

Scroll Home, switch to Guard, return Home, and assert the first visible article identifier remains unchanged. Measure each tab tap with `XCTClockMetric` and require median interaction duration under 0.1 seconds after warm-up.

- [ ] **Step 2: Run and verify failure**

Expected: FAIL because `MainTabView` does not exist.

- [ ] **Step 3: Implement five native tab roots**

Use `TabView(selection:)` with Home, Guard, Events, Discover, and Profile. Give each tab its own `NavigationPath` stored in a tab state object. Define white, near-black, and ginger-yellow tokens; card radius is 8, button radius is 8, icon buttons may be circular.

- [ ] **Step 4: Run tab tests**

Run: `ios-shell/scripts/test.sh GoHomeShellUITests/TabStateTests`

Expected: PASS; no tab root displays “正在读取” or a full-screen `ProgressView` after warm state.

- [ ] **Step 5: Commit**

```bash
git add ios-shell/GoHomeShell/Sources/DesignSystem ios-shell/GoHomeShell/Sources/Features/Main ios-shell/GoHomeShellUITests/TabStateTests.swift
git commit -m "feat(ios): add persistent native tab shell"
```

### Task 2: Home Header, Calendar, And Distance

**Files:**
- Create: `Sources/Features/Home/HomeView.swift`
- Create: `Sources/Features/Home/HomeViewModel.swift`
- Create: `Sources/Features/Home/CalendarStripView.swift`
- Create: `Sources/Features/Home/DistanceMapView.swift`
- Create: `Sources/Services/LocationService.swift`
- Test: `GoHomeShellTests/HomeViewModelTests.swift`

- [ ] **Step 1: Write view-model tests**

Assert real weather formatting, seven calendar days, permission-denied distance state, missing-household-location state, and a critical strip only for an unacknowledged real event.

- [ ] **Step 2: Run and verify failure**

Expected: FAIL because Home models are absent.

- [ ] **Step 3: Implement module-specific state**

```swift
enum DistanceState: Equatable {
    case value(kilometers: Double, travelMinutes: Int, user: CLLocationCoordinate2D, home: CLLocationCoordinate2D)
    case permissionRequired
    case homeLocationRequired
    case unavailable(lastUpdated: Date?)
}
```

Render each section without an outer page card. MapKit uses fixed height and does not resize while permission changes.

- [ ] **Step 4: Run tests and snapshot at 390x844 and 430x932**

Run: `ios-shell/scripts/test.sh GoHomeShellTests/HomeViewModelTests`

Expected: text fits, safe areas are respected, and denied location never displays invented distance.

- [ ] **Step 5: Commit**

```bash
git add ios-shell/GoHomeShell/Sources/Features/Home ios-shell/GoHomeShell/Sources/Services/LocationService.swift ios-shell/GoHomeShellTests/HomeViewModelTests.swift
git commit -m "feat(ios): add native calendar and distance home modules"
```

### Task 3: Real Editorial Masonry Feed

**Files:**
- Create: `Sources/Features/Home/MasonryLayout.swift`
- Create: `Sources/Features/Home/ArticleCard.swift`
- Create: `Sources/Features/Home/ArticleDetailRoute.swift`
- Test: `GoHomeShellTests/EditorialFeedTests.swift`

- [ ] **Step 1: Write filtering and layout tests**

Reject articles without HTTPS source, title, source name, or publishable category. Assert failed images retain title/source and use a category fallback. Assert anti-fraud incident messages are not accepted as articles.

- [ ] **Step 2: Run and verify failure**

Expected: FAIL because feed policy is undefined.

- [ ] **Step 3: Implement `MasonryLayout` and cards**

Use the iOS 16 `Layout` protocol with two equal columns and place the next subview in the shorter column. Cards render image ratio from metadata, category, title, source, and date. Tap opens `SFSafariViewController` through a SwiftUI representable; never route to Events.

- [ ] **Step 4: Run tests and VoiceOver audit**

Run: `ios-shell/scripts/test.sh GoHomeShellTests/EditorialFeedTests`

Expected: PASS; each card has one combined accessibility label and one Open action.

- [ ] **Step 5: Commit**

```bash
git add ios-shell/GoHomeShell/Sources/Features/Home/MasonryLayout.swift ios-shell/GoHomeShell/Sources/Features/Home/ArticleCard.swift ios-shell/GoHomeShell/Sources/Features/Home/ArticleDetailRoute.swift ios-shell/GoHomeShellTests/EditorialFeedTests.swift
git commit -m "feat(ios): add sourced editorial home feed"
```

### Task 4: Single-Stream Guard Runtime

**Files:**
- Create: `Sources/Streaming/CameraStreamClient.swift`
- Create: `Sources/Streaming/MJPEGStreamClient.swift`
- Create: `Sources/Features/Guard/GuardViewModel.swift`
- Test: `GoHomeShellTests/MJPEGStreamClientTests.swift`
- Test: `GoHomeShellTests/GuardViewModelTests.swift`

- [ ] **Step 1: Write multipart parser and lifecycle tests**

Feed fragmented multipart JPEG bytes and assert frame reconstruction. Select camera B after A and assert A is cancelled before B begins. Background the scene and assert stream cancellation; foreground and assert selected stream resumes once.

- [ ] **Step 2: Run and verify failure**

Expected: FAIL because streaming clients do not exist.

- [ ] **Step 3: Implement isolated stream protocol**

```swift
protocol CameraStreamClient: Sendable {
    func frames(cameraID: String) -> AsyncThrowingStream<Data, Error>
    func stop() async
}
```

The MJPEG actor owns one URLSession task, bounds the byte buffer, emits only complete JPEGs, and drops old frames when the consumer is behind.

- [ ] **Step 4: Run parser and lifecycle tests**

Run: `ios-shell/scripts/test.sh GoHomeShellTests/MJPEGStreamClientTests`

Expected: PASS with no retained URLSession task after cancellation.

- [ ] **Step 5: Commit**

```bash
git add ios-shell/GoHomeShell/Sources/Streaming ios-shell/GoHomeShell/Sources/Features/Guard/GuardViewModel.swift ios-shell/GoHomeShellTests/MJPEGStreamClientTests.swift ios-shell/GoHomeShellTests/GuardViewModelTests.swift
git commit -m "feat(ios): add single-camera native stream runtime"
```

### Task 5: Guard Product View

**Files:**
- Create: `Sources/Features/Guard/GuardView.swift`
- Create: `Sources/Features/Guard/CameraStageView.swift`
- Create: `Sources/Features/Guard/CameraThumbnailStrip.swift`
- Test: `GoHomeShellUITests/GuardFlowTests.swift`

- [ ] **Step 1: Write UI tests for two cameras**

Assert one stage image is updating, non-selected cameras show thumbnails, selection changes labels without a full-screen loading overlay, retry remains inside Guard, and pending event content appears only when fixtures contain an event.

- [ ] **Step 2: Run and verify failure**

Expected: FAIL because native Guard is absent.

- [ ] **Step 3: Implement stable 16:9 stage**

Use fixed aspect ratio, compact room/online/update overlays, camera selector, fullscreen control, and contextual retry. Do not expose YOLO, pose thresholds, raw RTSP, or algorithm pages.

- [ ] **Step 4: Run UI tests and physical-device stream check**

Run: `ios-shell/scripts/test.sh GoHomeShellUITests/GuardFlowTests`

Expected: PASS; Instruments/network log shows only one active stream request.

- [ ] **Step 5: Commit**

```bash
git add ios-shell/GoHomeShell/Sources/Features/Guard ios-shell/GoHomeShellUITests/GuardFlowTests.swift
git commit -m "feat(ios): build native guard experience"
```

### Task 6: Events And Evidence Detail

**Files:**
- Create: `Sources/Features/Events/EventsView.swift`
- Create: `Sources/Features/Events/EventsViewModel.swift`
- Create: `Sources/Features/Events/EventDetailView.swift`
- Create: `Sources/Features/Events/EvidenceTimelineView.swift`
- Test: `GoHomeShellTests/EventPresentationTests.swift`
- Test: `GoHomeShellUITests/EventActionTests.swift`

- [x] **Step 1: Write event presentation tests**

Map pending/handled/false-positive states, hide raw metric keys, group one SafetyIncident across multiple cameras, and produce human-readable cloud verification states.

- [x] **Step 2: Run and verify failure**

Expected: FAIL because native event presentation is absent.

- [x] **Step 3: Implement list, detail, and optimistic actions**

Use segmented filtering and evidence cards. `confirmSafe` and `markFalsePositive` update local state optimistically, disable duplicate submission by idempotency key, and roll back with an inline error if the server rejects the action.

- [x] **Step 4: Run targeted and full native tests**

Run: `ios-shell/scripts/test.sh GoHomeShellUITests/EventActionTests` and the full `xcodebuild test` suite.

Expected: PASS; event detail actions update the visible state, hide raw model output, and the full native suite remains green.

- [x] **Step 5: Commit**

```bash
git add ios-shell/GoHomeShell/Sources/Features/Events ios-shell/GoHomeShellTests/EventPresentationTests.swift ios-shell/GoHomeShellUITests/EventActionTests.swift
git commit -m "feat(ios): add native incident evidence and actions"
```

### Task 7: Profile And Configuration Ownership

**Files:**
- Create: `Sources/Features/Profile/ProfileView.swift`
- Create: `Sources/Features/Profile/FamilyMembersView.swift`
- Create: `Sources/Features/Profile/DeviceSettingsView.swift`
- Create: `Sources/Features/Profile/ContentPreferencesView.swift`
- Test: `GoHomeShellTests/ProfilePermissionTests.swift`

- [x] **Step 1: Write creator/member permission tests**

Assert only creator sees enabled algorithm/rule mutation controls; members receive read-only values. Assert “管理员” is absent from personal identity copy and role labels are “创建者/成员” only inside family management.

- [x] **Step 2: Run and verify failure**

Expected: FAIL because Profile views are absent.

- [x] **Step 3: Implement grouped native settings**

Sections: account, family, cared-for profile/contact, box/cameras, notifications, return-home/content preferences, Discover preferences, privacy/data, logout. Keep rule details in a pushed screen and enforce server permissions as well as UI state.

- [x] **Step 4: Run full primary-tab gate**

Run: `ios-shell/scripts/test.sh`  
Then install the Debug build on the connected iPhone and execute Home scroll retention, camera A/B switching, event confirmation, Profile permissions, and logout once.  
Expected: PASS; native unit/UI suites pass and all implemented tabs plus Profile remain responsive in the simulator. Physical-device install and logout still require the local signing/device pass.

- [x] **Step 5: Commit**

```bash
git add ios-shell/GoHomeShell/Sources/Features/Profile ios-shell/GoHomeShellTests/ProfilePermissionTests.swift
git commit -m "feat(ios): add native profile and owner permissions"
```
