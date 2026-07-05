#!/usr/bin/env node
"use strict";

const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const path = require("path");
const { URL } = require("url");

const DEFAULT_PORT = Number(process.env.GOHOME_APP_SERVER_PORT || 8788);
const DEFAULT_HOST = process.env.GOHOME_APP_SERVER_HOST || "0.0.0.0";
const DEFAULT_DEVICE_TOKEN = process.env.GOHOME_DEVICE_API_TOKEN || "gohome-local-device-token";
const DEFAULT_APP_TOKEN = process.env.GOHOME_APP_TOKEN || "gohome-local-app-token";

function nowIso() {
    return new Date().toISOString();
}

function safeJsonParse(value, fallback) {
    try {
        return JSON.parse(value);
    } catch (_error) {
        return fallback;
    }
}

function ensureDir(dir) {
    fs.mkdirSync(dir, { recursive: true });
}

function readBody(req, limitBytes = 25 * 1024 * 1024) {
    return new Promise((resolve, reject) => {
        const chunks = [];
        let size = 0;
        req.on("data", (chunk) => {
            size += chunk.length;
            if (size > limitBytes) {
                reject(new Error("request body too large"));
                req.destroy();
                return;
            }
            chunks.push(chunk);
        });
        req.on("end", () => resolve(Buffer.concat(chunks)));
        req.on("error", reject);
    });
}

function parseJsonBody(req) {
    return readBody(req).then((buffer) => {
        if (!buffer.length) return {};
        return JSON.parse(buffer.toString("utf8"));
    });
}

function stableId(prefix = "") {
    return `${prefix}${Date.now().toString(36)}${crypto.randomBytes(4).toString("hex")}`;
}

function normalizeNumber(value, fallback = null) {
    if (value === null || value === undefined || value === "") return fallback;
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
}

function normalizeBool(value) {
    if (typeof value === "boolean") return value;
    if (value === "false" || value === "0" || value === 0) return false;
    return Boolean(value);
}

function createDefaultDb() {
    const timestamp = nowIso();
    return {
        version: 1,
        created_at: timestamp,
        updated_at: timestamp,
        next_ids: {
            asset: 1,
            event: 1,
            camera: 1,
            heartbeat: 1,
        },
        users: [
            {
                id: 1,
                email: "admin@gohome.local",
                display_name: "回家管理员",
                password: "gohome",
                created_at: timestamp,
            },
        ],
        families: [
            {
                id: 1,
                name: "默认家庭",
                created_at: timestamp,
            },
        ],
        devices: {},
        cameras: {},
        assets: [],
        events: [],
        heartbeats: [],
    };
}

class JsonStore {
    constructor(filePath) {
        this.filePath = filePath;
        ensureDir(path.dirname(filePath));
        this.db = fs.existsSync(filePath)
            ? { ...createDefaultDb(), ...safeJsonParse(fs.readFileSync(filePath, "utf8"), {}) }
            : createDefaultDb();
        this.save();
    }

    save() {
        this.db.updated_at = nowIso();
        fs.writeFileSync(this.filePath, `${JSON.stringify(this.db, null, 2)}\n`);
    }

    nextId(type) {
        const next = Number(this.db.next_ids[type] || 1);
        this.db.next_ids[type] = next + 1;
        return next;
    }
}

