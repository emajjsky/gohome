const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { MediaAccessError, MediaAccessService } = require("../media-access");
const { createLocalAppServer } = require("../server");

const AUTH_SECRET = "media-auth-secret-with-at-least-thirty-two-bytes";
const SHARED_SECRET = "mediamtx-caller-secret-with-at-least-thirty-two-bytes";

function expectMediaError(callback, statusCode) {
    assert.throws(callback, (error) => error instanceof MediaAccessError && error.statusCode === statusCode);
}

function listen(server) {
    return new Promise((resolve, reject) => {
        server.once("error", reject);
        server.listen(0, "127.0.0.1", () => resolve(`http://127.0.0.1:${server.address().port}`));
    });
}

async function authorize(baseURL, sharedSecret, payload) {
    return fetch(`${baseURL}/internal/mediamtx/auth?secret=${encodeURIComponent(sharedSecret)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
}

test("media access tokens bind read permission to family, camera, mode, path and expiry", () => {
    let now = Date.parse("2026-08-03T12:00:00Z");
    let privacyMode = "skeleton";
    let membershipActive = true;
    const camera = {
        id: "31",
        family_id: "8",
        device_id: "edge-alpha",
        enabled: true,
    };
    const service = new MediaAccessService({
        secret: AUTH_SECRET,
        whepBaseURL: "https://gohome.example/media",
        readTTLSeconds: 120,
        clock: () => now,
        resolveCamera: (cameraId) => cameraId === "31" ? camera : null,
        resolvePrivacyMode: () => privacyMode,
        canUserAccessFamily: (userId, familyId) => (
            membershipActive && String(userId) === "12" && String(familyId) === "8"
        ),
    });

    const session = service.issueReadSession({
        userId: "12",
        familyId: "8",
        deviceId: "edge-alpha",
        cameraId: "31",
        privacyMode: "skeleton",
    });
    assert.equal(session.display_transport, "whep-h264-v1");
    assert.equal(session.composition_owner, "edge");
    assert.equal(session.media_path, "live/edge-alpha/31");
    assert.equal(session.whep_url, "https://gohome.example/media/live/edge-alpha/31/whep");
    assert.equal(session.authorization.scheme, "Bearer");
    assert.ok(session.authorization.token.startsWith("m1."));
    assert.equal(session.whep_url.includes(session.authorization.token), false);

    expectMediaError(() => service.issueReadSession({
        userId: "13",
        familyId: "8",
        deviceId: "edge-alpha",
        cameraId: "31",
        privacyMode: "skeleton",
    }), 403);
    expectMediaError(() => service.issueReadSession({
        userId: "12",
        familyId: "8",
        deviceId: "edge-other",
        cameraId: "31",
        privacyMode: "skeleton",
    }), 403);
    expectMediaError(() => service.issueReadSession({
        userId: "12",
        familyId: "8",
        deviceId: "edge-alpha",
        cameraId: "31",
        privacyMode: "person_blur",
    }), 409);

    const authorized = service.authorize({
        action: "read",
        protocol: "webrtc",
        path: session.media_path,
        token: session.authorization.token,
    });
    assert.deepEqual(authorized, {
        action: "read",
        path: "live/edge-alpha/31",
        user_id: "12",
        family_id: "8",
        device_id: "edge-alpha",
        camera_id: "31",
    });

    expectMediaError(() => service.authorize({
        action: "read",
        protocol: "webrtc",
        path: "live/edge-alpha/32",
        token: session.authorization.token,
    }), 403);
    expectMediaError(() => service.authorize({
        action: "read",
        protocol: "rtsp",
        path: session.media_path,
        token: session.authorization.token,
    }), 403);
    const tampered = `${session.authorization.token.slice(0, -1)}x`;
    expectMediaError(() => service.authorize({
        action: "read",
        protocol: "webrtc",
        path: session.media_path,
        token: tampered,
    }), 401);

    privacyMode = "person_blur";
    expectMediaError(() => service.authorize({
        action: "read",
        protocol: "webrtc",
        path: session.media_path,
        token: session.authorization.token,
    }), 403);
    privacyMode = "skeleton";
    membershipActive = false;
    expectMediaError(() => service.authorize({
        action: "read",
        protocol: "webrtc",
        path: session.media_path,
        token: session.authorization.token,
    }), 403);
    membershipActive = true;
    now += 121_000;
    expectMediaError(() => service.authorize({
        action: "read",
        protocol: "webrtc",
        path: session.media_path,
        token: session.authorization.token,
    }), 401);
});

test("device publishing requires an issued token and exact camera ownership", () => {
    const camera = { id: "31", family_id: "8", device_id: "edge-alpha", enabled: true };
    const service = new MediaAccessService({
        secret: AUTH_SECRET,
        whepBaseURL: "https://gohome.example/media",
        resolveDeviceTokens: (deviceId) => deviceId === "edge-alpha" ? [{
            device_id: "edge-alpha",
            family_id: "8",
            token_hash: crypto.createHash("sha256").update("issued-device-token").digest("hex"),
            status: "active",
        }] : [],
        resolveCamera: (cameraId) => cameraId === "31" ? camera : null,
    });

    assert.deepEqual(service.authorize({
        action: "publish",
        protocol: "rtsp",
        path: "live/edge-alpha/31",
        user: "edge-alpha",
        password: "issued-device-token",
    }), {
        action: "publish",
        path: "live/edge-alpha/31",
        device_id: "edge-alpha",
        camera_id: "31",
    });
    expectMediaError(() => service.authorize({
        action: "publish",
        protocol: "rtsp",
        path: "live/edge-alpha/31",
        user: "edge-alpha",
        password: "wrong-token",
    }), 401);
    expectMediaError(() => service.authorize({
        action: "publish",
        protocol: "rtsp",
        path: "live/edge-alpha/31",
        user: "edge-other",
        password: "issued-device-token",
    }), 403);
    camera.device_id = "edge-other";
    expectMediaError(() => service.authorize({
        action: "publish",
        protocol: "rtsp",
        path: "live/edge-alpha/31",
        user: "edge-alpha",
        password: "issued-device-token",
    }), 403);
});

test("MediaMTX internal auth endpoint protects caller identity and returns status-only decisions", async () => {
    const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "gohome-media-access-"));
    const app = createLocalAppServer({
        rootDir: path.join(__dirname, "..", ".."),
        dataDir,
        mediaAuthSecret: AUTH_SECRET,
        mediaAuthSharedSecret: SHARED_SECRET,
        mediaWhepBaseURL: "https://gohome.example/media",
    });
    const familyId = 8801;
    const userId = 8802;
    const deviceId = "edge-integration";
    const cameraId = "8803";
    app.store.db.users.push({ id: userId, email: "media@example.test", display_name: "媒体用户" });
    app.store.db.families.push({ id: familyId, name: "媒体家庭", created_by_user_id: userId });
    app.store.db.family_members.push({
        id: "media-member",
        family_id: familyId,
        user_id: userId,
        role: "owner",
        status: "active",
    });
    app.store.db.devices[deviceId] = { id: deviceId, device_id: deviceId, family_id: familyId };
    app.store.db.device_tokens.push({
        id: "media-device-token",
        device_id: deviceId,
        family_id: familyId,
        token: "integration-device-token",
        status: "active",
    });
    app.store.db.cameras[cameraId] = {
        id: Number(cameraId),
        device_id: deviceId,
        family_id: familyId,
        enabled: true,
    };

    const baseURL = await listen(app.server);
    try {
        const deniedCaller = await authorize(baseURL, "wrong-secret", {
            action: "publish",
            protocol: "rtsp",
            path: `live/${deviceId}/${cameraId}`,
            user: deviceId,
            password: "integration-device-token",
        });
        assert.equal(deniedCaller.status, 403);

        const challenge = await authorize(baseURL, SHARED_SECRET, {
            action: "publish",
            protocol: "rtsp",
            path: `live/${deviceId}/${cameraId}`,
            user: "",
            password: "",
        });
        assert.equal(challenge.status, 401);

        const published = await authorize(baseURL, SHARED_SECRET, {
            action: "publish",
            protocol: "rtsp",
            path: `live/${deviceId}/${cameraId}`,
            user: deviceId,
            password: "integration-device-token",
        });
        assert.equal(published.status, 204);
        assert.equal((await published.text()).length, 0);

        const session = app.mediaAccessService.issueReadSession({
            userId,
            familyId,
            deviceId,
            cameraId,
            privacyMode: "original",
        });
        const read = await authorize(baseURL, SHARED_SECRET, {
            action: "read",
            protocol: "webrtc",
            path: session.media_path,
            token: session.authorization.token,
        });
        assert.equal(read.status, 204);

        app.store.db.care_preferences[String(familyId)] = {
            family_id: familyId,
            metadata: { video_privacy: { minimum_mode: "skeleton" } },
        };
        const staleMode = await authorize(baseURL, SHARED_SECRET, {
            action: "read",
            protocol: "webrtc",
            path: session.media_path,
            token: session.authorization.token,
        });
        assert.equal(staleMode.status, 403);

        const health = await fetch(`${baseURL}/health`).then((response) => response.json());
        assert.deepEqual(health.media_access, {
            configured: true,
            transport: "whep-h264-v1",
            composition_owner: "edge",
            read_ttl_seconds: 120,
            whep_base_url: "https://gohome.example/media",
            mediamtx_auth_configured: true,
        });
        assert.equal(JSON.stringify(health).includes(AUTH_SECRET), false);
        assert.equal(JSON.stringify(health).includes(SHARED_SECRET), false);
    } finally {
        await new Promise((resolve) => app.server.close(resolve));
        fs.rmSync(dataDir, { recursive: true, force: true });
    }
});
