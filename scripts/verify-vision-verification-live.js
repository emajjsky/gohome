#!/usr/bin/env node
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");

process.env.GOHOME_VISION_VERIFICATION_ENABLED = "1";

const { createLocalAppServer } = require("../local-app-server/server");

const DEVICE_TOKEN = "vision-live-probe-device";

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

async function main() {
    const imagePath = path.resolve(process.argv[2] || "");
    if (!imagePath || !fs.existsSync(imagePath)) {
        throw new Error("usage: node scripts/verify-vision-verification-live.js /path/to/public-sample.jpg");
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
    try {
        const capabilities = await requestJson(baseUrl, "/api/v1/ops/service-config");
        const verificationCapability = capabilities.model_capabilities.find((item) => item.capability_id === "vision-event-verification");
        if (!verificationCapability?.configured) throw new Error("vision verification model is not configured");
        const eventKey = `vision-live-${Date.now()}`;
        const media = await requestJson(
            baseUrl,
            `/api/v1/device/media-assets/upload?camera_id=1&local_camera_id=1&edge_event_id=${eventKey}&purpose=event_evidence&snapshot_path=${eventKey}.jpg&content_type=image/jpeg`,
            {
                method: "POST",
                body: fs.readFileSync(imagePath),
                headers: { Authorization: `Bearer ${DEVICE_TOKEN}`, "Content-Type": "image/jpeg" },
            },
        );
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
                snapshot_path: `${eventKey}.jpg`,
                payload: {
                    rule: { reason: "公开序列边缘端命中跌倒候选。" },
                    evidence: {
                        metrics: { fall_score: 0.90, pose_fall_score: 0.88 },
                        pose_factor_graph: { fast_fall_candidate: true, fast_fall_score: 0.91 },
                        temporal_evidence_bundle: {
                            track_id: "public-p1",
                            posture_sequence: [
                                { posture: "standing" },
                                { posture: "lying" },
                            ],
                        },
                    },
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
            if (["confirmed", "rejected", "uncertain", "failed"].includes(status)) break;
            if (status === "retrying") {
                await requestJson(baseUrl, "/api/v1/internal/vision-verifications/run", {
                    method: "POST",
                    body: JSON.stringify({ force: true, limit: 1 }),
                });
            }
        }
        const verification = event?.payload?.verification || {};
        if (!["confirmed", "rejected", "uncertain"].includes(verification.status)) {
            throw new Error(`live verification did not complete: ${JSON.stringify(verification)}`);
        }
        console.log(JSON.stringify({
            ok: true,
            model: verification.model,
            status: verification.status,
            decision: verification.decision,
            attempt_count: verification.attempt_count,
            result: verification.result,
            asset_size: media.asset.size,
        }, null, 2));
    } finally {
        await new Promise((resolve) => app.server.close(resolve));
        fs.rmSync(tempDir, { recursive: true, force: true });
    }
}

main().catch((error) => {
    console.error(error.message || error);
    process.exit(1);
});
