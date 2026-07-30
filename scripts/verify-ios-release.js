"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const infoPath = path.join(root, "ios-shell/GoHomeShell/Config/Info.plist");
const entitlementsPath = path.join(root, "ios-shell/GoHomeShell/Config/GoHomeShell.entitlements");
const privacyPath = path.join(root, "ios-shell/GoHomeShell/Resources/PrivacyInfo.xcprivacy");
const projectPath = path.join(root, "ios-shell/GoHomeShell.xcodeproj/project.pbxproj");
const exportOptionsPath = path.join(root, "ios-shell/ExportOptions.plist");
const iconPath = path.join(root, "ios-shell/GoHomeShell/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png");

const info = fs.readFileSync(infoPath, "utf8");
const entitlements = fs.readFileSync(entitlementsPath, "utf8");
const privacy = fs.readFileSync(privacyPath, "utf8");
const project = fs.readFileSync(projectPath, "utf8");
const exportOptions = fs.readFileSync(exportOptionsPath, "utf8");

function hasNonEmptyPlistString(source, key) {
    const pattern = new RegExp(`<key>${key}</key>\\s*<string>([^<]+)</string>`);
    return pattern.test(source);
}

[
    "NSCameraUsageDescription",
    "NSLocalNetworkUsageDescription",
    "NSLocationWhenInUseUsageDescription",
    "NSMicrophoneUsageDescription",
    "NSPhotoLibraryUsageDescription",
].forEach((key) => assert.ok(hasNonEmptyPlistString(info, key), `${key} must be declared`));

assert.match(info, /<key>GoHomeAPIBaseURL<\/key>\s*<string>https:\/\//, "production API must use HTTPS");
assert.match(info, /<key>CFBundleIconName<\/key>\s*<string>AppIcon<\/string>/, "the built app must declare AppIcon");
assert.match(info, /<key>GoHomePushEnabled<\/key>\s*<true\/>/, "push must be enabled for the paid-team build");
assert.match(info, /<key>ITSAppUsesNonExemptEncryption<\/key>\s*<false\/>/, "system-only encryption must declare export-compliance exemption");
assert.doesNotMatch(info, /GoHomeWebAppURL/, "the removed WebView runtime must not return");
assert.match(entitlements, /<key>aps-environment<\/key>\s*<string>\$\(APS_ENVIRONMENT\)<\/string>/, "APNs entitlement must follow the build configuration");

assert.match(privacy, /<key>NSPrivacyTracking<\/key>\s*<false\/>/);
assert.match(privacy, /NSPrivacyAccessedAPICategoryUserDefaults/);
assert.match(privacy, /<string>CA92\.1<\/string>/);
[
    "Name",
    "PhoneNumber",
    "PhysicalAddress",
    "CoarseLocation",
    "PhotosorVideos",
    "OtherUserContent",
    "UserID",
    "DeviceID",
    "ProductInteraction",
    "SensitiveInfo",
].forEach((type) => assert.match(privacy, new RegExp(`NSPrivacyCollectedDataType${type}`)));
assert.doesNotMatch(privacy, /<key>NSPrivacyCollectedDataTypeTracking<\/key>\s*<true\/>/);

assert.match(project, /PrivacyInfo\.xcprivacy in Resources/);
assert.match(project, /Assets\.xcassets in Resources/);
assert.match(project, /MARKETING_VERSION = 1\.0\.0;/);
assert.match(project, /APS_ENVIRONMENT = development;/, "Debug builds must register sandbox APNs tokens");
assert.match(project, /APS_ENVIRONMENT = production;/, "Release builds must register production APNs tokens");
assert.match(project, /CURRENT_PROJECT_VERSION = [1-9]\d*;/, "the build number must be a positive integer");

assert.match(exportOptions, /<key>destination<\/key>\s*<string>upload<\/string>/);
assert.match(exportOptions, /<key>method<\/key>\s*<string>app-store-connect<\/string>/);
assert.match(exportOptions, /<key>signingStyle<\/key>\s*<string>automatic<\/string>/);
assert.match(exportOptions, /<key>teamID<\/key>\s*<string>X4M4T6Z4CJ<\/string>/);
assert.match(exportOptions, /<key>uploadSymbols<\/key>\s*<true\/>/);

const icon = fs.readFileSync(iconPath);
assert.equal(icon.toString("ascii", 1, 4), "PNG", "app icon must be a PNG");
assert.equal(icon.readUInt32BE(16), 1024, "app icon width must be 1024");
assert.equal(icon.readUInt32BE(20), 1024, "app icon height must be 1024");
assert.notEqual(icon[25], 4, "app icon must not use grayscale alpha");
assert.notEqual(icon[25], 6, "app icon must not use RGBA alpha");

console.log("iOS release metadata verification passed");
