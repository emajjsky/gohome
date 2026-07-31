# iOS TestFlight Acceptance Checklist

Distributed baseline: `1.0.0 (4)`

Candidate under validation: `1.0.0 (5)` (available to the internal TestFlight group; physical install pending)

## Automated Gates

- [x] Full native unit and UI test suite passes.
- [x] Release metadata and privacy-manifest verification passes.
- [x] Build 3 is installed from TestFlight and registers a production APNs token.
- [x] Build 3 receives controlled production APNs notifications on a physical device.
- [x] Foreground presentation regression test covers banner, notification center list, badge, and sound.
- [x] Build 4 generic iOS device archive succeeds with automatic signing.
- [x] App Store Connect accepts Build 4 with production APNs entitlement.
- [x] App Store Connect finishes processing and exposes Build 4 to TestFlight.
- [x] Build 5 is archived from the sole native project on `main` and accepted for upload.
- [x] Build 5 finishes Apple processing and is installable from TestFlight.

## Physical Device

- [x] Cold launch reaches usable content without a blocking full-screen loader.
- [ ] Warm launch restores the signed-in household and cached tab content.
- [x] Home, Guard, Memory, Community, and Profile switch without reloading the app shell.
- [ ] Backgrounding and foregrounding preserve the selected tab and current navigation.
- [ ] Logout clears private cached data and relaunch returns to authentication.

## Account And Household

- [ ] Registration, login, verification, and error states work on production services.
- [ ] Avatar, nickname, city, district, and system location save and survive relaunch.
- [ ] Household creator can edit the cared-for profile; members are read-only.
- [ ] Box bind, unbind, pairing expiry, and account ownership are reflected immediately.
- [ ] Camera add, edit, pause, resume, and delete stay synchronized with the box.

## Guard

- [ ] Live video starts on cellular and Wi-Fi without requiring an app restart.
- [ ] Leaving and returning to Guard does not accumulate video latency.
- [ ] Only one live stream remains active when cameras or tabs change.
- [ ] The box shows measured source FPS and the App shows successfully decoded display FPS; neither value is inferred from Hailo throughput.
- [ ] A 10-20 minute side-by-side run records both FPS values and visible clock delay without sustained queue growth.
- [ ] Skeleton, blur, and original privacy modes match the box state.
- [ ] Activity timeline and event list retain cached content while refreshing in the background.
- [ ] Event detail opens evidence, multimodal verification, and the correct camera context.

## Memory

- [ ] First photo or video selection appears in the composer without selecting twice.
- [ ] Photo selection is limited to nine; video selection is limited to one.
- [ ] Image grid, video preview, location, edit, delete, and publication time render correctly.
- [ ] Media compression, COS upload, retry, and failure recovery complete predictably.

## Messages And Notifications

- [ ] Notification permission state matches iOS Settings.
- [x] APNs token registration succeeds against the production API.
- [x] A TestFlight login replaces the old sandbox-only registration with an active production token.
- [x] An immediate server-initiated message is accepted by APNs and records queue/provider latency separately.
- [x] `/health.push_metrics` has no unexplained backlog; delivery `34636` has one attempt and one delivered/opened receipt chain.
- [ ] The same `message_id` or `event_id` produces one visible notification and one route per installation.
- [ ] Different messages and different physical devices still receive their own notification.
- [ ] Foreground and background safety notifications open the correct event.
- [x] A foreground notification remains visible in Notification Center on Build 4 and opens without creating another delivery.
- [ ] Return-home reminder produces a useful conversation prompt and native share sheet.
- [ ] Share completion and cancellation return to a stable screen.

## Community And Privacy

- [ ] Recommendation cards open provenance before any official external source.
- [ ] Source, suitability, disclosure, and verification date are visible.
- [ ] Location denial leaves Memory usable and explains how to enable access.
- [ ] Privacy and data controls reflect actual server behavior.
- [ ] VoiceOver labels, Dynamic Type, and minimum touch targets remain usable.

## Acceptance Evidence

Record the tested iPhone model, iOS version, network, account role, box ID, camera IDs,
start/end time, failed item, reproduction steps, and screenshot or screen recording for
every failed item. A blocked item is not a pass.

Debug installs are used only for explicitly approved local diagnosis. Release acceptance
uses TestFlight; a direct Xcode install must never be presented as the distributed build.

Build 5 physical checkpoint on 2026-07-31: the TestFlight install opened directly to the
restored household, all five native tabs were browsable, and live camera video opened.
Skeleton mode exposed that its rate badge depended on person-bearing pose packets. The
main-line fix now always reports decoded scene FPS and appends measured pose Hz when pose
packets arrive; 148 iOS tests and release metadata validation pass. A later TestFlight
build must verify that fix on the physical device before the FPS gate closes.
