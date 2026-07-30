# GoHome Native iOS Delivery Master Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the household-user WebView product with a native SwiftUI iOS 16 application and deliver a TestFlight-ready build without changing edge vision algorithms.

**Architecture:** Four ordered subplans produce independently testable increments: cloud-native contracts, native foundation and onboarding, native primary tabs, then messages/discover/APNs/TestFlight. The browser household UI remains available only as a migration oracle until native parity; edge admin, cloud operations, and legal/help web pages remain supported.

**Tech Stack:** Swift 5.10, SwiftUI, URLSession, Keychain Services, MapKit, CoreLocation, Network/Bonjour, UserNotifications, UIKit share sheet, Node.js, PostgreSQL 16, `node:test`, XcodeGen, XCTest, XCUITest.

---

## Ordered Subplans

1. [Cloud Native Contracts](2026-07-21-cloud-native-contracts.md)
2. [Native Foundation And Onboarding](2026-07-21-native-foundation-onboarding.md)
3. [Native Primary Tabs](2026-07-21-native-primary-tabs.md)
4. [Native Messages, Discover And TestFlight](2026-07-21-native-messages-discover-testflight.md)

## Delivery Gates

Distributed baseline: `1.0.0 (4)`. It is installed from TestFlight, registers a
production APNs token, and has completed a server-initiated production delivery with
one APNs attempt and one authenticated delivered/opened receipt chain. It adds
notification-center list presentation for foreground notifications; visual
notification-center retention, automatic event delivery, deep-link, and streaming
soak checks remain before Gate 4 is complete.

- [ ] **Gate 1: Cloud contract**

Run:

```bash
npm run db:migrate
npm run test:native-server
npm run verify:app-server
```

Expected: native v2 tests pass, legacy App/edge regression passes, and PostgreSQL mutations do not delete and reinsert complete tables.

- [ ] **Gate 2: Native onboarding**

Run:

```bash
cd ios-shell
xcodegen generate
xcodebuild test -project GoHomeShell.xcodeproj -scheme GoHomeShell \
  -destination 'platform=iOS Simulator,name=iPhone 16 Pro'
```

Expected: native unit/UI tests pass from signed-out state through the first incomplete onboarding destination; no `WKWebView` is the application root.

- [ ] **Gate 3: Native product parity**

Run:

```bash
ios-shell/scripts/test.sh
```

Then install the Debug build on the connected iPhone.

Expected: the native tabs are Home, Guard, Memory, Community, and Profile; tab
switches preserve state; Guard owns at most one active live stream and contains
Activity and Events; Memory and event actions persist through relaunch.

Current automated evidence on 2026-07-28: 112 iOS unit tests executed with zero
failures and one simulator Keychain skip; the primary and account/city UI audits
passed on iPhone 16 Pro and iPhone SE (3rd generation). Physical camera, APNs, and
production-account checks remain required.

Streaming checkpoint on 2026-07-30: both camera sources are HEVC at 15 FPS. The
bounded MJPEG relay currently reaches about 14-15 FPS for camera 3 and 11-12 FPS
for camera 4 without queue growth. Cloud scheduler stalls were removed and stream
metrics are available from `/health`. Gate 3 still requires a 10-20 minute physical
device foreground/background and tab-return soak; 30 FPS and vendor-app-equivalent
hardware decoding are not yet accepted claims.

Build 3 automated evidence on 2026-07-30: 122 unit tests executed with one
environment skip, and 22 UI tests pass with
zero failures. The pending candidate drops stale complete MJPEG frames at both the
network and view-model boundaries, decodes off the main actor, and displays measured
App decode FPS. The box console separately displays its measured camera source FPS.
The camera CGI capability contract exposes `15/10/5/1` as the available frame-rate
choices, so 15 FPS is a device capability result rather than a product-side guess.

Production APNs now scans once per second, reuses healthy HTTP/2 sessions, sends
immediate messages at priority 10, and records provider and queue latency. A direct
provider probe was accepted in 765 ms, but the only registered device token was still
`sandbox`; TestFlight acceptance remains blocked until build 3 registers a production
token and the same delivery is visible or acknowledged on the phone.

Distribution checkpoint on 2026-07-30: Xcode Accounts was refreshed from the stale
Personal Team cache to the enrolled individual team. App Store Connect accepted
`1.0.0 (3)` with delivery UUID `73c4d021-5d45-4723-8885-ff7b1f00ea81`. Apple remote
signing used the production Team Store profile and `aps-environment=production`; the
build is processing. This completes upload only, not TestFlight device or APNs acceptance.

