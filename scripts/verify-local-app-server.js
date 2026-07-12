#!/usr/bin/env node
"use strict";

const assert = require("assert");
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");

process.env.GOHOME_CARE_MODEL_CALLS = "0";
process.env.GOHOME_CARE_IMAGE_CALLS = "0";
process.env.GOHOME_WEATHER_PROVIDER = "none";
process.env.GOHOME_SEARCH_PROVIDER = "none";
process.env.GOHOME_VISION_VERIFICATION_ENABLED = "0";

const { createDefaultDb, createLocalAppServer, normalizeDb } = require("../local-app-server/server");
const { createDbFromCloudRows, TABLE_ORDER } = require("../local-app-server/postgres-store");
const { buildCloudSeedBundle, sha256 } = require("./export-local-app-db");

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
    const migrationsDir = path.resolve(__dirname, "../local-app-server/migrations");
    const schemaSql = fs.readdirSync(migrationsDir)
        .filter((file) => file.endsWith(".sql"))
        .sort()
        .map((file) => fs.readFileSync(path.join(migrationsDir, file), "utf8"))
        .join("\n\n");
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

function assertHtmlUsesLocalTailwind() {
    const rootDir = path.resolve(__dirname, "..");
    const htmlFiles = fs.readdirSync(rootDir).filter((file) => file.endsWith(".html"));
    assert.ok(htmlFiles.length > 0, "missing html files");
    for (const file of htmlFiles) {
        const html = fs.readFileSync(path.join(rootDir, file), "utf8");
        assert.ok(!html.includes("cdn.tailwindcss.com"), `${file} still depends on Tailwind CDN`);
        assert.ok(!html.includes("tailwind.config"), `${file} still includes runtime Tailwind config`);
    }
}

