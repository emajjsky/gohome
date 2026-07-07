#!/usr/bin/env node
"use strict";

const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { createDefaultDb, createLocalAppServer, normalizeDb } = require("../local-app-server/server");
const { createDbFromCloudRows, TABLE_ORDER } = require("../local-app-server/postgres-store");
const { buildCloudSeedBundle } = require("./export-local-app-db");

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

function schemaColumns(sql, tableName) {
    const escapedTable = tableName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const match = sql.match(new RegExp(`create table if not exists ${escapedTable}\\s*\\((.*?)\\);`, "is"));
    if (!match) return null;
    const columns = new Set();
    for (const rawLine of match[1].split("\n")) {
        const line = rawLine.trim().replace(/,$/, "");
        if (!line || /^(primary|unique|foreign|constraint|check)\b/i.test(line)) continue;
        columns.add(line.split(/\s+/)[0].replace(/"/g, ""));
    }
    return columns;
}

function assertSeedBundleMatchesSchema(seedBundle) {
    const schemaSql = fs.readFileSync(path.resolve(__dirname, "../local-app-server/migrations/001_initial_schema.sql"), "utf8");
    for (const tableName of TABLE_ORDER) {
        const columns = schemaColumns(schemaSql, tableName);
        assert.ok(columns, `missing schema table: ${tableName}`);
        for (const row of seedBundle.tables[tableName] || []) {
            for (const column of Object.keys(row)) {
                assert.ok(columns.has(column), `missing schema column: ${tableName}.${column}`);
            }
        }
    }
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

        const localIdOnlySync = await requestJson(baseUrl, "/api/v1/device/sync", {
            method: "POST",
            body: JSON.stringify({
                device_id: "edge-test",
                config_version: stableDeviceConfig.config_version,
                cameras: [
                    {
                        camera_id: 11,
                        status: "online",
                        sync_status: "synced",
                        enabled: true,
                        last_error: "",
                    },
                ],
            }),
            headers: { Authorization: `Bearer ${exchanged.device_token}` },
        });
        assert.equal(localIdOnlySync.ok, true);
        assert.equal(String(localIdOnlySync.updated_cameras[0].id), String(camera.id));

        const camerasAfterLocalIdOnlySync = await requestJson(baseUrl, "/api/app/cameras", {
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(camerasAfterLocalIdOnlySync.length, 1);
        assert.equal(camerasAfterLocalIdOnlySync.some((item) => String(item.id) === "11"), false);

        const configAfterLocalIdOnlySync = await requestJson(baseUrl, "/api/v1/device/config", {
            headers: { Authorization: `Bearer ${exchanged.device_token}` },
        });
        assert.equal(configAfterLocalIdOnlySync.cameras.length, 1);
        assert.equal(String(configAfterLocalIdOnlySync.cameras[0].id), String(camera.id));

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
            camera_id: 11,
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
        assert.equal(String(created.event.camera_id), String(camera.id));
        assert.equal(String(created.event.payload.edge_camera_id), "11");
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

        const carePreferences = await requestJson(baseUrl, `/api/v1/families/${family.id}/care-preferences`, {
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(carePreferences.family_id, family.id);
        assert.equal(carePreferences.frequency, "daily");
        assert.equal(carePreferences.image_generation_enabled, false);

        const updatedCarePreferences = await requestJson(baseUrl, `/api/v1/families/${family.id}/care-preferences`, {
            method: "PUT",
            body: JSON.stringify({
                interests: ["天气", "越剧"],
                image_generation_enabled: true,
                image_provider: "wan",
                image_model: "wan2.7",
                content_recommendations_enabled: false,
            }),
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(updatedCarePreferences.image_generation_enabled, true);
        assert.equal(updatedCarePreferences.image_model, "wan2.7");

        const careCard = await requestJson(baseUrl, `/api/v1/app/care-cards/today?family_id=${family.id}`, {
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(careCard.card_type, "daily");
        assert.ok(careCard.facts.length >= 3);
        assert.equal(careCard.image_mode, "pending_provider");
        assert.ok(careCard.actions.some((action) => action.key === "call"));

        const generatedCareCard = await requestJson(baseUrl, "/api/v1/internal/care-cards/generate", {
            method: "POST",
            body: JSON.stringify({ family_id: family.id, force: true }),
            headers: { Authorization: `Bearer ${APP_TOKEN}` },
        });
        assert.equal(generatedCareCard.ok, true);
        assert.equal(generatedCareCard.card.card_id, careCard.card_id);

        const opsConfig = await requestJson(baseUrl, "/api/v1/ops/service-config", {
            headers: {},
        });
        assert.equal(opsConfig.ok, true);
        assert.equal(opsConfig.secret_policy.user_configurable, false);
        assert.equal(opsConfig.secret_policy.database, "no_plain_secret");
        assert.ok(opsConfig.model_capabilities.some((capability) => capability.capability_id === "multimodal-language"));
        assert.ok(opsConfig.model_capabilities.some((capability) => capability.capability_id === "care-card-image" && capability.aspect_ratio === "4:7"));

        const appTokenCannotWriteModelConfig = await fetch(`${baseUrl}/api/v1/model-providers/care-card-image`, {
            method: "PUT",
            body: JSON.stringify({ model: "wan2.7", api_key: "secret" }),
            headers: { Authorization: `Bearer ${APP_TOKEN}`, "Content-Type": "application/json" },
        });
        assert.equal(appTokenCannotWriteModelConfig.status, 405);

        const opsTempDir = fs.mkdtempSync(path.join(os.tmpdir(), "gohome-app-server-ops-"));
        const opsApp = createLocalAppServer({
            rootDir: path.resolve(__dirname, ".."),
            dataDir: opsTempDir,
            deviceToken: DEVICE_TOKEN,
            appToken: APP_TOKEN,
            opsToken: "verify-ops-token",
        });
        const opsBaseUrl = await listen(opsApp.server);
        try {
            const blockedOpsPage = await fetch(`${opsBaseUrl}/ops.html`);
            assert.equal(blockedOpsPage.status, 403);
            const blockedOpsConfig = await fetch(`${opsBaseUrl}/api/v1/ops/service-config`, {
                headers: { Authorization: `Bearer ${APP_TOKEN}` },
            });
            assert.equal(blockedOpsConfig.status, 403);
            const allowedOpsPage = await fetch(`${opsBaseUrl}/ops.html?ops_token=verify-ops-token`);
            assert.equal(allowedOpsPage.status, 200);
            assert.match(allowedOpsPage.headers.get("content-type") || "", /text\/html/);
            const allowedOpsConfig = await requestJson(opsBaseUrl, "/api/v1/ops/service-config?ops_token=verify-ops-token");
            assert.equal(allowedOpsConfig.secret_policy.user_configurable, false);
        } finally {
            opsApp.server.close();
        }

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

        const seedBundle = buildCloudSeedBundle(app.store.db, { source: "verify-local-app-server" });
        assert.equal(seedBundle.schema_version, "001_initial_schema");
        assert.equal(seedBundle.tables.users.length, 2);
        assert.equal(seedBundle.tables.families.length, 2);
        assert.equal(seedBundle.tables.family_members.length, 2);
        assert.equal(seedBundle.tables.device_tokens.length, 1);
        assert.equal(seedBundle.tables.device_tokens[0].token_hash.length, 64);
        assert.equal(seedBundle.tables.cameras.length, 1);
        assert.equal(seedBundle.tables.camera_secrets.length, 1);
        assert.equal(seedBundle.tables.events.length, 1);
        assert.equal(seedBundle.tables.events[0].camera_id, String(camera.id));
        assert.equal(seedBundle.tables.media_assets.length, 1);
        assert.equal(seedBundle.tables.care_preferences.length, 1);
        assert.equal(seedBundle.tables.care_preferences[0].image_model, "wan2.7");
        assert.equal(seedBundle.tables.care_cards.length, 1);
        assert.equal(seedBundle.tables.care_cards[0].card_id, careCard.card_id);
        assert.equal(seedBundle.tables.model_providers.length, 0);
        assertSeedBundleMatchesSchema(seedBundle);

        const restoredDb = normalizeDb(createDbFromCloudRows(seedBundle.tables, createDefaultDb()));
        assert.equal(restoredDb.users.length, 2);
        assert.equal(restoredDb.families.length, 2);
        assert.equal(Object.values(restoredDb.cameras).length, 1);
        assert.equal(restoredDb.events.length, 1);
        assert.equal(restoredDb.events[0].summary, "疑似跌倒");
        assert.equal(String(restoredDb.events[0].camera_id), String(camera.id));
        assert.equal(restoredDb.assets.length, 1);
        assert.equal(restoredDb.device_tokens[0].token_hash.length, 64);
        assert.equal(restoredDb.care_preferences[String(family.id)].image_model, "wan2.7");
        assert.equal(restoredDb.care_cards.length, 1);
        assert.equal(restoredDb.care_cards[0].card_id, careCard.card_id);
        assert.equal(restoredDb.model_providers.length, 0);

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
