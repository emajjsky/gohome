"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const mediaUnit = fs.readFileSync(
    path.join(root, "deploy/cloud-media/gohome-mediamtx.service"),
    "utf8",
);
const mediaConfig = fs.readFileSync(
    path.join(root, "deploy/cloud-media/mediamtx.yml"),
    "utf8",
);

const addressFamilies = mediaUnit.match(/^RestrictAddressFamilies=(.+)$/m);
assert.ok(addressFamilies, "MediaMTX must restrict its socket families explicitly");

const allowedFamilies = new Set(addressFamilies[1].trim().split(/\s+/));
assert.deepEqual(
    allowedFamilies,
    new Set(["AF_UNIX", "AF_INET", "AF_INET6", "AF_NETLINK"]),
    "MediaMTX needs route netlink for WebRTC ICE without broadening other socket families",
);
assert.match(mediaUnit, /^NoNewPrivileges=true$/m);
assert.match(mediaUnit, /^ProtectSystem=strict$/m);
assert.doesNotMatch(mediaUnit, /^PrivateNetwork=true$/m);

assert.match(mediaConfig, /^webrtc: true$/m);
assert.match(mediaConfig, /^webrtcAddress: 127\.0\.0\.1:8889$/m);
assert.match(mediaConfig, /^webrtcLocalUDPAddress: ":8189"$/m);
assert.match(mediaConfig, /^webrtcLocalTCPAddress: ":8189"$/m);
assert.match(mediaConfig, /^webrtcIPsFromInterfaces: false$/m);

console.log("cloud media deployment verification passed");
