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

Expected: all five tabs are native, tab switches preserve state, Guard owns at most one active live stream, and event actions persist through relaunch.

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
