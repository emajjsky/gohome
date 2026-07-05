#!/usr/bin/env node
"use strict";

const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { createLocalAppServer } = require("../local-app-server/server");

const DEVICE_TOKEN = "verify-device-token";
const APP_TOKEN = "verify-app-token";

function listen(server) {
    return new Promise((resolve, reject) => {
        server.once("error", reject);
        server.listen(0, "127.0.0.1", () => {
            const address = server.address();
            resolve(`http://127.0.0.1:${address.port}`);
        });
    });
}

async function requestJson(baseUrl, pathName, options = {}) {
    const response = await fetch(`${baseUrl}${pathName}`, {
        ...options,
        headers: {
            Accept: "application/json",
            ...(options.body && !(options.body instanceof Buffer) ? { "Content-Type": "application/json" } : {}),
            ...(options.headers || {}),
        },
    });
    const text = await response.text();
    const payload = text ? JSON.parse(text) : null;
    if (!response.ok) {
        throw new Error(`${options.method || "GET"} ${pathName} failed: ${response.status} ${text}`);
    }
    return payload;
}

async function main() {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "gohome-app-server-"));
    const app = createLocalAppServer({
        rootDir: path.resolve(__dirname, ".."),
        dataDir: tempDir,
        deviceToken: DEVICE_TOKEN,
        appToken: APP_TOKEN,
    });
    const baseUrl = await listen(app.server);

    try {
        const health = await requestJson(baseUrl, "/health");
        assert.equal(health.ok, true);

        const login = await requestJson(baseUrl, "/api/auth/login", {
            method: "POST",
            body: JSON.stringify({ email: "admin@gohome.local", password: "gohome" }),
        });
        assert.equal(login.token, APP_TOKEN);

        const registered = await requestJson(baseUrl, "/api/auth/register", {
            method: "POST",
            body: JSON.stringify({ email: "daughter@gohome.local", password: "secret123", display_name: "女儿" }),
        });
        assert.equal(registered.user.email, "daughter@gohome.local");

        const family = await requestJson(baseUrl, "/api/families", {
            method: "POST",
            body: JSON.stringify({ name: "测试家庭" }),
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(family.name, "测试家庭");

        const elderProfile = await requestJson(baseUrl, `/api/v1/families/${family.id}/elders/elder_primary/profile`, {
            method: "PUT",
            body: JSON.stringify({ display_name: "张阿姨", relationship: "母亲", city: "杭州" }),
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(elderProfile.display_name, "张阿姨");

        const bindingCode = await requestJson(baseUrl, "/api/device/binding-codes", {
            method: "POST",
            body: JSON.stringify({ family_id: family.id, expires_in_minutes: 10 }),
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(bindingCode.status, "active");

        const exchanged = await requestJson(baseUrl, "/api/device/token/exchange", {
            method: "POST",
            body: JSON.stringify({ code: bindingCode.code, device_id: "edge-test", device_name: "测试盒子" }),
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(exchanged.ok, true);
        assert.ok(exchanged.device_token);

        const heartbeat = await requestJson(baseUrl, "/api/v1/device/heartbeat", {
            method: "POST",
            body: JSON.stringify({ device_id: "edge-test", name: "测试盒子", status: "online" }),
            headers: { Authorization: `Bearer ${exchanged.device_token}` },
        });
        assert.equal(heartbeat.ok, true);

        const camera = await requestJson(baseUrl, "/api/cameras", {
            method: "POST",
            body: JSON.stringify({
                name: "客厅主视",
                room: "客厅",
                stream_url: "rtsp://192.168.1.20:554/stream1",
                enabled: true,
            }),
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(camera.room, "客厅");
        assert.equal(camera.connection_owner, "edge_agent");
        assert.equal(camera.stream_url, undefined);
        assert.equal(camera.status, "pending_edge_sync");

        const patchedCamera = await requestJson(baseUrl, `/api/cameras/${camera.id}`, {
            method: "PATCH",
            body: JSON.stringify({ enabled: false }),
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(patchedCamera.enabled, false);

        const testedCamera = await requestJson(baseUrl, `/api/cameras/${camera.id}/test`, {
            method: "POST",
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(testedCamera.ok, true);
        assert.equal(testedCamera.camera.status, "pending_edge_verify");

        const enabledCamera = await requestJson(baseUrl, `/api/cameras/${camera.id}`, {
            method: "PATCH",
            body: JSON.stringify({ enabled: true }),
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(enabledCamera.enabled, true);

        const deviceConfig = await requestJson(baseUrl, "/api/v1/device/config", {
            headers: { Authorization: `Bearer ${exchanged.device_token}` },
        });
        assert.equal(deviceConfig.ok, true);
        assert.equal(deviceConfig.cameras.length, 1);
        assert.equal(deviceConfig.cameras[0].stream_url, "rtsp://192.168.1.20:554/stream1");
        assert.equal(deviceConfig.cameras[0].enabled, true);

        const deviceSync = await requestJson(baseUrl, "/api/v1/device/sync", {
            method: "POST",
            body: JSON.stringify({
                device_id: "edge-test",
                config_version: deviceConfig.config_version,
                worker_running: true,
                status: { status: "online", sync_status: "healthy" },
                cameras: [
                    {
                        camera_id: camera.id,
                        local_camera_id: 11,
                        status: "online",
                        sync_status: "synced",
                        enabled: true,
                        last_error: "",
                    },
                ],
            }),
            headers: { Authorization: `Bearer ${exchanged.device_token}` },
        });
        assert.equal(deviceSync.ok, true);
        assert.equal(deviceSync.current_config_version, deviceConfig.config_version);

        const appCameras = await requestJson(baseUrl, "/api/app/cameras", {
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        const syncedCamera = appCameras.find((item) => String(item.id) === String(camera.id));
        assert.equal(syncedCamera.status, "online");
        assert.equal(syncedCamera.sync_status, "synced");
        assert.ok(syncedCamera.last_seen_at);

        const stableDeviceConfig = await requestJson(baseUrl, "/api/v1/device/config", {
            headers: { Authorization: `Bearer ${exchanged.device_token}` },
        });
        assert.equal(stableDeviceConfig.config_version, deviceConfig.config_version);

        const deleteProbe = await requestJson(baseUrl, "/api/cameras", {
            method: "POST",
            body: JSON.stringify({
                name: "删除同步验证",
                room: "验证",
                stream_url: "demo:delete_probe",
                enabled: true,
            }),
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        const deletedProbe = await requestJson(baseUrl, `/api/cameras/${deleteProbe.id}`, {
            method: "DELETE",
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(deletedProbe.ok, true);
        const deleteSync = await requestJson(baseUrl, "/api/v1/device/sync", {
            method: "POST",
            body: JSON.stringify({
                device_id: "edge-test",
                config_version: stableDeviceConfig.config_version,
                cameras: [
                    {
                        camera_id: deleteProbe.id,
                        status: "deleted",
                        sync_status: "synced",
                    },
                ],
            }),
            headers: { Authorization: `Bearer ${exchanged.device_token}` },
        });
        assert.equal(deleteSync.ok, true);
        const camerasAfterDeleteSync = await requestJson(baseUrl, "/api/app/cameras", {
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(camerasAfterDeleteSync.some((item) => String(item.id) === String(deleteProbe.id)), false);

        const imageBytes = Buffer.from("fake-jpeg-content");
        const media = await requestJson(
            baseUrl,
            "/api/v1/device/media-assets/upload?file_name=test.jpg&snapshot_path=events/test.jpg&content_type=image/jpeg&edge_event_id=42",
            {
                method: "POST",
                body: imageBytes,
                headers: {
                    Authorization: `Bearer ${DEVICE_TOKEN}`,
                    "Content-Type": "image/jpeg",
                },
            }
        );
        assert.equal(media.ok, true);
        assert.equal(media.asset.snapshot_path, "events/test.jpg");

        const eventPayload = {
            idempotency_key: "event:42",
            event_type: "fall_candidate",
            summary: "疑似跌倒",
            level: "critical",
            room: "客厅",
            camera_id: 1,
            snapshot_path: "events/test.jpg",
            occurred_at: "2026-07-05T10:00:00.000Z",
            payload: {
                rule: {
                    reason: "连续帧中出现倒地姿态证据。",
                    observed: { confirm_frames: 2, fall_score: 0.82 },
                },
                edge_upload: {
                    edge_event_id: 42,
                    edge_device_id: "edge-test",
                },
            },
        };
        const created = await requestJson(baseUrl, "/api/v1/device/events", {
            method: "POST",
            body: JSON.stringify(eventPayload),
            headers: { Authorization: `Bearer ${DEVICE_TOKEN}` },
        });
        assert.equal(created.ok, true);
        assert.equal(created.event.summary, "疑似跌倒");
        assert.equal(created.event.media_asset_id, media.asset.id);

        const events = await requestJson(baseUrl, "/api/app/events?limit=5&acknowledged=false", {
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(events.length, 1);
        assert.equal(events[0].type, "fall_candidate");

        const bindings = await requestJson(baseUrl, "/api/device-bindings?family_id=1", {
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(bindings.length, 0);

        const newFamilyBindings = await requestJson(baseUrl, `/api/device-bindings?family_id=${family.id}`, {
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(newFamilyBindings.length, 1);
        assert.equal(newFamilyBindings[0].device_id, "edge-test");

        const snapshot = await requestJson(baseUrl, "/api/app/cameras/1/snapshot/latest?allow_missing=1", {
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(snapshot.available, true);
        assert.equal(snapshot.snapshot_path, "events/test.jpg");

        const evaluation = await requestJson(baseUrl, "/api/app/cameras/1/evaluation/latest", {
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(evaluation.candidates.length, 1);
        assert.equal(evaluation.state.latest_event_type, "fall_candidate");

        const detail = await requestJson(baseUrl, `/api/app/events/${events[0].id}`, {
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(detail.payload.rule.observed.confirm_frames, 2);

        const patched = await requestJson(baseUrl, `/api/app/events/${events[0].id}`, {
            method: "PATCH",
            body: JSON.stringify({ acknowledged: true, resolution: "handled" }),
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(patched.acknowledged, true);
        assert.equal(patched.resolution, "handled");

        const session = await requestJson(baseUrl, "/api/v1/video/sessions", {
            method: "POST",
            body: JSON.stringify({ resource_type: "snapshot", snapshot_path: "events/test.jpg" }),
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.ok(session.ticket);

        const mediaResponse = await fetch(`${baseUrl}/api/v1/video/media/snapshots/events/test.jpg?playback_ticket=${session.ticket}`);
        assert.equal(mediaResponse.status, 200);
        assert.equal(await mediaResponse.text(), "fake-jpeg-content");

        const streamSession = await requestJson(baseUrl, "/api/v1/video/sessions", {
            method: "POST",
            body: JSON.stringify({ resource_type: "stream", camera_id: 1 }),
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        const streamResponse = await fetch(`${baseUrl}/api/v1/video/cameras/1/stream.mjpg?playback_ticket=${streamSession.ticket}`);
        assert.equal(streamResponse.status, 200);
        assert.match(streamResponse.headers.get("content-type") || "", /multipart\/x-mixed-replace/);
        streamResponse.body.cancel();

        console.log(JSON.stringify({
            ok: true,
            base_url: baseUrl,
            events: events.length,
            asset_id: media.asset.id,
            event_id: created.event.id,
            data_dir: tempDir,
        }, null, 2));
    } finally {
        app.server.close();
    }
}

main().catch((error) => {
    console.error(error);
    process.exit(1);
});
