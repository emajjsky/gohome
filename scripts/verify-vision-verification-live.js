#!/usr/bin/env node
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");

process.env.GOHOME_VISION_VERIFICATION_ENABLED = "1";

const { createLocalAppServer } = require("../local-app-server/server");
const { createCosStorage } = require("../local-app-server/cos-storage");

const DEVICE_TOKEN = "vision-live-probe-device";
const FRAME_ROLES = ["before", "transition", "evidence", "current"];
const DEFAULT_FRAME_URLS = [
    "https://img.alicdn.com/imgextra/i3/O1CN01K3SgGo1eqmlUgeE9b_!!6000000003923-0-tps-3840-2160.jpg",
    "https://img.alicdn.com/imgextra/i4/O1CN01BjZvwg1Y23CF5qIRB_!!6000000003000-0-tps-3840-2160.jpg",
    "https://img.alicdn.com/imgextra/i4/O1CN01Ib0clU27vTgBdbVLQ_!!6000000007859-0-tps-3840-2160.jpg",
    "https://img.alicdn.com/imgextra/i1/O1CN01aygPLW1s3EXCdSN4X_!!6000000005710-0-tps-3840-2160.jpg",
];

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

async function requestJson(baseUrl, pathname, options = {}) {
    const response = await fetch(`${baseUrl}${pathname}`, {
        ...options,
        headers: {
            Accept: "application/json",
            ...(options.body && !(options.body instanceof Buffer) ? { "Content-Type": "application/json" } : {}),
            ...(options.headers || {}),
        },
    });
    const text = await response.text();
    const payload = text ? JSON.parse(text) : null;
    if (!response.ok) throw new Error(`${options.method || "GET"} ${pathname}: ${response.status} ${text}`);
    return payload;
}

async function frameBytes(source) {
    if (/^https?:\/\//i.test(source)) {
        const response = await fetch(source);
        if (!response.ok) throw new Error(`frame download failed: ${response.status} ${source}`);
        return Buffer.from(await response.arrayBuffer());
    }
    const filePath = path.resolve(source);
    if (!fs.existsSync(filePath)) throw new Error(`frame file not found: ${filePath}`);
    return fs.readFileSync(filePath);
}

