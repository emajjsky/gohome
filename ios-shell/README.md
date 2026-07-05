# GoHome iOS Shell

This is the minimal native iOS shell for:

- requesting notification permission on a real iPhone
- calling `registerForRemoteNotifications()`
- receiving the APNs device token
- loading the existing `app-shell.html` through `WKWebView`
- bridging `push_token`, `app_install_id`, and notification launch payload back to the web layer

## Open the project

```bash
cd /Users/tanyihua/trae比赛/gohome/ios-shell
open GoHomeShell.xcodeproj
```

The repository already includes a minimal `GoHomeShell.xcodeproj`.

If you want to regenerate it from `project.yml`, run:

```bash
cd /Users/tanyihua/trae比赛/gohome/ios-shell
./generate.sh
```

If `xcodegen` is not installed yet, run `brew install xcodegen` first.

## Before running

1. Set the correct signing team in Xcode.
2. Keep the bundle id aligned with `GOHOME_APNS_TOPIC`.
3. Edit `GoHomeShell/Config/Info.plist` and set `GoHomeWebAppURL` to the reachable `app-shell.html` URL for the phone.
4. Keep `aps-environment` and the provisioning profile aligned with your target environment.

## Bridge contract

The web layer calls:

- `window.webkit.messageHandlers.gohomeNativeApp.postMessage({ method: "registerForPush", ... })`
- `window.webkit.messageHandlers.gohomeNativeApp.postMessage({ method: "consumeLaunchPayload", ... })`

The native shell responds by calling:

- `window.GoHomeEdge.resolveNativeBridgeResult(requestId, result, error)`