async function main() {
    const defaultDb = createDefaultDb();
    for (const key of [
        "offline_enabled",
        "black_screen_enabled",
        "no_motion_enabled",
        "person_detection_enabled",
        "fall_detection_enabled",
        "activity_detection_enabled",
        "fire_detection_enabled",
        "notification_enabled",
    ]) {
        assert.equal(defaultDb.rules[key], true, `${key} must be enabled by default`);
        assert.equal(defaultDb.family_rules["1"][key], true, `${key} family default must be enabled`);
    }
    const isolatedRestartDb = normalizeDb({
        ...createDefaultDb(),
        active_user_id: 2,
        users: [
            ...createDefaultDb().users,
            { id: 2, email: "new-user@gohome.local", display_name: "新用户", created_at: new Date().toISOString() },
        ],
    });
    assert.equal(isolatedRestartDb.family_members.some((member) => Number(member.user_id) === 2), false);

    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "gohome-app-server-"));
    const app = createLocalAppServer({
        rootDir: path.resolve(__dirname, ".."),
        dataDir: tempDir,
        deviceToken: DEVICE_TOKEN,
        appToken: APP_TOKEN,
    });
    const baseUrl = await listen(app.server);

    try {
        assertHtmlUsesLocalTailwind();

        const health = await requestJson(baseUrl, "/health");
        assert.equal(health.ok, true);

        const unknownLogin = await fetch(`${baseUrl}/api/auth/login`, {
            method: "POST",
            body: JSON.stringify({ email: "unknown@gohome.local", password: "secret123" }),
            headers: { "Content-Type": "application/json" },
        });
        assert.equal(unknownLogin.status, 401);

        const login = await requestJson(baseUrl, "/api/auth/login", {
            method: "POST",
            body: JSON.stringify({ email: "admin@gohome.local", password: "gohome" }),
        });
        assert.match(login.token, /^app_/);
        assert.equal(login.user.email, "admin@gohome.local");
        const adminSessionToken = login.token;
        const adminFamilies = await requestJson(baseUrl, "/api/families/mine", {
            headers: { Authorization: `Bearer ${adminSessionToken}` },
        });
        assert.equal(adminFamilies.length, 1);
        assert.equal(adminFamilies[0].name, "默认家庭");

        const registered = await requestJson(baseUrl, "/api/auth/register", {
            method: "POST",
            body: JSON.stringify({ email: "daughter@gohome.local", password: "secret123", display_name: "女儿" }),
        });
        assert.equal(registered.user.email, "daughter@gohome.local");
        assert.match(registered.token, /^app_/);
        const appSessionToken = registered.token;

        const duplicateRegister = await fetch(`${baseUrl}/api/auth/register`, {
            method: "POST",
            body: JSON.stringify({ email: "daughter@gohome.local", password: "secret123", display_name: "女儿" }),
            headers: { "Content-Type": "application/json" },
        });
        assert.equal(duplicateRegister.status, 409);

        const phoneAccountEmail = "13900000000@phone.gohome.local";
        const phoneRegistered = await requestJson(baseUrl, "/api/auth/register", {
            method: "POST",
            body: JSON.stringify({ phone: "13900000000", code: "000000", display_name: "家属" }),
        });
        assert.equal(phoneRegistered.user.email, phoneAccountEmail);
        assert.equal(phoneRegistered.user.phone, "13900000000");
        assert.match(phoneRegistered.token, /^app_/);

        const phoneFamilies = await requestJson(baseUrl, "/api/families/mine", {
            headers: { Authorization: `Bearer ${phoneRegistered.token}` },
        });
        assert.equal(phoneFamilies.length, 0);

        const phoneWrongCode = await fetch(`${baseUrl}/api/auth/login`, {
            method: "POST",
            body: JSON.stringify({ phone: "13900000000", code: "123456" }),
            headers: { "Content-Type": "application/json" },
        });
        assert.equal(phoneWrongCode.status, 401);

        const phoneLogin = await requestJson(baseUrl, "/api/auth/login", {
            method: "POST",
            body: JSON.stringify({ phone: "13900000000", code: "000000" }),
        });
        assert.match(phoneLogin.token, /^app_/);

        const emptyNewUserFamilies = await requestJson(baseUrl, "/api/families/mine", {
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(emptyNewUserFamilies.length, 0);

        const family = await requestJson(baseUrl, "/api/families", {
            method: "POST",
            body: JSON.stringify({ name: "测试家庭" }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(family.name, "测试家庭");
        assert.match(family.join_code, /^GH-\d+-[A-F0-9]{6}$/);

        const invalidJoin = await fetch(`${baseUrl}/api/families/join`, {
            method: "POST",
            body: JSON.stringify({ code: "GH-0-BAD000" }),
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${phoneRegistered.token}`,
            },
        });
        assert.equal(invalidJoin.status, 404);

        const joinedFamily = await requestJson(baseUrl, "/api/families/join", {
            method: "POST",
            body: JSON.stringify({ code: family.join_code }),
            headers: { Authorization: `Bearer ${phoneRegistered.token}` },
        });
        assert.equal(String(joinedFamily.id), String(family.id));
        assert.equal(joinedFamily.member_count, 2);

        const phoneFamiliesAfterJoin = await requestJson(baseUrl, "/api/families/mine", {
            headers: { Authorization: `Bearer ${phoneRegistered.token}` },
        });
        assert.equal(phoneFamiliesAfterJoin.length, 1);
        assert.equal(String(phoneFamiliesAfterJoin[0].id), String(family.id));

        const ownerRules = await requestJson(baseUrl, `/api/rules?family_id=${family.id}`, {
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(ownerRules.can_edit, true);
        assert.equal(ownerRules.fall_detection_enabled, true);
        const memberRules = await requestJson(baseUrl, `/api/rules?family_id=${family.id}`, {
            headers: { Authorization: `Bearer ${phoneRegistered.token}` },
        });
        assert.equal(memberRules.can_edit, false);

        const initialPresence = await requestJson(baseUrl, `/api/v1/families/${family.id}/presence-state`, {
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(initialPresence.can_edit, true);
        assert.equal(initialPresence.monitoring.mode, "active");

        const pausedPresence = await requestJson(baseUrl, `/api/v1/families/${family.id}/presence-monitoring`, {
            method: "PUT",
            body: JSON.stringify({ mode: "travel", reason: "测试旅行模式" }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(pausedPresence.status, "paused");
        assert.equal(pausedPresence.monitoring.mode, "travel");

        const memberPresenceUpdate = await fetch(`${baseUrl}/api/v1/families/${family.id}/presence-monitoring`, {
            method: "PUT",
            body: JSON.stringify({ mode: "active" }),
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${phoneRegistered.token}`,
            },
        });
        assert.equal(memberPresenceUpdate.status, 403);

        const resumedPresence = await requestJson(baseUrl, `/api/v1/families/${family.id}/presence-monitoring`, {
            method: "PUT",
            body: JSON.stringify({ mode: "active" }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(resumedPresence.monitoring.mode, "active");
        assert.equal(resumedPresence.monitoring.paused_until, "");
        const joinedMembership = app.store.db.family_members.find((member) => (
            String(member.family_id) === String(family.id)
            && String(member.user_id) === String(phoneRegistered.user.id)
        ));
        joinedMembership.role = "owner";
        const memberRulesUpdate = await fetch(`${baseUrl}/api/rules?family_id=${family.id}`, {
            method: "PUT",
            body: JSON.stringify({ fall_detection_enabled: false }),
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${phoneRegistered.token}`,
            },
        });
        assert.equal(memberRulesUpdate.status, 403);

        const claimFamily = await requestJson(baseUrl, "/api/families", {
            method: "POST",
            body: JSON.stringify({ name: "认领测试家庭" }),
            headers: { Authorization: `Bearer ${phoneRegistered.token}` },
        });
        const claimHeartbeat = await requestJson(baseUrl, "/api/v1/device/heartbeat", {
            method: "POST",
            body: JSON.stringify({
                device_id: "edge-claimable",
                name: "待认领盒子",
                status: "online",
                metadata: { serial_number: "GH-CLAIM001" },
            }),
            headers: { Authorization: `Bearer ${DEVICE_TOKEN}` },
        });
        assert.equal(claimHeartbeat.ok, true);
        const claimableDevices = await requestJson(baseUrl, "/api/device-claims/available", {
            headers: { Authorization: `Bearer ${phoneRegistered.token}` },
        });
        assert.ok(claimableDevices.some((item) => item.device_id === "edge-claimable" && item.serial_number === "GH-CLAIM001"));
        const unclaimedConfig = await requestJson(baseUrl, "/api/v1/device/config", {
            headers: { Authorization: `Bearer ${DEVICE_TOKEN}` },
        });
        assert.equal(unclaimedConfig.cameras.length, 0);
        const noCodeBinding = await fetch(`${baseUrl}/api/device-bindings`, {
            method: "POST",
            body: JSON.stringify({ family_id: claimFamily.id }),
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${phoneRegistered.token}`,
            },
        });
        assert.equal(noCodeBinding.status, 400);
        const claimedDevice = await requestJson(baseUrl, "/api/device-claims/claim", {
            method: "POST",
            body: JSON.stringify({ family_id: claimFamily.id, claim_code: "GH-CLAIM001" }),
            headers: { Authorization: `Bearer ${phoneRegistered.token}` },
        });
        assert.equal(claimedDevice.ok, true);
        assert.equal(claimedDevice.binding.device_id, "edge-claimable");
        const claimFamilyBindings = await requestJson(baseUrl, `/api/device-bindings?family_id=${claimFamily.id}`, {
            headers: { Authorization: `Bearer ${phoneRegistered.token}` },
        });
        assert.equal(claimFamilyBindings.length, 1);
        assert.equal(claimFamilyBindings[0].device_id, "edge-claimable");

        const claimFamilyCamera = await requestJson(baseUrl, "/api/cameras", {
            method: "POST",
            body: JSON.stringify({
                family_id: claimFamily.id,
                name: "厨房次视",
                room: "厨房",
                stream_url: "rtsp://192.168.1.21:554/stream2",
                enabled: true,
            }),
            headers: { Authorization: `Bearer ${phoneRegistered.token}` },
        });
        assert.equal(String(claimFamilyCamera.family_id), String(claimFamily.id));
        assert.equal(claimFamilyCamera.room, "厨房");

        await requestJson(baseUrl, "/api/v1/device/heartbeat", {
            method: "POST",
            body: JSON.stringify({
                device_id: "edge-transferable",
                name: "可移交盒子",
                status: "online",
                metadata: { serial_number: "GH-TRANSFER1" },
            }),
            headers: { Authorization: `Bearer ${DEVICE_TOKEN}` },
        });
        const transferableClaim = await requestJson(baseUrl, "/api/device-claims/claim", {
            method: "POST",
            body: JSON.stringify({ family_id: claimFamily.id, claim_code: "GH-TRANSFER1" }),
            headers: { Authorization: `Bearer ${phoneRegistered.token}` },
        });
        const transferableCamera = await requestJson(baseUrl, "/api/cameras", {
            method: "POST",
            body: JSON.stringify({
                family_id: claimFamily.id,
                device_id: "edge-transferable",
                name: "移交测试摄像头",
                room: "客厅",
                stream_url: "rtsp://192.168.1.30:554/stream1",
                enabled: true,
            }),
            headers: { Authorization: `Bearer ${phoneRegistered.token}` },
        });
        assert.equal(transferableCamera.device_id, "edge-transferable");
        const unboundTransferable = await requestJson(baseUrl, `/api/device-bindings/${transferableClaim.binding.id}`, {
            method: "DELETE",
            headers: { Authorization: `Bearer ${phoneRegistered.token}` },
        });
        assert.equal(unboundTransferable.ok, true);
        assert.equal(unboundTransferable.binding.status, "revoked");
        assert.equal(unboundTransferable.removed_camera_count, 1);

        await requestJson(baseUrl, "/api/v1/device/heartbeat", {
            method: "POST",
            body: JSON.stringify({
                device_id: "edge-transferable",
                family_id: claimFamily.id,
                status: "online",
            }),
            headers: { Authorization: `Bearer ${DEVICE_TOKEN}` },
        });
        const claimableAfterUnbind = await requestJson(baseUrl, "/api/device-claims/available", {
            headers: { Authorization: `Bearer ${phoneRegistered.token}` },
        });
        assert.ok(claimableAfterUnbind.some((item) => item.device_id === "edge-transferable"));
        const oldFamilyBindingsAfterUnbind = await requestJson(baseUrl, `/api/device-bindings?family_id=${claimFamily.id}`, {
            headers: { Authorization: `Bearer ${phoneRegistered.token}` },
        });
        assert.equal(oldFamilyBindingsAfterUnbind.some((item) => (
            item.device_id === "edge-transferable" && item.status !== "revoked"
        )), false);

        const transferFamily = await requestJson(baseUrl, "/api/families", {
            method: "POST",
            body: JSON.stringify({ name: "设备移交家庭" }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        const transferredDevice = await requestJson(baseUrl, "/api/device-claims/claim", {
            method: "POST",
            body: JSON.stringify({ family_id: transferFamily.id, claim_code: "GH-TRANSFER1" }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(String(transferredDevice.binding.family_id), String(transferFamily.id));
        assert.equal(transferredDevice.binding.device_id, "edge-transferable");

        const blockedClaimFamilyCamera = await fetch(`${baseUrl}/api/cameras`, {
            method: "POST",
            body: JSON.stringify({
                family_id: claimFamily.id,
                name: "越权摄像头",
                room: "书房",
                stream_url: "rtsp://192.168.1.22:554/stream1",
                enabled: true,
            }),
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${appSessionToken}`,
            },
        });
        assert.equal(blockedClaimFamilyCamera.status, 403);

        const adminBlockedFromDaughterFamily = await fetch(`${baseUrl}/api/v1/families/${family.id}/elders/elder_primary/profile`, {
            headers: { Authorization: `Bearer ${adminSessionToken}` },
        });
        assert.equal(adminBlockedFromDaughterFamily.status, 403);

        const elderProfile = await requestJson(baseUrl, `/api/v1/families/${family.id}/elders/elder_primary/profile`, {
            method: "PUT",
            body: JSON.stringify({
                display_name: "张阿姨",
                relationship: "母亲",
                city: "杭州",
                mobile_phone: "13800138000",
                home_phone: "057100000000",
            }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(elderProfile.display_name, "张阿姨");

        const bindingCode = await requestJson(baseUrl, "/api/device/binding-codes", {
            method: "POST",
            body: JSON.stringify({ family_id: family.id, expires_in_minutes: 10 }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(bindingCode.status, "active");
        assert.match(bindingCode.code, /^[a-f0-9]{16}$/);

        const exchanged = await requestJson(baseUrl, "/api/device/token/exchange", {
            method: "POST",
            body: JSON.stringify({ code: bindingCode.code, device_id: "edge-test", device_name: "测试盒子" }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(exchanged.ok, true);
        assert.ok(exchanged.device_token);

        const reusedBindingCode = await fetch(`${baseUrl}/api/device/token/exchange`, {
            method: "POST",
            body: JSON.stringify({ code: bindingCode.code, device_id: "edge-test" }),
            headers: { "Content-Type": "application/json" },
        });
        assert.equal(reusedBindingCode.status, 400);

        const conflictingCode = await requestJson(baseUrl, "/api/device/binding-codes", {
            method: "POST",
            body: JSON.stringify({ family_id: transferFamily.id, expires_in_minutes: 10 }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        const conflictingExchange = await fetch(`${baseUrl}/api/device/token/exchange`, {
            method: "POST",
            body: JSON.stringify({ code: conflictingCode.code, device_id: "edge-test" }),
            headers: { "Content-Type": "application/json" },
        });
        assert.equal(conflictingExchange.status, 409);

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
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(camera.room, "客厅");
        assert.equal(camera.connection_owner, "edge_agent");
        assert.equal(camera.stream_url, undefined);
        assert.equal(camera.status, "pending_edge_sync");

        const patchedCamera = await requestJson(baseUrl, `/api/cameras/${camera.id}`, {
            method: "PATCH",
            body: JSON.stringify({ enabled: false }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(patchedCamera.enabled, false);

        const testedCamera = await requestJson(baseUrl, `/api/cameras/${camera.id}/test`, {
            method: "POST",
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(testedCamera.ok, true);
        assert.equal(testedCamera.camera.status, "pending_edge_verify");

        const enabledCamera = await requestJson(baseUrl, `/api/cameras/${camera.id}`, {
            method: "PATCH",
            body: JSON.stringify({ enabled: true }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
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
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        const syncedCamera = appCameras.find((item) => String(item.id) === String(camera.id));
        assert.equal(syncedCamera.status, "online");
        assert.equal(syncedCamera.sync_status, "synced");
        assert.ok(syncedCamera.last_seen_at);

        const validationMedia = await requestJson(
            baseUrl,
            `/api/v1/device/media-assets/upload?camera_id=${camera.id}&local_camera_id=11&edge_event_id=validation-1&purpose=validation_evidence&snapshot_path=validation.jpg&content_type=image/jpeg`,
            {
                method: "POST",
                body: Buffer.from("validation-frame"),
                headers: { Authorization: `Bearer ${exchanged.device_token}`, "Content-Type": "image/jpeg" },
            },
        );
        assert.equal(validationMedia.asset.purpose, "validation_evidence");
        await requestJson(baseUrl, "/api/v1/device/events", {
            method: "POST",
            body: JSON.stringify({
                idempotency_key: "event:validation-1",
                edge_event_id: "validation-1",
                event_type: "fall_candidate",
                summary: "公开数据集验证",
                level: "critical",
                room: "客厅",
                camera_id: camera.id,
                snapshot_path: "validation.jpg",
                payload: { validation: { test_event: true, mode: "public_dataset_replay" } },
            }),
            headers: { Authorization: `Bearer ${exchanged.device_token}` },
        });
        const snapshotWithoutLivePreview = await requestJson(baseUrl, `/api/app/cameras/${camera.id}/snapshot/latest`, {
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(snapshotWithoutLivePreview.available, false, "validation evidence must never become camera preview");
        const visibleEventsAfterValidation = await requestJson(baseUrl, "/api/app/events?limit=20", {
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(visibleEventsAfterValidation.some((item) => item.payload?.validation?.test_event), false);

        await requestJson(
            baseUrl,
            `/api/v1/device/media-assets/upload?camera_id=${camera.id}&local_camera_id=11&purpose=live_preview&snapshot_path=live-preview.jpg&content_type=image/jpeg`,
            {
                method: "POST",
                body: Buffer.from("live-preview-frame"),
                headers: { Authorization: `Bearer ${exchanged.device_token}`, "Content-Type": "image/jpeg" },
            },
        );
        const snapshotWithLivePreview = await requestJson(baseUrl, `/api/app/cameras/${camera.id}/snapshot/latest`, {
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(snapshotWithLivePreview.available, true);
        assert.equal(snapshotWithLivePreview.snapshot_path, "live-preview.jpg");

        const staleOffline = await requestJson(baseUrl, "/api/v1/device/events", {
            method: "POST",
            body: JSON.stringify({
                idempotency_key: "event:stale-offline",
                event_type: "camera_offline",
                summary: "客厅主视曾短暂离线",
                level: "critical",
                room: "客厅",
                camera_id: camera.id,
                occurred_at: "2026-07-05T09:00:00.000Z",
                payload: {
                    error: "network stream opened but no frame was returned",
                    rule: { id: "camera_offline", label: "摄像头离线提醒" },
                },
            }),
            headers: { Authorization: `Bearer ${exchanged.device_token}` },
        });
        assert.equal(staleOffline.event.event_type, "camera_offline");

        const hiddenStaleEvents = await requestJson(baseUrl, "/api/app/events?limit=5&acknowledged=false", {
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(hiddenStaleEvents.some((item) => String(item.id) === String(staleOffline.event.id)), false);
        const summaryAfterStaleEvent = await requestJson(baseUrl, "/api/app/summary/today", {
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(summaryAfterStaleEvent.open_events, 0);
        assert.equal(summaryAfterStaleEvent.critical_events, 0);

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
            headers: { Authorization: `Bearer ${appSessionToken}` },
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
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        const deletedProbe = await requestJson(baseUrl, `/api/cameras/${deleteProbe.id}`, {
            method: "DELETE",
            headers: { Authorization: `Bearer ${appSessionToken}` },
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
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(camerasAfterDeleteSync.some((item) => String(item.id) === String(deleteProbe.id)), false);

        const imageBytes = Buffer.from("fake-jpeg-content");
        const media = await requestJson(
            baseUrl,
            `/api/v1/device/media-assets/upload?file_name=test.jpg&snapshot_path=events/test.jpg&content_type=image/jpeg&edge_event_id=42&camera_id=${camera.id}&local_camera_id=11&purpose=event_evidence`,
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
        assert.equal(String(media.asset.family_id), String(family.id));
        assert.equal(String(media.asset.device_id), String(camera.device_id));

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
        assert.equal(created.message.generated_by, "edge-event");
        assert.equal(created.message.source_event_ids[0], created.event.id);
        assert.equal(created.deliveries.length, 1);

        const originalVerificationEnv = {
            GOHOME_VISION_VERIFICATION_ENABLED: process.env.GOHOME_VISION_VERIFICATION_ENABLED,
            GOHOME_MULTIMODAL_BASE_URL: process.env.GOHOME_MULTIMODAL_BASE_URL,
            GOHOME_MULTIMODAL_API_KEY: process.env.GOHOME_MULTIMODAL_API_KEY,
            GOHOME_MULTIMODAL_MODEL: process.env.GOHOME_MULTIMODAL_MODEL,
        };
        let verificationRequestCount = 0;
        const mockVerificationServer = http.createServer(async (req, res) => {
            verificationRequestCount += 1;
            assert.equal(req.method, "POST");
            assert.equal(req.url, "/v1/chat/completions");
            assert.equal(req.headers.authorization, "Bearer mock-vision-key");
            const body = await new Promise((resolve) => {
                const chunks = [];
                req.on("data", (chunk) => chunks.push(chunk));
                req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
            });
            const requestPayload = JSON.parse(body);
            const userContent = requestPayload.messages[1].content;
            assert.equal(requestPayload.model, "mock-vision-model");
            assert.ok(Array.isArray(userContent));
            assert.match(userContent[0].text, /pose_factor_graph/);
            assert.match(userContent[1].image_url.url, /^data:image\/jpeg;base64,/);
            const parsed = verificationRequestCount === 1
                ? {
                    person_count: 1,
                    posture: "fallen",
                    surface: "floor",
                    emergency: true,
                    confidence: 0.93,
                    reason: "画面中一人位于地面低位。",
                    suggested_event_type: "fall_candidate",
                    unexpected: "strict contract must reject this field",
                }
                : {
                    person_count: 1,
                    posture: "fallen",
                    surface: "floor",
                    emergency: true,
                    confidence: 0.93,
                    reason: "画面中一人横卧在地面区域，支持边缘端跌倒候选。",
                    suggested_event_type: "fall_candidate",
                };
            res.writeHead(200, { "Content-Type": "application/json" });
            res.end(JSON.stringify({
                id: `mock-vision-${verificationRequestCount}`,
                model: "mock-vision-model",
                choices: [{ message: { content: JSON.stringify(parsed) } }],
                usage: { total_tokens: 80 },
            }));
        });
        const mockVerificationBaseUrl = await listen(mockVerificationServer);
        try {
            process.env.GOHOME_VISION_VERIFICATION_ENABLED = "1";
            process.env.GOHOME_MULTIMODAL_BASE_URL = `${mockVerificationBaseUrl}/v1/chat/completions`;
            process.env.GOHOME_MULTIMODAL_API_KEY = "mock-vision-key";
            process.env.GOHOME_MULTIMODAL_MODEL = "mock-vision-model";
            const verificationMedia = await requestJson(
                baseUrl,
                `/api/v1/device/media-assets/upload?file_name=verification.jpg&snapshot_path=events/verification.jpg&content_type=image/jpeg&edge_event_id=43&camera_id=${camera.id}&local_camera_id=11&purpose=event_evidence`,
                {
                    method: "POST",
                    body: Buffer.from("mock-verification-jpeg"),
                    headers: { Authorization: `Bearer ${DEVICE_TOKEN}`, "Content-Type": "image/jpeg" },
                },
            );
            const verificationEvent = await requestJson(baseUrl, "/api/v1/device/events", {
                method: "POST",
                body: JSON.stringify({
                    idempotency_key: "event:43",
                    edge_event_id: "43",
                    event_type: "fall_candidate",
                    summary: "视觉复核测试事件",
                    level: "critical",
                    room: "客厅",
                    camera_id: 11,
                    snapshot_path: "events/verification.jpg",
                    payload: {
                        rule: { reason: "边缘端检测到站立后快速下降。" },
                        evidence: {
                            metrics: { fall_score: 0.88 },
                            pose_factor_graph: { fast_fall_candidate: true, fast_fall_score: 0.91 },
                            temporal_evidence_bundle: { track_id: "c11-p1", posture_sequence: ["standing", "lying"] },
                        },
                        edge_upload: { edge_event_id: 43, edge_device_id: "edge-test" },
                    },
                }),
                headers: { Authorization: `Bearer ${DEVICE_TOKEN}` },
            });
            assert.equal(verificationEvent.event.media_asset_id, verificationMedia.asset.id);
            assert.equal(verificationEvent.verification.status, "pending");
            await new Promise((resolve) => setTimeout(resolve, 100));
            const retryingEvent = await requestJson(baseUrl, `/api/v1/events/${verificationEvent.event.id}`, {
                headers: { Authorization: `Bearer ${appSessionToken}` },
            });
            assert.equal(retryingEvent.payload.verification.status, "retrying");
            assert.match(retryingEvent.payload.verification.error, /strict JSON contract/);
            const retryRun = await requestJson(baseUrl, "/api/v1/internal/vision-verifications/run", {
                method: "POST",
                body: JSON.stringify({ force: true, limit: 1 }),
            });
            assert.equal(retryRun.succeeded, 1);
            const verifiedEvent = await requestJson(baseUrl, `/api/v1/events/${verificationEvent.event.id}`, {
                headers: { Authorization: `Bearer ${appSessionToken}` },
            });
            assert.equal(verifiedEvent.payload.verification.status, "confirmed");
            assert.equal(verifiedEvent.payload.verification.result.posture, "fallen");
            assert.equal(verifiedEvent.payload.verification.result.surface, "floor");
            assert.equal(verifiedEvent.payload.verification.attempt_count, 2);
            assert.equal(verifiedEvent.payload.incident.status, "confirmed");
            const verificationOutcomeMessage = app.store.db.app_messages.find((message) => (
                message.generated_by === "vision-verification-orchestrator"
                && String(message.event_id) === String(verificationEvent.event.id)
                && message.metadata?.verification_status === "confirmed"
            ));
            assert.ok(verificationOutcomeMessage);
            assert.ok(app.store.db.notification_deliveries.some((delivery) => (
                String(delivery.message_id) === String(verificationOutcomeMessage.message_id)
            )));
            const verificationJob = app.store.db.model_generation_jobs.find((job) => (
                job.purpose === "vision_event_verification"
                && String(job.metadata?.event_id) === String(verificationEvent.event.id)
            ));
            assert.ok(verificationJob);
            assert.equal(verificationJob.output_status, "succeeded");
            assert.equal(verificationJob.metadata.attempt_count, 2);
            assert.equal("api_key" in verificationJob.request_payload, false);
            const deviceVerificationStatus = await requestJson(baseUrl, "/api/v1/device/vision-verifications?limit=5", {
                headers: { Authorization: `Bearer ${DEVICE_TOKEN}` },
            });
            assert.equal(deviceVerificationStatus.ok, true);
            assert.equal(deviceVerificationStatus.configured, true);
            assert.ok(deviceVerificationStatus.records.some((record) => (
                String(record.event_id) === String(verificationEvent.event.id)
                && record.verification.status === "confirmed"
                && record.job.output_status === "succeeded"
                && record.verification.result.confidence === 0.93
            )));
            const deviceEventLog = await requestJson(baseUrl, "/api/v1/device/event-log?limit=20", {
                headers: { Authorization: `Bearer ${DEVICE_TOKEN}` },
            });
            assert.equal(deviceEventLog.ok, true);
            assert.ok(deviceEventLog.records.some((record) => (
                String(record.event_id) === String(verificationEvent.event.id)
                && String(record.edge_event_id) === "43"
                && record.incident.status === "confirmed"
                && record.verification.status === "confirmed"
            )));
        } finally {
            for (const [key, value] of Object.entries(originalVerificationEnv)) {
                if (value === undefined) delete process.env[key];
                else process.env[key] = value;
            }
            mockVerificationServer.close();
        }

        const secondCamera = await requestJson(baseUrl, "/api/cameras", {
            method: "POST",
            body: JSON.stringify({
                name: "走廊摄像头",
                room: "走廊",
                stream_url: "demo:hallway",
                enabled: true,
            }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        const correlatedEvent = await requestJson(baseUrl, "/api/v1/device/events", {
            method: "POST",
            body: JSON.stringify({
                idempotency_key: "event:42-hallway",
                edge_event_id: "42-hallway",
                event_type: "fall_candidate",
                summary: "走廊摄像头同时看到疑似跌倒",
                level: "critical",
                room: "走廊",
                camera_id: secondCamera.id,
                occurred_at: "2026-07-05T10:00:15.000Z",
                payload: {
                    rule: { reason: "相邻摄像头在同一时间窗口命中相同事故。" },
                    edge_upload: { edge_event_id: "42-hallway", edge_device_id: "edge-test" },
                },
            }),
            headers: { Authorization: `Bearer ${DEVICE_TOKEN}` },
        });
        assert.equal(correlatedEvent.message, null);
        assert.equal(correlatedEvent.deliveries.length, 0);
        assert.equal(correlatedEvent.event.payload.incident.incident_id, created.event.payload.incident.incident_id);
        assert.equal(String(correlatedEvent.event.payload.incident.primary_event_id), String(created.event.id));
        assert.equal(correlatedEvent.event.payload.incident.source_camera_ids.length, 2);
        await requestJson(baseUrl, `/api/cameras/${secondCamera.id}`, {
            method: "DELETE",
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });

        const originalAbsenceThreshold = process.env.GOHOME_LONG_ABSENCE_SECONDS;
        try {
            process.env.GOHOME_LONG_ABSENCE_SECONDS = "60";
            const cloudCamera = app.store.db.cameras[String(camera.id)];
            cloudCamera.status = "online";
            cloudCamera.sync_status = "synced";
            cloudCamera.edge_reported_at = new Date().toISOString();
            cloudCamera.presence = {
                reported_at: new Date().toISOString(),
                last_observed_at: new Date().toISOString(),
                last_person_seen_at: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
                observation_coverage: 1,
                observed_samples: 720,
                expected_samples: 720,
            };
            created.event.payload.incident.started_at = new Date(Date.now() - 2 * 60 * 1000).toISOString();
            const verifiedSafetyEvent = app.store.db.events.find((event) => event.summary === "视觉复核测试事件");
            verifiedSafetyEvent.payload.incident.started_at = new Date(Date.now() - 2 * 60 * 1000).toISOString();
            const absenceRun = await requestJson(baseUrl, "/api/v1/internal/scheduler/run", {
                method: "POST",
                body: JSON.stringify({ family_id: family.id, force: true }),
            });
            assert.equal(absenceRun.result.long_absence_events_created, 1);
            assert.ok(
                absenceRun.result.incident_reminders_created >= 2,
                JSON.stringify(app.store.db.events.map((event) => ({
                    summary: event.summary,
                    status: event.payload?.incident?.status,
                    primary_event_id: event.payload?.incident?.primary_event_id,
                    acknowledged: event.acknowledged,
                }))),
            );
            const longAbsenceEvent = app.store.db.events.find((event) => event.event_type === "long_absence");
            assert.ok(longAbsenceEvent);
            assert.equal(longAbsenceEvent.payload.incident.status, "confirmed");
            const sameMinuteRun = await requestJson(baseUrl, "/api/v1/internal/scheduler/run", {
                method: "POST",
                body: JSON.stringify({ family_id: family.id, force: true }),
            });
            assert.equal(sameMinuteRun.result.incident_reminders_created, 0);
            cloudCamera.presence.last_person_seen_at = new Date().toISOString();
            cloudCamera.presence.reported_at = new Date().toISOString();
            await requestJson(baseUrl, "/api/v1/internal/scheduler/run", {
                method: "POST",
                body: JSON.stringify({ family_id: family.id, force: true }),
            });
            assert.equal(longAbsenceEvent.acknowledged, true);
            assert.equal(longAbsenceEvent.resolution, "person_seen_again");
            assert.equal(longAbsenceEvent.payload.incident.status, "resolved");
            await requestJson(baseUrl, `/api/v1/families/${family.id}/care-preferences`, {
                method: "PUT",
                body: JSON.stringify({ metadata: { presence_monitoring: { mode: "travel", reason: "短期外出" } } }),
                headers: { Authorization: `Bearer ${appSessionToken}` },
            });
            cloudCamera.presence.last_person_seen_at = new Date(Date.now() - 2 * 60 * 1000).toISOString();
            await requestJson(baseUrl, "/api/v1/internal/scheduler/run", {
                method: "POST",
                body: JSON.stringify({ family_id: family.id, force: true }),
            });
            const storedFamily = app.store.db.families.find((item) => String(item.id) === String(family.id));
            assert.equal(storedFamily.presence_state.status, "paused");
            assert.equal(app.store.db.events.filter((event) => event.event_type === "long_absence").length, 1);
            await requestJson(baseUrl, `/api/v1/families/${family.id}/care-preferences`, {
                method: "PUT",
                body: JSON.stringify({ metadata: { presence_monitoring: { mode: "active" } } }),
                headers: { Authorization: `Bearer ${appSessionToken}` },
            });
        } finally {
            if (originalAbsenceThreshold === undefined) delete process.env.GOHOME_LONG_ABSENCE_SECONDS;
            else process.env.GOHOME_LONG_ABSENCE_SECONDS = originalAbsenceThreshold;
        }

        const eventMessages = await requestJson(baseUrl, `/api/v1/app/messages?family_id=${family.id}&status=all`, {
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.ok(eventMessages.some((message) => (
            message.generated_by === "edge-event"
            && message.source_event_ids.some((eventId) => String(eventId) === String(created.event.id))
        )));

        const events = await requestJson(baseUrl, "/api/app/events?limit=5&acknowledged=false", {
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(events.length, 2);
        assert.ok(events.every((event) => event.type === "fall_candidate"));

        const blockedDefaultFamilyBindings = await fetch(`${baseUrl}/api/device-bindings?family_id=1`, {
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(blockedDefaultFamilyBindings.status, 403);

        const newFamilyBindings = await requestJson(baseUrl, `/api/device-bindings?family_id=${family.id}`, {
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(newFamilyBindings.length, 1);
        assert.equal(newFamilyBindings[0].device_id, "edge-test");

        const snapshot = await requestJson(baseUrl, `/api/app/cameras/${camera.id}/snapshot/latest?allow_missing=1`, {
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(snapshot.available, true);
        assert.equal(snapshot.snapshot_path, "live-preview.jpg");

        const evaluation = await requestJson(baseUrl, `/api/app/cameras/${camera.id}/evaluation/latest`, {
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(evaluation.candidates.length, 1);
        assert.equal(evaluation.state.latest_event_type, "fall_candidate");

        const detail = await requestJson(baseUrl, `/api/app/events/${created.event.id}`, {
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(detail.payload.rule.observed.confirm_frames, 2);

        const patched = await requestJson(baseUrl, `/api/app/events/${created.event.id}`, {
            method: "PATCH",
            body: JSON.stringify({ acknowledged: true, resolution: "handled" }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(patched.acknowledged, true);
        assert.equal(patched.resolution, "handled");
        assert.equal(patched.payload.incident.status, "acknowledged");
        const linkedCorrelatedEvent = app.store.db.events.find((event) => String(event.id) === String(correlatedEvent.event.id));
        assert.equal(linkedCorrelatedEvent.acknowledged, true);
        assert.equal(linkedCorrelatedEvent.payload.incident.status, "acknowledged");
        assert.ok(app.store.db.app_messages
            .filter((message) => (message.source_event_ids || []).some((eventId) => String(eventId) === String(created.event.id)))
            .every((message) => message.status === "archived"));

        const carePreferences = await requestJson(baseUrl, `/api/v1/families/${family.id}/care-preferences`, {
            headers: { Authorization: `Bearer ${appSessionToken}` },
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
                image_model: "wan2.7-image",
                content_recommendations_enabled: false,
                metadata: {
                    care_card_schedule: {
                        enabled: true,
                        delivery_time: "07:45",
                        timezone: "Asia/Shanghai",
                        channels: ["app_push"],
                        content_types: {
                            home_status: true,
                            elder_interest_topics: true,
                            health_tips: true,
                            weather: true,
                            holidays: true,
                            anniversaries: true,
                            visit_reminder: true,
                        },
                        interest_topics: ["养生", "越剧", "杭州本地"],
                        message_focus: "先说明家里是否平稳，再给女儿一个适合打电话时聊的轻松话题。",
                        visit_reminder: {
                            enabled: true,
                            threshold_days: 10,
                            location_tracking_enabled: true,
                            last_visit_at: "2026-06-20",
                        },
                        anniversaries: [
                            { label: "妈妈生日", date: "2026-09-01", repeat: "yearly" },
                        ],
                    },
                },
            }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(updatedCarePreferences.image_generation_enabled, true);
        assert.equal(updatedCarePreferences.image_model, "wan2.7-image");
        const savedSchedule = updatedCarePreferences.metadata.care_card_schedule;
        assert.equal(savedSchedule.delivery_time, "07:45");
        assert.equal(savedSchedule.content_types.health_tips, true);
        assert.deepEqual(savedSchedule.interest_topics, ["养生", "越剧", "杭州本地"]);
        assert.equal(savedSchedule.message_focus, "先说明家里是否平稳，再给女儿一个适合打电话时聊的轻松话题。");
        assert.equal(savedSchedule.visit_reminder.threshold_days, 10);
        assert.equal(savedSchedule.visit_reminder.location_tracking_enabled, true);
        assert.equal(savedSchedule.visit_reminder.last_visit_at, "2026-06-20");
        assert.equal(savedSchedule.anniversaries[0].label, "妈妈生日");

        const careCard = await requestJson(baseUrl, `/api/v1/app/care-cards/today?family_id=${family.id}`, {
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(careCard.card_type, "daily");
        assert.ok(careCard.facts.length >= 3);
        assert.equal(careCard.image_mode, "pending_provider");
        assert.ok(careCard.actions.some((action) => action.key === "call"));

        const generatedCareCard = await requestJson(baseUrl, "/api/v1/internal/care-cards/generate", {
            method: "POST",
            body: JSON.stringify({ family_id: family.id, force: true }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(generatedCareCard.ok, true);
        assert.equal(generatedCareCard.card.card_id, careCard.card_id);

        const pushToken = await requestJson(baseUrl, "/api/v1/app/push-tokens", {
            method: "POST",
            body: JSON.stringify({
                family_id: family.id,
                app_install_id: "verify-ios-install",
                platform: "ios",
                push_token: "verify-push-token-1234567890",
                device_name: "iPhone Verify",
                app_version: "0.1.0",
            }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(pushToken.family_id, family.id);
        assert.equal(pushToken.platform, "ios");
        assert.equal(pushToken.token_preview, "veri...7890");

        const schedulerRun = await requestJson(baseUrl, "/api/v1/internal/scheduler/run", {
            method: "POST",
            body: JSON.stringify({ family_id: family.id, force: true }),
        });
        assert.equal(schedulerRun.ok, true);
        assert.equal(schedulerRun.run.status, "succeeded");
        assert.equal(schedulerRun.result.families_checked, 1);
        assert.ok(schedulerRun.result.care_cards_generated >= 1);
        assert.ok(schedulerRun.result.notification_deliveries_created >= 1);

        const appMessages = await requestJson(baseUrl, `/api/v1/app/messages?family_id=${family.id}&status=open`, {
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        const careMessage = appMessages.find((message) => message.message_type === "care_card");
        assert.ok(careMessage);
        assert.equal(careMessage.care_card_id, generatedCareCard.card.card_id);
        assert.ok(careMessage.actions.some((action) => action.key === "open_care_card"));

        const readMessage = await requestJson(baseUrl, `/api/v1/app/messages/${encodeURIComponent(careMessage.message_id)}?family_id=${family.id}`, {
            method: "PATCH",
            body: JSON.stringify({ status: "read" }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(readMessage.status, "read");
        assert.ok(readMessage.read_at);

        const deliveries = await requestJson(baseUrl, `/api/v1/notifications/deliveries?family_id=${family.id}`, {
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.ok(deliveries.some((delivery) => (
            delivery.message_id === careMessage.message_id
            && ["queued", "simulated", "app_message_only"].includes(delivery.status)
        )));

        const pushTest = await requestJson(baseUrl, "/api/v1/app/push-test", {
            method: "POST",
            body: JSON.stringify({ family_id: family.id }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(pushTest.ok, true);
        assert.ok(pushTest.deliveries.length >= 1);

        const schedulerStatus = await requestJson(baseUrl, "/api/v1/internal/scheduler/status");
        assert.equal(schedulerStatus.ok, true);
        assert.ok(schedulerStatus.latest_runs.length >= 1);

        const opsConfig = await requestJson(baseUrl, "/api/v1/ops/service-config", {
            headers: {},
        });
        assert.equal(opsConfig.ok, true);
        assert.equal(opsConfig.secret_policy.user_configurable, false);
        assert.equal(opsConfig.secret_policy.database, "no_plain_secret");
        assert.ok(Array.isArray(opsConfig.env_files));
        assert.ok(opsConfig.model_capabilities.some((capability) => capability.capability_id === "multimodal-language"));
        assert.ok(opsConfig.model_capabilities.some((capability) => capability.capability_id === "vision-event-verification"));
        assert.ok(opsConfig.model_capabilities.some((capability) => capability.capability_id === "care-card-image" && capability.aspect_ratio === "1:1"));
        for (const capability of opsConfig.model_capabilities) {
            assert.equal("base_url" in capability, false);
            assert.equal("api_key_preview" in capability, false);
        }

        const appTokenCannotWriteModelConfig = await fetch(`${baseUrl}/api/v1/model-providers/care-card-image`, {
            method: "PUT",
            body: JSON.stringify({ model: "wan2.7", api_key: "secret" }),
            headers: { Authorization: `Bearer ${appSessionToken}`, "Content-Type": "application/json" },
        });
        assert.equal(appTokenCannotWriteModelConfig.status, 405);

        const originalModelEnv = {
            GOHOME_CARE_MODEL_CALLS: process.env.GOHOME_CARE_MODEL_CALLS,
            GOHOME_CARE_IMAGE_CALLS: process.env.GOHOME_CARE_IMAGE_CALLS,
            GOHOME_MULTIMODAL_BASE_URL: process.env.GOHOME_MULTIMODAL_BASE_URL,
            GOHOME_MULTIMODAL_API_KEY: process.env.GOHOME_MULTIMODAL_API_KEY,
            GOHOME_MULTIMODAL_MODEL: process.env.GOHOME_MULTIMODAL_MODEL,
        };
        const mockModelServer = http.createServer(async (req, res) => {
            assert.equal(req.method, "POST");
            assert.equal(req.url, "/v1/chat/completions");
            assert.equal(req.headers.authorization, "Bearer mock-model-key");
            const body = await new Promise((resolve) => {
                const chunks = [];
                req.on("data", (chunk) => chunks.push(chunk));
                req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
            });
            const payload = JSON.parse(body);
            assert.equal(payload.model, "mock-care-model");
            assert.match(payload.messages[1].content, /care_card_schedule/);
            assert.match(payload.messages[1].content, /先说明家里是否平稳/);
            assert.match(payload.messages[1].content, /妈妈生日/);
            res.writeHead(200, { "Content-Type": "application/json" });
            res.end(JSON.stringify({
                id: "mock-chatcmpl",
                model: "mock-care-model",
                choices: [{
                    message: {
                        content: JSON.stringify({
                            title: "模型生成的今日关怀",
                            body: "家里状态整体平稳，适合用轻松的语气问候一下今天的天气和午休。",
                            facts: ["模型基于设备、摄像头和事件摘要生成。"],
                            suggested_actions: ["打电话问候", "看看实时状态", "查看今日提醒"],
                            tone: "warm",
                            image_brief: "温馨家庭关怀卡片",
                        }),
                    },
                }],
                usage: { total_tokens: 120 },
            }));
        });
        const mockModelBaseUrl = await listen(mockModelServer);
        try {
            process.env.GOHOME_CARE_MODEL_CALLS = "1";
            process.env.GOHOME_CARE_IMAGE_CALLS = "0";
            process.env.GOHOME_MULTIMODAL_BASE_URL = `${mockModelBaseUrl}/v1/chat/completions`;
            process.env.GOHOME_MULTIMODAL_API_KEY = "mock-model-key";
            process.env.GOHOME_MULTIMODAL_MODEL = "mock-care-model";
            const modelCareCard = await requestJson(baseUrl, "/api/v1/internal/care-cards/generate", {
                method: "POST",
                body: JSON.stringify({ family_id: family.id, force: true }),
                headers: { Authorization: `Bearer ${appSessionToken}` },
            });
            assert.equal(modelCareCard.ok, true);
            assert.equal(modelCareCard.card.title, "模型生成的今日关怀");
            assert.equal(modelCareCard.card.generated_by, "model:mock-care-model");
            assert.ok(app.store.db.model_generation_jobs.some((job) => (
                job.model === "mock-care-model" && job.output_status === "succeeded"
            )));
        } finally {
            for (const [key, value] of Object.entries(originalModelEnv)) {
                if (value === undefined) delete process.env[key];
                else process.env[key] = value;
            }
            mockModelServer.close();
        }

        const originalImageEnv = {
            GOHOME_CARE_MODEL_CALLS: process.env.GOHOME_CARE_MODEL_CALLS,
            GOHOME_CARE_IMAGE_CALLS: process.env.GOHOME_CARE_IMAGE_CALLS,
            GOHOME_IMAGE_BASE_URL: process.env.GOHOME_IMAGE_BASE_URL,
            GOHOME_IMAGE_API_KEY: process.env.GOHOME_IMAGE_API_KEY,
            GOHOME_IMAGE_MODEL: process.env.GOHOME_IMAGE_MODEL,
            GOHOME_IMAGE_REQUEST_MODE: process.env.GOHOME_IMAGE_REQUEST_MODE,
            GOHOME_CARE_IMAGE_POLL_INTERVAL_MS: process.env.GOHOME_CARE_IMAGE_POLL_INTERVAL_MS,
            GOHOME_CARE_IMAGE_MAX_POLLS: process.env.GOHOME_CARE_IMAGE_MAX_POLLS,
        };
        const mockImageBytes = Buffer.from("mock-png-content");
        const mockImageServer = http.createServer(async (req, res) => {
            if (req.method === "POST" && req.url === "/api/v1/services/aigc/multimodal-generation/generation") {
                assert.equal(req.headers.authorization, "Bearer mock-image-key");
                assert.equal(req.headers["x-dashscope-sse"], undefined);
                const body = await new Promise((resolve) => {
                    const chunks = [];
                    req.on("data", (chunk) => chunks.push(chunk));
                    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
                });
                const payload = JSON.parse(body);
                assert.equal(payload.model, "mock-wan-image");
                assert.equal(payload.parameters.size, "1024*1024");
                assert.equal(payload.parameters.n, 1);
                assert.equal(payload.parameters.thinking_mode, true);
                assert.equal(payload.parameters.stream, undefined);
                assert.equal(payload.parameters.enable_interleave, undefined);
                assert.match(payload.input.messages[0].content[0].text, /1:1/);
                assert.match(payload.input.messages[0].content[0].text, /卡片标题/);
                res.writeHead(200, { "Content-Type": "application/json" });
                res.end(JSON.stringify({
                    output: {
                        results: [
                            { url: `${mockImageBaseUrl}/images/card.png` },
                        ],
                    },
                    usage: { image_count: 1 },
                    request_id: "mock-image-request",
                }));
                return;
            }
            if (req.method === "GET" && req.url === "/images/card.png") {
                res.writeHead(200, { "Content-Type": "image/png" });
                res.end(mockImageBytes);
                return;
            }
            res.writeHead(404, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ detail: "not found" }));
        });
        const mockImageBaseUrl = await listen(mockImageServer);
        try {
            process.env.GOHOME_CARE_MODEL_CALLS = "0";
            process.env.GOHOME_CARE_IMAGE_CALLS = "1";
            process.env.GOHOME_IMAGE_BASE_URL = `${mockImageBaseUrl}/api/v1/services/aigc/multimodal-generation/generation`;
            process.env.GOHOME_IMAGE_API_KEY = "mock-image-key";
            process.env.GOHOME_IMAGE_MODEL = "mock-wan-image";
            delete process.env.GOHOME_IMAGE_REQUEST_MODE;
            process.env.GOHOME_CARE_IMAGE_POLL_INTERVAL_MS = "1";
            process.env.GOHOME_CARE_IMAGE_MAX_POLLS = "3";
            const imageCareCard = await requestJson(baseUrl, "/api/v1/internal/care-cards/generate", {
                method: "POST",
                body: JSON.stringify({ family_id: family.id, force: true }),
                headers: { Authorization: `Bearer ${appSessionToken}` },
            });
            assert.equal(imageCareCard.ok, true);
            assert.equal(imageCareCard.card.image_mode, "generated");
            assert.match(imageCareCard.card.image_url, /^care-cards\//);
            const imageJob = [...app.store.db.model_generation_jobs].reverse().find((job) => job.purpose === "care_card_image_generation");
            assert.ok(imageJob);
            assert.equal(imageJob.model, "mock-wan-image");
            assert.equal(imageJob.output_status, "succeeded");
            assert.equal(imageJob.response_payload.request_mode, "sync");
            const careImageAsset = [...app.store.db.assets].reverse().find((asset) => asset.snapshot_path === imageCareCard.card.image_url);
            assert.ok(careImageAsset);
            assert.equal(careImageAsset.content_type, "image/png");
            assert.equal(careImageAsset.size, mockImageBytes.length);
            const imageSession = await requestJson(baseUrl, "/api/v1/video/sessions", {
                method: "POST",
                body: JSON.stringify({ resource_type: "snapshot", snapshot_path: imageCareCard.card.image_url }),
                headers: { Authorization: `Bearer ${appSessionToken}` },
            });
            const careImageResponse = await fetch(`${baseUrl}/api/v1/video/media/snapshots/${encodeURIComponent(imageCareCard.card.image_url)}?playback_ticket=${imageSession.ticket}`);
            assert.equal(careImageResponse.status, 200);
            assert.equal(careImageResponse.headers.get("content-type"), "image/png");
            assert.equal(await careImageResponse.text(), "mock-png-content");
        } finally {
            for (const [key, value] of Object.entries(originalImageEnv)) {
                if (value === undefined) delete process.env[key];
                else process.env[key] = value;
            }
            mockImageServer.close();
        }

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
                headers: { Authorization: `Bearer ${appSessionToken}` },
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
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.ok(session.ticket);

        const mediaResponse = await fetch(`${baseUrl}/api/v1/video/media/snapshots/events/test.jpg?playback_ticket=${session.ticket}`);
        assert.equal(mediaResponse.status, 200);
        assert.equal(await mediaResponse.text(), "fake-jpeg-content");

        const streamSession = await requestJson(baseUrl, "/api/v1/video/sessions", {
            method: "POST",
            body: JSON.stringify({ resource_type: "stream", camera_id: camera.id }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        const streamResponse = await fetch(`${baseUrl}/api/v1/video/cameras/${camera.id}/stream.mjpg?playback_ticket=${streamSession.ticket}`);
        assert.equal(streamResponse.status, 200);
        assert.match(streamResponse.headers.get("content-type") || "", /multipart\/x-mixed-replace/);
        streamResponse.body.cancel();

        const customizedRules = await requestJson(baseUrl, `/api/rules?family_id=${family.id}`, {
            method: "PUT",
            body: JSON.stringify({ activity_detection_enabled: false }),
            headers: { Authorization: `Bearer ${appSessionToken}` },
        });
        assert.equal(customizedRules.activity_detection_enabled, false);

        const seedBundle = buildCloudSeedBundle(app.store.db, { source: "verify-local-app-server" });
        assert.equal(seedBundle.schema_version, "004_app_sessions");
        assert.equal(seedBundle.tables.users.length, 3);
        assert.ok(seedBundle.tables.users.some((user) => user.email === phoneAccountEmail));
        assert.ok(seedBundle.tables.app_sessions.length >= 3);
        assert.ok(seedBundle.tables.app_sessions.every((session) => session.token_hash.length === 64));
        assert.ok(seedBundle.tables.app_sessions.every((session) => !("token" in session)));
        assert.ok(seedBundle.tables.families.some((item) => String(item.id) === String(transferFamily.id)));
        assert.ok(seedBundle.tables.family_members.some((item) => (
            String(item.family_id) === String(transferFamily.id)
            && String(item.user_id) === String(registered.user.id)
            && item.role === "owner"
        )));
        assert.ok(seedBundle.tables.elder_profiles.some((item) => String(item.family_id) === String(transferFamily.id)));
        const seededElderProfile = seedBundle.tables.elder_profiles.find((profile) => String(profile.family_id) === String(family.id));
        assert.equal(seededElderProfile.mobile_phone, "13800138000");
        assert.equal(seededElderProfile.home_phone, "057100000000");
        assert.equal(seedBundle.tables.device_tokens.length, 1);
        assert.equal(seedBundle.tables.device_tokens[0].token_hash.length, 64);
        assert.equal(seedBundle.tables.cameras.length, 2);
        assert.ok(seedBundle.tables.cameras.some((item) => (
            String(item.id) === String(claimFamilyCamera.id)
            && String(item.family_id) === String(claimFamily.id)
        )));
        assert.equal(seedBundle.tables.camera_secrets.length, 2);
        assert.equal(seedBundle.tables.care_rules.length, seedBundle.tables.families.length);
        const seededFamilyRules = seedBundle.tables.care_rules.find((item) => String(item.family_id) === String(family.id));
        assert.ok(seededFamilyRules);
        assert.equal(seededFamilyRules.rule_type, "edge_rules");
        assert.equal(seededFamilyRules.config.activity_detection_enabled, false);
        assert.equal(seedBundle.tables.events.length, 5);
        const seededFallEvent = seedBundle.tables.events.find((event) => event.event_type === "fall_candidate");
        const seededStaleOfflineEvent = seedBundle.tables.events.find((event) => String(event.id) === String(staleOffline.event.id));
        assert.ok(seededFallEvent);
        assert.ok(seededStaleOfflineEvent);
        assert.equal(seededFallEvent.camera_id, String(camera.id));
        assert.equal(seedBundle.tables.media_assets.length, 3);
        const seededEventAsset = seedBundle.tables.media_assets.find((asset) => asset.snapshot_path === "events/test.jpg");
        assert.equal(seededEventAsset.metadata.purpose, "event_evidence");
        assert.equal(seedBundle.tables.care_preferences.length, 1);
        assert.equal(seedBundle.tables.care_preferences[0].image_model, "wan2.7-image");
        assert.equal(seedBundle.tables.care_preferences[0].metadata.care_card_schedule.delivery_time, "07:45");
        assert.equal(seedBundle.tables.care_preferences[0].metadata.care_card_schedule.visit_reminder.threshold_days, 10);
        assert.equal(seedBundle.tables.care_preferences[0].metadata.care_card_schedule.anniversaries[0].label, "妈妈生日");
        assert.equal(seedBundle.tables.care_cards.length, 1);
        assert.equal(seedBundle.tables.care_cards[0].card_id, careCard.card_id);
        assert.ok(seedBundle.tables.app_messages.some((message) => message.message_type === "care_card"));
        assert.ok(seedBundle.tables.app_messages.some((message) => message.message_type === "test"));
        assert.equal(seedBundle.tables.app_push_tokens.length, 1);
        assert.equal(seedBundle.tables.app_push_tokens[0].push_token_hash.length, 64);
        assert.ok(seedBundle.tables.notification_deliveries.length >= 2);
        assert.ok(seedBundle.tables.notification_deliveries.every((delivery) => (
            !delivery.message_id
            || seedBundle.tables.app_messages.some((message) => message.message_id === delivery.message_id)
        )));
        assert.ok(seedBundle.tables.scheduler_runs.some((run) => run.status === "succeeded"));
        assert.equal(seedBundle.tables.model_providers.length, 0);
        assertSeedBundleMatchesSchema(seedBundle);

        const restoredDb = normalizeDb(createDbFromCloudRows(seedBundle.tables, createDefaultDb()));
        assert.equal(restoredDb.users.length, 3);
        assert.ok(restoredDb.users.some((user) => user.email === phoneAccountEmail));
        assert.ok(restoredDb.app_sessions.some((session) => session.token_hash === sha256(appSessionToken)));
        assert.ok(restoredDb.families.some((item) => String(item.id) === String(transferFamily.id)));
        assert.ok(restoredDb.device_bindings.some((item) => (
            String(item.family_id) === String(transferFamily.id)
            && item.device_id === "edge-transferable"
            && item.status !== "revoked"
        )));
        assert.equal(restoredDb.elder_profiles[`${family.id}:elder_primary`].mobile_phone, "13800138000");
        assert.equal(restoredDb.elder_profiles[`${family.id}:elder_primary`].home_phone, "057100000000");
        assert.equal(Object.values(restoredDb.cameras).length, 2);
        assert.equal(String(restoredDb.cameras[String(claimFamilyCamera.id)].family_id), String(claimFamily.id));
        assert.equal(restoredDb.events.length, 5);
        const restoredFallEvent = restoredDb.events.find((event) => event.event_type === "fall_candidate");
        const restoredStaleOfflineEvent = restoredDb.events.find((event) => String(event.id) === String(staleOffline.event.id));
        assert.ok(restoredFallEvent);
        assert.ok(restoredStaleOfflineEvent);
        assert.equal(restoredFallEvent.summary, "疑似跌倒");
        assert.equal(String(restoredFallEvent.camera_id), String(camera.id));
        assert.equal(restoredDb.assets.length, 3);
        const restoredEventAsset = restoredDb.assets.find((asset) => asset.snapshot_path === "events/test.jpg");
        assert.equal(restoredEventAsset.purpose, "event_evidence");
        assert.equal(restoredDb.device_tokens[0].token_hash.length, 64);
        assert.equal(restoredDb.family_rules[String(family.id)].activity_detection_enabled, false);
        assert.equal(restoredDb.family_rules[String(family.id)].fire_detection_enabled, true);
        assert.equal(restoredDb.family_rules[String(claimFamily.id)].activity_detection_enabled, true);
        assert.equal(restoredDb.care_preferences[String(family.id)].image_model, "wan2.7-image");
        assert.equal(restoredDb.care_preferences[String(family.id)].metadata.care_card_schedule.delivery_time, "07:45");
        assert.equal(restoredDb.care_preferences[String(family.id)].metadata.care_card_schedule.message_focus, "先说明家里是否平稳，再给女儿一个适合打电话时聊的轻松话题。");
        assert.equal(restoredDb.care_cards.length, 1);
        assert.equal(restoredDb.care_cards[0].card_id, careCard.card_id);
        assert.ok(restoredDb.app_messages.some((message) => message.message_type === "care_card"));
        assert.equal(restoredDb.app_push_tokens.length, 1);
        assert.ok(restoredDb.notification_deliveries.length >= 2);
        assert.ok(restoredDb.scheduler_runs.some((run) => run.status === "succeeded"));
        const restoredVerificationJob = restoredDb.model_generation_jobs.find((job) => job.purpose === "vision_event_verification");
        assert.ok(restoredVerificationJob);
        assert.equal(restoredVerificationJob.metadata.attempt_count, 2);
        assert.equal(restoredDb.model_providers.length, 0);

        process.env.GOHOME_ALLOW_CLOUD_DEVICE_CLAIMS = "0";
        const hiddenClaimableDevices = await requestJson(baseUrl, "/api/device-claims/available", {
            headers: { Authorization: `Bearer ${phoneRegistered.token}` },
        });
        assert.deepEqual(hiddenClaimableDevices, []);
        const blockedCloudClaim = await fetch(`${baseUrl}/api/device-claims/claim`, {
            method: "POST",
            body: JSON.stringify({ family_id: claimFamily.id, claim_code: "GH-CLAIM001" }),
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${phoneRegistered.token}`,
            },
        });
        assert.equal(blockedCloudClaim.status, 403);

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