async function main() {
    const frameSources = process.argv.slice(2);
    const sources = frameSources.length ? frameSources : DEFAULT_FRAME_URLS;
    if (sources.length !== FRAME_ROLES.length) {
        throw new Error("usage: node scripts/verify-vision-verification-live.js [before transition evidence current]");
    }
    const frames = await Promise.all(sources.map((source) => frameBytes(source)));
    if (new Set(frames.map((bytes) => bytes.toString("base64"))).size !== FRAME_ROLES.length) {
        throw new Error("vision probe requires four distinct frame images");
    }
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "gohome-vision-live-"));
    const app = createLocalAppServer({
        rootDir: path.resolve(__dirname, ".."),
        dataDir: tempDir,
        deviceToken: DEVICE_TOKEN,
    });
    await new Promise((resolve, reject) => {
        app.server.once("error", reject);
        app.server.listen(0, "127.0.0.1", resolve);
    });
    const baseUrl = `http://127.0.0.1:${app.server.address().port}`;
    const opsHeaders = process.env.GOHOME_OPS_TOKEN
        ? { Authorization: `Bearer ${process.env.GOHOME_OPS_TOKEN}` }
        : {};
    const mediaAssets = [];
    try {
        const capabilities = await requestJson(baseUrl, "/api/v1/ops/service-config", { headers: opsHeaders });
        const verificationCapability = capabilities.model_capabilities.find((item) => item.capability_id === "vision-event-verification");
        if (!verificationCapability?.configured) throw new Error("vision verification model is not configured");
        const eventKey = `vision-live-${Date.now()}`;
        const startedAt = Date.now();
        for (const [index, role] of FRAME_ROLES.entries()) {
            const capturedAt = new Date(startedAt + index * 500).toISOString();
            const uploadQuery = new URLSearchParams({
                camera_id: "1",
                local_camera_id: "1",
                edge_event_id: eventKey,
                purpose: role === "current" ? "event_evidence" : "event_evidence_keyframe",
                snapshot_path: `${eventKey}-${role}.jpg`,
                content_type: "image/jpeg",
                idempotency_key: `event-evidence:${eventKey}:${role}`,
                evidence_frame_role: role,
                captured_at: capturedAt,
            });
            const media = await requestJson(
                baseUrl,
                `/api/v1/device/media-assets/upload?${uploadQuery}`,
                {
                    method: "POST",
                    body: frames[index],
                    headers: { Authorization: `Bearer ${DEVICE_TOKEN}`, "Content-Type": "image/jpeg" },
                },
            );
            mediaAssets.push({ ...media.asset, role, captured_at: capturedAt });
        }
        const created = await requestJson(baseUrl, "/api/v1/device/events", {
            method: "POST",
            body: JSON.stringify({
                idempotency_key: `event:${eventKey}`,
                edge_event_id: eventKey,
                event_type: "fall_candidate",
                summary: "公开样本视觉复核探测",
                level: "critical",
                room: "公开数据集",
                camera_id: 1,
                snapshot_path: `${eventKey}-current.jpg`,
                payload: {
                    validation: { test_event: true, vision_verification_probe: true },
                    rule: { reason: "公开序列边缘端命中跌倒候选。" },
                    evidence: {
                        metrics: { fall_score: 0.90, pose_fall_score: 0.88 },
                        pose_factor_graph: { fast_fall_candidate: true, fast_fall_score: 0.91 },
                        temporal_evidence_bundle: {
                            track_id: "public-p1",
                            snapshots: mediaAssets.map((asset) => ({
                                snapshot_path: asset.snapshot_path,
                                observed_at: asset.captured_at,
                                role: asset.role,
                            })),
                            posture_sequence: [
                                { posture: "standing" },
                                { posture: "lying" },
                            ],
                        },
                    },
                    evidence_media_assets: mediaAssets.map((asset) => ({
                        asset,
                        role: asset.role,
                        captured_at: asset.captured_at,
                    })),
                    media_upload_result: { asset: mediaAssets.at(-1) },
                    edge_upload: { edge_event_id: eventKey, edge_device_id: "public-probe" },
                },
            }),
            headers: { Authorization: `Bearer ${DEVICE_TOKEN}` },
        });
        let event = created.event;
        for (let attempt = 0; attempt < 12; attempt += 1) {
            await sleep(1500);
            event = app.store.db.events.find((item) => String(item.id) === String(created.event.id));
            const status = event?.payload?.verification?.status;
            if (["confirmed", "suspected", "rejected", "uncertain", "failed"].includes(status)) break;
            if (status === "retrying") {
                await requestJson(baseUrl, "/api/v1/internal/vision-verifications/run", {
                    method: "POST",
                    body: JSON.stringify({ force: true, limit: 1 }),
                    headers: opsHeaders,
                });
            }
        }
        const verification = event?.payload?.verification || {};
        if (!["confirmed", "suspected", "rejected", "uncertain"].includes(verification.status)) {
            throw new Error(`live verification did not complete: ${JSON.stringify(verification)}`);
        }
        console.log(JSON.stringify({
            ok: true,
            model: verification.model,
            status: verification.status,
            decision: verification.decision,
            attempt_count: verification.attempt_count,
            result: verification.result,
            frame_count: mediaAssets.length,
            asset_sizes: mediaAssets.map((asset) => asset.size),
        }, null, 2));
    } finally {
        await new Promise((resolve) => app.server.close(resolve));
        for (const asset of mediaAssets) {
            if (asset.storage_provider === "cos" && asset.storage_key) {
                await createCosStorage().deleteObject({ key: asset.storage_key });
            }
        }
        fs.rmSync(tempDir, { recursive: true, force: true });
    }
}

main().catch((error) => {
    console.error(error.message || error);
    process.exit(1);
});
