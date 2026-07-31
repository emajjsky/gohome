# iOS TestFlight Acceptance Checklist

Distributed baseline: `1.0.0 (5)`

Candidate under validation: `1.0.0 (7)` (source fix pending final gates and upload)

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
- [x] Build 6 is archived from the sole native project on `main`, processed by Apple, and assigned to `比赛内测`.
- [ ] Build 7 rejects cached location samples, is archived from the sole native project, processed by Apple, and assigned to `比赛内测`.

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
- [ ] The household creator can save one fixed home location without rebinding the box; Home shows the current phone-to-home distance and Community uses only the fixed household location.
- [ ] Household members cannot change the fixed home location, and Community never falls back to the phone's current position.
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
packets arrive; the current main-line suite passes 152 iOS tests and release metadata
validation. A later TestFlight
build must verify that fix on the physical device before the FPS gate closes.

The same Build 5 pass exposed a migration gap for households bound before fixed home
coordinates were introduced: Home could not calculate return distance and Community
showed that the household location was unset. Main now gives household creators one
shared native setup flow from either surface. It preserves the existing cared-for
profile, saves the fixed household coordinate through the existing profile contract,
then refreshes Home and Profile without unbinding the box or restarting the App. The
next TestFlight build must verify save, relaunch persistence, phone-to-home distance,
member read-only behavior, and household-based Community results.

Build 6 release checkpoint on 2026-07-31: main passed 152 of 152 iOS tests,
the fixed-home-location cloud contract test, and release metadata verification. Xcode
archived `GoHome 1.0.0 (6)` from the sole native project and App Store Connect accepted
Delivery UUID `7a905a03-83ba-4e02-bd95-4a8457e6f8d4`. Apple processing completed and
the build is assigned to `比赛内测`. Physical installation and the open acceptance
items above remain required.

Build 6 physical location checkpoint on 2026-07-31: the App accepted an iOS cached
coordinate from an earlier trip and saved it as the fixed home location. Existing
locations also lacked a discoverable correction action. Build 6 therefore fails the
fixed-home-location gate. The Build 7 source candidate accepts only coordinates
produced after the current request begins, enforces a 200-meter accuracy ceiling,
uses a bounded 12-second update window, and exposes creator-only correction actions
from both Home and Community. It also applies the same freshness policy when
calculating the phone-to-home distance. TestFlight installation and correction at the
physical home remain required before this gate can pass.

Build 7 upload checkpoint on 2026-07-31: the sole native project archived and exported
`GoHome 1.0.0 (7)`. App Store Connect accepted the upload with Delivery UUID
`7555c324-63d1-4657-8d44-d7c3e86a7d21`; the package has production APNs entitlement,
`get-task-allow=false`, and is currently processing. Apple processing, internal-group
assignment, TestFlight installation, and physical location correction remain open.

Skeleton transport checkpoint on 2026-07-31: edge and cloud no longer cap the
safe-scene path at 1 FPS. Two-camera edge/cloud measurements are approximately 10-14 accepted
scene FPS with zero Hailo failures and zero camera reconnects; a person-bearing camera
produced 10.8 pose packets per second while an empty camera correctly stayed near idle.
These are transport measurements, not TestFlight display acceptance. Keep the Guard
screen open for 10-20 minutes, walk across each camera, background/foreground the App,
switch tabs and return, then record decoded FPS, POSE Hz, visible lag, privacy leakage,
temperature and reconnect count before checking the streaming gate.
