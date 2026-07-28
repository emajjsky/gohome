# iOS TestFlight Acceptance Checklist

Release candidate: `1.0.0 (2)`

## Automated Gates

- [x] Full native unit and UI test suite passes.
- [x] Release metadata and privacy-manifest verification passes.
- [x] Generic iOS device archive succeeds with automatic signing.
- [x] App Store Connect accepts the uploaded package.
- [ ] App Store Connect finishes processing and exposes the build to TestFlight.

## Physical Device

- [ ] Cold launch reaches usable content without a blocking full-screen loader.
- [ ] Warm launch restores the signed-in household and cached tab content.
- [ ] Home, Guard, Memory, Community, and Profile switch without reloading the app shell.
- [ ] Backgrounding and foregrounding preserve the selected tab and current navigation.
- [ ] Logout clears private cached data and relaunch returns to authentication.

## Account And Household

- [ ] Registration, login, verification, and error states work on production services.
- [ ] Household creator can edit the cared-for profile; members are read-only.
- [ ] Box bind, unbind, pairing expiry, and account ownership are reflected immediately.
- [ ] Camera add, edit, pause, resume, and delete stay synchronized with the box.

## Guard

- [ ] Live video starts on cellular and Wi-Fi without requiring an app restart.
- [ ] Leaving and returning to Guard does not accumulate video latency.
- [ ] Only one live stream remains active when cameras or tabs change.
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
- [ ] APNs token registration succeeds against the production API.
- [ ] Foreground and background safety notifications open the correct event.
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
