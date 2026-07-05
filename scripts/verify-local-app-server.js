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

        const mediaResponse = await fetch(`${baseUrl}/api/v1/video/media/snapshots/events/test.jpg?playback_ticket=${session.ticket}`, {
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(mediaResponse.status, 200);
        assert.equal(await mediaResponse.text(), "fake-jpeg-content");

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
