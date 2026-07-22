#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
xcodegen generate

args=()
if [ "${1:-}" != "" ]; then
  args+=("-only-testing:$1")
fi

device_id="$(xcrun simctl list devices available -j | ruby -rjson -e '
  devices = JSON.parse(STDIN.read).fetch("devices").values.flatten
  match = devices.find { |device| device["name"] == "iPhone 16 Pro" && device["isAvailable"] }
  abort "No available iPhone 16 Pro simulator" unless match
  print match.fetch("udid")
')"

if [ "${#args[@]}" -gt 0 ]; then
  xcodebuild test \
    -project GoHomeShell.xcodeproj \
    -scheme GoHomeShell \
    -destination "platform=iOS Simulator,id=${device_id}" \
    "${args[@]}"
else
  xcodebuild test \
    -project GoHomeShell.xcodeproj \
    -scheme GoHomeShell \
    -destination "platform=iOS Simulator,id=${device_id}"
fi