function createLocalAppServer(options = {}) {
    const rootDir = path.resolve(options.rootDir || process.cwd());
    const dataDir = path.resolve(options.dataDir || process.env.GOHOME_APP_SERVER_DATA_DIR || path.join(rootDir, "data", "app-server"));
    const mediaDir = path.join(dataDir, "media");
    const store = new JsonStore(path.join(dataDir, "db.json"));
    const deviceToken = String(options.deviceToken || DEFAULT_DEVICE_TOKEN);
    const appToken = String(options.appToken || DEFAULT_APP_TOKEN);
    const playbackTickets = new Map();

    ensureDir(mediaDir);

    function write(res, statusCode, payload, headers = {}) {
        const isBuffer = Buffer.isBuffer(payload);
        const body = isBuffer ? payload : Buffer.from(JSON.stringify(payload ?? {}, null, 2));
        res.writeHead(statusCode, {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept",
            "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
            "Cache-Control": "no-store",
            "Content-Type": isBuffer ? (headers["Content-Type"] || "application/octet-stream") : "application/json; charset=utf-8",
            "Content-Length": body.length,
            ...headers,
        });
        res.end(body);
    }

    function writeError(res, statusCode, detail) {
        write(res, statusCode, { detail });
    }

    function tokenFrom(req) {
        const header = String(req.headers.authorization || "");
        const match = header.match(/^Bearer\s+(.+)$/i);
        return match ? match[1].trim() : "";
    }

    function requireDevice(req, res) {
        if (tokenFrom(req) !== deviceToken) {
            writeError(res, 401, "device token invalid");
            return false;
        }
        return true;
    }

    function requireApp(req, res) {
        const url = new URL(req.url, "http://local");
        const token = tokenFrom(req) || url.searchParams.get("access_token") || "";
        const playbackTicket = url.searchParams.get("playback_ticket") || "";
        const ticket = playbackTicket ? playbackTickets.get(playbackTicket) : null;
        if (ticket && Number(ticket.expires_at || 0) > Date.now()) {
            return true;
        }
        if (token !== appToken) {
            writeError(res, 401, "请先登录回家 App。");
            return false;
        }
        return true;
    }

    function publicEvent(event) {
        const camera = store.db.cameras[String(event.camera_id)] || {};
        const asset = event.media_asset_id
            ? store.db.assets.find((item) => Number(item.id) === Number(event.media_asset_id))
            : null;
        return {
            id: event.id,
            type: event.event_type,
            event_type: event.event_type,
            level: event.level,
            summary: event.summary,
            room: event.room || camera.room || camera.name || "",
            camera_id: event.camera_id,
            camera_name: camera.name || event.camera_name || "",
            occurred_at: event.occurred_at,
            created_at: event.created_at,
            acknowledged: Boolean(event.acknowledged),
            resolution: event.resolution || "",
            snapshot_path: event.snapshot_path || asset?.snapshot_path || "",
            snapshot_url: event.snapshot_path || asset?.snapshot_path || "",
            media_asset_id: asset?.id || null,
            payload: event.payload || {},
        };
    }

    function currentEdgeDeviceId() {
        const device = Object.values(store.db.devices)[0];
        if (device?.device_id || device?.id) return String(device.device_id || device.id);
        const event = [...store.db.events].reverse().find((item) => item.payload?.edge_upload?.edge_device_id);
        return String(event?.payload?.edge_upload?.edge_device_id || "edge-local");
    }

    function eventList(url) {
        const limit = Math.min(100, Math.max(1, normalizeNumber(url.searchParams.get("limit"), 30)));
        const cameraId = normalizeNumber(url.searchParams.get("camera_id"), null);
        const acknowledged = url.searchParams.get("acknowledged");
        let events = [...store.db.events];
        if (cameraId !== null) {
            events = events.filter((event) => Number(event.camera_id) === cameraId);
        }
        if (acknowledged !== null) {
            const expected = normalizeBool(acknowledged);
            events = events.filter((event) => Boolean(event.acknowledged) === expected);
        }
        return events
            .sort((a, b) => String(b.occurred_at || b.created_at).localeCompare(String(a.occurred_at || a.created_at)))
            .slice(0, limit)
            .map(publicEvent);
    }

    function upsertCamera(eventPayload) {
        const rawCameraId = eventPayload.camera_id || eventPayload.payload?.camera_id || "edge-camera";
        const cameraKey = String(rawCameraId);
        const room = String(eventPayload.room || eventPayload.payload?.room || eventPayload.payload?.camera_name || "");
        const existing = store.db.cameras[cameraKey] || {};
        store.db.cameras[cameraKey] = {
            id: rawCameraId,
            name: existing.name || room || `摄像头 ${rawCameraId}`,
            room: room || existing.room || "",
            enabled: true,
            status: "online",
            updated_at: nowIso(),
        };
        return store.db.cameras[cameraKey];
    }

    function latestAssetForSnapshot(snapshotPath) {
        const normalized = String(snapshotPath || "").replace(/^\/+/, "");
        return [...store.db.assets]
            .reverse()
            .find((asset) => asset.snapshot_path === normalized || asset.relative_path === normalized || String(asset.id) === normalized);
    }

    function assetAbsolutePath(asset) {
        if (!asset?.relative_path) return "";
        const filePath = path.resolve(mediaDir, asset.relative_path);
        if (!filePath.startsWith(mediaDir)) return "";
        return filePath;
    }

    function latestMediaEvent(cameraId = null) {
        const targetCameraId = cameraId === null ? null : Number(cameraId);
        return [...store.db.events]
            .filter((event) => event.media_asset_id && (targetCameraId === null || Number(event.camera_id) === targetCameraId))
            .sort((a, b) => String(b.occurred_at || b.created_at).localeCompare(String(a.occurred_at || a.created_at)))[0] || null;
    }

    function eventAsset(event) {
        if (!event?.media_asset_id) return null;
        return store.db.assets.find((asset) => Number(asset.id) === Number(event.media_asset_id)) || null;
    }

    function latestCameraSnapshotPayload(cameraId) {
        const event = latestMediaEvent(cameraId);
        const asset = eventAsset(event);
        if (!event || !asset) {
            return { available: false };
        }
        const evidence = event.payload?.evidence || {};
        const metrics = evidence.metrics || {};
        const flags = evidence.flags || {};
        const tags = Array.isArray(evidence.tags) ? evidence.tags : [];
        return {
            available: true,
            id: event.id,
            camera_id: event.camera_id,
            image_url: asset.snapshot_path,
            snapshot_path: asset.snapshot_path,
            captured_at: event.occurred_at || asset.created_at,
            width: metrics.frame_width || null,
            height: metrics.frame_height || null,
            brightness: metrics.brightness ?? null,
            motion_score: metrics.motion_score ?? null,
            person_count: metrics.person_count ?? null,
            tags,
            analysis: {
                ...flags,
                ...(evidence.algorithms || {}),
                event_type: event.event_type,
                summary: event.summary,
                rule: event.payload?.rule || evidence.rule || {},
            },
        };
    }

    function latestCameraEvaluationPayload(cameraId) {
        const targetCameraId = Number(cameraId);
        const event = [...store.db.events]
            .filter((item) => Number(item.camera_id) === targetCameraId)
            .sort((a, b) => String(b.occurred_at || b.created_at).localeCompare(String(a.occurred_at || a.created_at)))[0];
        if (!event) {
            return {
                camera_id: targetCameraId,
                evaluated_at: nowIso(),
                state: { camera_state: "unknown" },
                candidates: [],
                explanation: "等待边缘盒子上传检测结果。",
            };
        }
        const evidence = event.payload?.evidence || {};
        const evaluation = event.payload?.evaluation || {};
        return {
            camera_id: targetCameraId,
            snapshot_id: null,
            evaluated_at: evaluation.evaluated_at || event.occurred_at || event.created_at,
            matched_rules: event.payload?.rule ? [event.payload.rule] : [],
            explanation: event.payload?.rule?.reason || event.summary,
            score: evidence.metrics?.fall_score ?? evidence.metrics?.fire_score ?? null,
            state: {
                ...(evaluation.state || {}),
                latest_event_type: event.event_type,
                latest_event_level: event.level,
            },
            candidates: [publicEvent(event)],
            analysis: evidence,
        };
    }

    function serveLatestCameraSnapshot(req, res, cameraId) {
        if (!requireApp(req, res)) return;
        write(res, 200, latestCameraSnapshotPayload(cameraId));
    }

    function serveLatestCameraEvaluation(req, res, cameraId) {
        if (!requireApp(req, res)) return;
        write(res, 200, latestCameraEvaluationPayload(cameraId));
    }

    function serveCameraMjpeg(req, res, cameraId) {
        if (!requireApp(req, res)) return;
        const boundary = `gohome-${crypto.randomBytes(4).toString("hex")}`;
        res.writeHead(200, {
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-store, no-transform",
            "Connection": "close",
            "Content-Type": `multipart/x-mixed-replace; boundary=${boundary}`,
        });

        let closed = false;
        let lastAssetId = null;
        req.on("close", () => {
            closed = true;
        });

        const writeFrame = () => {
            if (closed || res.destroyed) return;
            const event = latestMediaEvent(cameraId);
            const asset = eventAsset(event);
            const filePath = assetAbsolutePath(asset);
            if (!asset || !filePath || !fs.existsSync(filePath)) {
                return;
            }
            const frame = fs.readFileSync(filePath);
            lastAssetId = asset.id;
            res.write(`--${boundary}\r\n`);
            res.write(`Content-Type: ${asset.content_type || "image/jpeg"}\r\n`);
            res.write(`Content-Length: ${frame.length}\r\n`);
            res.write(`X-GoHome-Asset-Id: ${asset.id}\r\n\r\n`);
            res.write(frame);
            res.write("\r\n");
        };

        writeFrame();
        const timer = setInterval(() => {
            if (closed || res.destroyed) {
                clearInterval(timer);
                return;
            }
            const next = eventAsset(latestMediaEvent(cameraId));
            if (next?.id !== lastAssetId) {
                writeFrame();
            }
        }, 1000);
    }

    async function handleDeviceMediaUpload(req, res, url) {
        if (!requireDevice(req, res)) return;
        const content = await readBody(req);
        const assetId = store.nextId("asset");
        const fileName = path.basename(url.searchParams.get("file_name") || `asset-${assetId}.jpg`).replace(/[^\w.\-]+/g, "_");
        const dateDir = new Date().toISOString().slice(0, 10);
        const relativePath = path.join(dateDir, `${assetId}-${fileName}`);
        const target = path.join(mediaDir, relativePath);
        ensureDir(path.dirname(target));
        fs.writeFileSync(target, content);
        const snapshotPath = String(url.searchParams.get("snapshot_path") || relativePath).replace(/^\/+/, "");
        const asset = {
            id: assetId,
            file_name: fileName,
            content_type: url.searchParams.get("content_type") || req.headers["content-type"] || "image/jpeg",
            snapshot_path: snapshotPath,
            relative_path: relativePath,
            edge_event_id: url.searchParams.get("edge_event_id") || "",
            size: content.length,
            created_at: nowIso(),
            url: `/api/v1/video/media/snapshots/${encodeURIComponent(snapshotPath)}`,
        };
        store.db.assets.push(asset);
        store.save();
        write(res, 200, { ok: true, asset });
    }

    async function handleDeviceEvent(req, res) {
        if (!requireDevice(req, res)) return;
        const payload = await parseJsonBody(req);
        upsertCamera(payload);
        const edgeEventId = payload.payload?.edge_upload?.edge_event_id || payload.edge_event_id || "";
        const mediaFromPayload = payload.media_upload_result?.asset || payload.payload?.media_upload_result?.asset || null;
        const asset = mediaFromPayload?.id
            ? store.db.assets.find((item) => Number(item.id) === Number(mediaFromPayload.id))
            : [...store.db.assets].reverse().find((item) => String(item.edge_event_id || "") === String(edgeEventId || ""));
        const event = {
            id: store.nextId("event"),
            idempotency_key: String(payload.idempotency_key || stableId("event-")),
            edge_event_id: edgeEventId || null,
            event_type: String(payload.event_type || "event"),
            summary: String(payload.summary || "回家事件"),
            level: String(payload.level || "warning"),
            room: String(payload.room || ""),
            camera_id: payload.camera_id || null,
            camera_name: String(payload.payload?.camera_name || ""),
            snapshot_path: String(payload.snapshot_path || asset?.snapshot_path || "").replace(/^\/+/, ""),
            media_asset_id: asset?.id || null,
            occurred_at: String(payload.occurred_at || nowIso()),
            acknowledged: false,
            resolution: "",
            payload: payload.payload || {},
            created_at: nowIso(),
            updated_at: nowIso(),
        };
        const existing = store.db.events.find((item) => item.idempotency_key === event.idempotency_key);
        if (existing) {
            write(res, 200, { ok: true, event: publicEvent(existing), media_asset: asset || null, duplicate: true });
            return;
        }
        store.db.events.push(event);
        store.save();
        write(res, 200, { ok: true, event: publicEvent(event), media_asset: asset || null });
    }

    async function handleHeartbeat(req, res) {
        if (!requireDevice(req, res)) return;
        const payload = await parseJsonBody(req);
        const deviceId = String(payload.device_id || payload.id || "edge-local");
        store.db.devices[deviceId] = {
            ...store.db.devices[deviceId],
            ...payload,
            id: deviceId,
            device_id: deviceId,
            last_seen_at: nowIso(),
        };
        store.db.heartbeats.push({
            id: store.nextId("heartbeat"),
            device_id: deviceId,
            payload,
            created_at: nowIso(),
        });
        store.save();
        write(res, 200, { ok: true, server_time: nowIso(), config: {} });
    }

    function serveMedia(req, res, snapshotPath) {
        if (!requireApp(req, res)) return;
        const asset = latestAssetForSnapshot(decodeURIComponent(snapshotPath || ""));
        const filePath = assetAbsolutePath(asset);
        if (!asset || !filePath || !fs.existsSync(filePath)) {
            writeError(res, 404, "media asset not found");
            return;
        }
        write(res, 200, fs.readFileSync(filePath), {
            "Content-Type": asset.content_type || "image/jpeg",
            "Cache-Control": "private, max-age=60",
        });
    }

    function serveAsset(req, res, assetId) {
        if (!requireApp(req, res)) return;
        const asset = store.db.assets.find((item) => Number(item.id) === Number(assetId));
        const filePath = assetAbsolutePath(asset);
        if (!asset || !filePath || !fs.existsSync(filePath)) {
            writeError(res, 404, "media asset not found");
            return;
        }
        write(res, 200, fs.readFileSync(filePath), {
            "Content-Type": asset.content_type || "image/jpeg",
            "Cache-Control": "private, max-age=60",
        });
    }

    function serveStatic(req, res, url) {
        const pathname = decodeURIComponent(url.pathname === "/" ? "/index.html" : url.pathname);
        const filePath = path.resolve(rootDir, `.${pathname}`);
        if (!filePath.startsWith(rootDir) || !fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
            writeError(res, 404, "not found");
            return;
        }
        const ext = path.extname(filePath).toLowerCase();
        const types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".webmanifest": "application/manifest+json; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        };
        write(res, 200, fs.readFileSync(filePath), {
            "Content-Type": types[ext] || "application/octet-stream",
            "Cache-Control": "no-cache",
        });
    }

    async function route(req, res) {
        const url = new URL(req.url, "http://local");
        const pathname = url.pathname.replace(/\/+$/, "") || "/";

        if (req.method === "OPTIONS") {
            write(res, 204, {});
            return;
        }

        try {
            if (req.method === "GET" && pathname === "/health") {
                write(res, 200, {
                    ok: true,
                    service: "gohome-local-app-server",
                    app_server_base_url: `http://localhost:${DEFAULT_PORT}`,
                    events: store.db.events.length,
                    assets: store.db.assets.length,
                    updated_at: store.db.updated_at,
                    local_app_demo_token: appToken,
                });
                return;
            }

            if (req.method === "POST" && (pathname === "/api/auth/login" || pathname === "/api/v1/identity/login")) {
                const payload = await parseJsonBody(req);
                const user = store.db.users.find((item) => item.email === payload.email) || store.db.users[0];
                write(res, 200, { token: appToken, user: { id: user.id, email: user.email, display_name: user.display_name } });
                return;
            }

            if (req.method === "POST" && (pathname === "/api/auth/register" || pathname === "/api/v1/identity/register")) {
                const payload = await parseJsonBody(req);
                const email = String(payload.email || `user-${Date.now()}@gohome.local`).trim();
                let user = store.db.users.find((item) => item.email === email);
                if (!user) {
                    user = {
                        id: store.db.users.length + 1,
                        email,
                        display_name: String(payload.display_name || payload.name || "回家用户"),
                        password: String(payload.password || ""),
                        created_at: nowIso(),
                    };
                    store.db.users.push(user);
                    store.save();
                }
                write(res, 200, { token: appToken, user: { id: user.id, email: user.email, display_name: user.display_name } });
                return;
            }

            if (req.method === "GET" && (pathname === "/api/users/me" || pathname === "/api/v1/identity/me")) {
                if (!requireApp(req, res)) return;
                const user = store.db.users[0];
                write(res, 200, { id: user.id, email: user.email, display_name: user.display_name });
                return;
            }

            if (req.method === "GET" && pathname === "/api/families/mine") {
                if (!requireApp(req, res)) return;
                write(res, 200, store.db.families);
                return;
            }

            if (req.method === "GET" && pathname === "/api/device-bindings") {
                if (!requireApp(req, res)) return;
                const familyId = normalizeNumber(url.searchParams.get("family_id"), store.db.families[0]?.id || 1);
                const deviceId = currentEdgeDeviceId();
                write(res, 200, [{
                    id: 1,
                    family_id: familyId,
                    device_id: deviceId,
                    device_name: "回家盒子",
                    device_type: "edge-agent",
                    status: "active",
                    bound_at: store.db.created_at,
                }]);
                return;
            }

            if (req.method === "GET" && (pathname === "/api/app/device" || pathname === "/api/device")) {
                if (!requireApp(req, res)) return;
                const device = Object.values(store.db.devices)[0] || {};
                write(res, 200, {
                    device_id: currentEdgeDeviceId(),
                    name: device.name || "回家盒子",
                    worker_running: true,
                    detector_backend: device.detector_backend || "yolo",
                    yolo_model: device.yolo_model || "yolo11n.pt",
                    yolo_imgsz: device.yolo_imgsz || 640,
                    upload_agent: { configured: true, app_server_base_url: true },
                });
                return;
            }

            if (req.method === "GET" && (pathname === "/api/app/cameras" || pathname === "/api/cameras")) {
                if (!requireApp(req, res)) return;
                write(res, 200, Object.values(store.db.cameras));
                return;
            }

            const latestSnapshotMatch = pathname.match(/^\/api\/(?:app\/)?cameras\/([^/]+)\/snapshot\/latest$/);
            if (req.method === "GET" && latestSnapshotMatch) {
                serveLatestCameraSnapshot(req, res, latestSnapshotMatch[1]);
                return;
            }

            const latestEvaluationMatch = pathname.match(/^\/api\/(?:app\/)?cameras\/([^/]+)\/evaluation\/latest$/);
            if (req.method === "GET" && latestEvaluationMatch) {
                serveLatestCameraEvaluation(req, res, latestEvaluationMatch[1]);
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/video/profiles") {
                if (!requireApp(req, res)) return;
                write(res, 200, {
                    profiles: [
                        { id: "mobile", label: "移动端" },
                        { id: "monitor", label: "守护" },
                        { id: "detail", label: "细节" },
                    ],
                });
                return;
            }

            if (req.method === "POST" && pathname === "/api/v1/video/sessions") {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req);
                const ticket = stableId("play-");
                playbackTickets.set(ticket, { payload, expires_at: Date.now() + 120000 });
                write(res, 200, { ticket, expires_at: new Date(Date.now() + 120000).toISOString() });
                return;
            }

            const v1StreamMatch = pathname.match(/^\/api\/v1\/video\/cameras\/([^/]+)\/stream\.mjpg$/);
            if (req.method === "GET" && v1StreamMatch) {
                serveCameraMjpeg(req, res, v1StreamMatch[1]);
                return;
            }

            if (req.method === "GET" && pathname.startsWith("/api/v1/video/media/snapshots/")) {
                serveMedia(req, res, pathname.slice("/api/v1/video/media/snapshots/".length));
                return;
            }

            if (req.method === "GET" && pathname.startsWith("/api/v1/video/assets/")) {
                serveAsset(req, res, pathname.slice("/api/v1/video/assets/".length));
                return;
            }

            if (req.method === "POST" && pathname === "/api/v1/device/heartbeat") {
                await handleHeartbeat(req, res);
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/device/config") {
                if (!requireDevice(req, res)) return;
                write(res, 200, { ok: true, config: {} });
                return;
            }

            if (req.method === "POST" && pathname === "/api/v1/device/media-assets/upload") {
                await handleDeviceMediaUpload(req, res, url);
                return;
            }

            if (req.method === "POST" && pathname === "/api/v1/device/events") {
                await handleDeviceEvent(req, res);
                return;
            }

            if (req.method === "GET" && (
                pathname === "/api/app/events" ||
                pathname === "/api/events" ||
                pathname === "/api/v1/events"
            )) {
                if (!requireApp(req, res)) return;
                write(res, 200, eventList(url));
                return;
            }

            const eventMatch = pathname.match(/^\/api\/(?:app\/)?events\/(\d+)$/) || pathname.match(/^\/api\/v1\/events\/(\d+)$/);
            if (eventMatch && req.method === "GET") {
                if (!requireApp(req, res)) return;
                const event = store.db.events.find((item) => Number(item.id) === Number(eventMatch[1]));
                if (!event) {
                    writeError(res, 404, "event not found");
                    return;
                }
                write(res, 200, publicEvent(event));
                return;
            }
            if (eventMatch && req.method === "PATCH") {
                if (!requireApp(req, res)) return;
                const event = store.db.events.find((item) => Number(item.id) === Number(eventMatch[1]));
                if (!event) {
                    writeError(res, 404, "event not found");
                    return;
                }
                const patch = await parseJsonBody(req);
                if ("acknowledged" in patch) event.acknowledged = normalizeBool(patch.acknowledged);
                if ("resolution" in patch) event.resolution = String(patch.resolution || "");
                event.updated_at = nowIso();
                store.save();
                write(res, 200, publicEvent(event));
                return;
            }

            if (req.method === "GET" && (
                pathname === "/api/app/summary/today" ||
                pathname === "/api/summary/today" ||
                pathname === "/api/v1/summary/today"
            )) {
                if (!requireApp(req, res)) return;
                const open = store.db.events.filter((event) => !event.acknowledged).length;
                const critical = store.db.events.filter((event) => !event.acknowledged && event.level === "critical").length;
                write(res, 200, { events: store.db.events.length, open_events: open, critical_events: critical });
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/app/messages") {
                if (!requireApp(req, res)) return;
                const events = eventList(url).filter((event) => !event.acknowledged).slice(0, 5);
                write(res, 200, events.map((event) => ({
                    id: `event-${event.id}`,
                    message_type: event.level === "critical" ? "alert" : "explain",
                    title: event.summary,
                    subtitle: `${event.room || event.camera_name || "摄像头"} · ${event.event_type}`,
                    body: event.payload?.rule?.reason || event.summary,
                    facts: [event.event_type, event.level],
                    actions: [{ key: "open_event", label: "查看事件" }],
                    source_event_ids: [event.id],
                    generated_by: "local-app-server",
                    created_at: event.created_at,
                })));
                return;
            }

            serveStatic(req, res, url);
        } catch (error) {
            writeError(res, 500, error.message || "server error");
        }
    }

    const server = http.createServer(route);
    return { server, store, dataDir, appToken, deviceToken };
}

if (require.main === module) {
    const app = createLocalAppServer({ rootDir: path.resolve(__dirname, "..") });
    app.server.listen(DEFAULT_PORT, DEFAULT_HOST, () => {
        console.log(`GoHome local App server listening on http://${DEFAULT_HOST}:${DEFAULT_PORT}`);
        console.log(`App token: ${app.appToken}`);
        console.log(`Device token: ${app.deviceToken}`);
        console.log(`Data dir: ${app.dataDir}`);
    });
}

module.exports = { createLocalAppServer };