Build 4 checkpoint on 2026-07-30: 123 unit tests and 22 UI tests passed with zero
failures, and release metadata verification passed. App Store Connect accepted
`1.0.0 (4)` with delivery UUID `477a252a-4426-4b94-8b9e-55bd21a660f5`. Apple remote
signing used `Apple Distribution: yihua tan` and `aps-environment=production`; the
package is installed through TestFlight. The cloud ops endpoint sent delivery `34636`
to the latest active production installation with one APNs attempt, and Build 4
returned delivered/opened on the same record. The user confirmed that the foreground
notification remained in Notification Center and opened it without creating another
delivery. Automatic business notification and event deep-link acceptance remain.

The notification state machine now treats a delivery key as one immutable attempt
chain. Scheduler reruns preserve retry deadlines and terminal outcomes; queueing never
sets message delivery time. APNs acceptance is `sent`, authenticated foreground or
open receipts advance the same record to `delivered`, and an open receipt additionally
sets `clicked_at`. `/health` reports backlog age, retry pressure, sent, delivered,
opened, and failed counts without conflating them.

Build 5 consolidation checkpoint on 2026-07-31: the native App, cloud contracts, and
latest Hailo/EACP edge pipeline are being merged into one `main` source line. The
release must be generated only from `ios-shell/GoHomeShell.xcodeproj`, display
`GoHome`, retain `com.gohome.family`, use production APNs entitlement, and contain no
legacy WebView application root. Archive upload, Apple processing, and TestFlight
physical-device acceptance remain separate gates.

- [ ] **Gate 4: Messaging and distribution**

Run:

```bash
xcodebuild archive -project ios-shell/GoHomeShell.xcodeproj \
  -scheme GoHomeShell -configuration Release \
  -archivePath build/GoHome.xcarchive
xcodebuild -exportArchive -archivePath build/GoHome.xcarchive \
  -exportOptionsPlist ios-shell/ExportOptions.plist \
  -exportPath build/TestFlight
```

Expected: archive and export succeed; return-home messages share through the native sheet; product recommendations have verified external sources; Release contains no demo OTP or remote household WebView root.

Build 3 must additionally prove that a stable `message_id` or `event_id` is
presented and routed at most once per installation while unrelated notifications
without a stable identifier remain deliverable.

The physical-device candidate now also exposes notification channel diagnostics
and one authenticated push self-test. APNs acceptance remains `sent`; only a
foreground receive receipt or user interaction may advance the same delivery to
`delivered`. Transient APNs transport failures reuse that delivery with bounded
backoff and must never create a second message for the incident.

## Worktree And Commit Discipline

- Create an isolated implementation worktree before Task 1 because the current main worktree contains active edge and documentation changes.
- Never modify `edge-agent/app/vision`, `edge-agent/app/worker.py`, algorithm tests, or Raspberry Pi deployment scripts from this line.
- Complete and commit each task before starting the next task.
- Rebase or merge only after each subplan's gate passes.
- Do not remove public household Web routes until Gate 4 passes on a physical iPhone.

## User Dependencies

Code work can proceed without these values, but Gate 4 cannot complete until the user provides or configures:

- active Apple Developer membership and App Store Connect access;
- final Bundle ID and development team;
- APNs Auth Key (`.p8`), Key ID, and Team ID;
- privacy/support URLs;
- SMS provider credentials for production phone verification;
- reviewed product-source links and any required affiliate disclosures.

## 2026-07-30 Stream And Location Follow-up

- Direct RTSP measurements show that both HEVC 640x360 substreams advertise 15 FPS, while camera 29 actually delivers about 11.2-12.0 FPS and camera 30 about 14.1-15.1 FPS. TCP and UDP are equivalent in this environment. Hailo Pose median latency is about 14 ms with zero inference failures, so the current visual gap is dominated by source jitter and the `HEVC -> JPEG -> HTTPS -> MJPEG -> UIImage` display path.
- `GuardViewModel` now decodes JPEG data and prepares display images off the main actor. `CameraStageView` receives a predecoded `UIImage`; the existing frame data remains available for compatibility. The targeted build and 14 tests pass. Physical-device installation and a 10-20 minute foreground/background and tab-switch soak remain required.
- Community services now resolve from the elder/home profile city and district. Missing home location disables non-emergency nearby services instead of falling back to the phone or account location. The next contract must persist home coordinates with source/freshness, use CoreLocation only for the phone coordinate, and calculate the user-to-home distance from these two explicit inputs.
- Do not claim vendor-App-equivalent smoothness until the physical soak passes. The long-term transport candidate is hardware-decoded H.264/HEVC over WebRTC or an equivalent bounded-latency channel, with MJPEG retained as fallback.
- Home coordinates are now explicit family profile data saved from a phone while at home. The current phone coordinate remains on-device for distance calculation, while Community uses only the fixed home coordinate. Missing data remains missing and never falls back to an unrelated city or phone location.
- Device event evidence is stored in private COS and read through authenticated signed redirects. Edge local evidence uses bounded retention and remains protected from recycling until cloud synchronization completes.
