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
            user: 2,
            family: 2,
            elder_profile: 1,
            binding: 1,
            binding_code: 1,
            device_token: 1,
            asset: 1,
            event: 1,
            camera: 1,
            heartbeat: 1,
            calendar_event: 1,
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
                member_count: 1,
                created_at: timestamp,
            },
        ],
        elder_profiles: {},
        device_bindings: [],
        binding_codes: [],
        device_tokens: [],
        devices: {},
        cameras: {},
        assets: [],
        events: [],
        heartbeats: [],
        calendar_events: [],
    };
}

class JsonStore {
    constructor(filePath) {
        this.filePath = filePath;
        ensureDir(path.dirname(filePath));
        this.db = this.normalize(fs.existsSync(filePath)
            ? { ...createDefaultDb(), ...safeJsonParse(fs.readFileSync(filePath, "utf8"), {}) }
            : createDefaultDb());
        this.save();
    }

    normalize(db) {
        const defaults = createDefaultDb();
        db.next_ids = { ...defaults.next_ids, ...(db.next_ids || {}) };
        db.users = Array.isArray(db.users) ? db.users : defaults.users;
        db.families = Array.isArray(db.families) ? db.families : defaults.families;
        db.elder_profiles = db.elder_profiles && typeof db.elder_profiles === "object" ? db.elder_profiles : {};
        db.device_bindings = Array.isArray(db.device_bindings) ? db.device_bindings : [];
        db.binding_codes = Array.isArray(db.binding_codes) ? db.binding_codes : [];
        db.device_tokens = Array.isArray(db.device_tokens) ? db.device_tokens : [];
        db.devices = db.devices && typeof db.devices === "object" ? db.devices : {};
        db.cameras = db.cameras && typeof db.cameras === "object" ? db.cameras : {};
        db.assets = Array.isArray(db.assets) ? db.assets : [];
        db.events = Array.isArray(db.events) ? db.events : [];
        db.heartbeats = Array.isArray(db.heartbeats) ? db.heartbeats : [];
        db.calendar_events = Array.isArray(db.calendar_events) ? db.calendar_events : [];
        return db;
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
        const token = tokenFrom(req);
        const issued = store.db.device_tokens.find((item) => item.token === token && item.status === "active");
        if (token !== deviceToken && !issued) {
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

    function publicUser(user) {
        return {
            id: user.id,
            email: user.email,
            display_name: user.display_name,
            created_at: user.created_at,
        };
    }

    function publicFamily(family) {
        return {
            id: family.id,
            name: family.name,
            member_count: Number(family.member_count || 1),
            created_at: family.created_at,
            updated_at: family.updated_at || family.created_at,
        };
    }

    function selectedFamily(familyId = null) {
        if (familyId !== null && familyId !== undefined && familyId !== "") {
            return store.db.families.find((item) => Number(item.id) === Number(familyId)) || null;
        }
        return store.db.families[0] || null;
    }

    function elderProfileKey(familyId, elderId = "elder_primary") {
        return `${familyId}:${elderId || "elder_primary"}`;
    }

    function defaultElderProfile(familyId, elderId = "elder_primary") {
        return {
            id: elderId,
            elder_id: elderId,
            family_id: Number(familyId),
            display_name: "张阿姨",
            relationship: "母亲",
            age: null,
            city: "杭州",
            health_notes: "",
            care_preferences: {
                fall_detection: true,
                fire_detection: true,
                inactivity_observation: true,
                daily_weather: true,
                daily_news: true,
            },
            created_at: store.db.created_at,
            updated_at: store.db.updated_at,
        };
    }

    function publicBinding(binding) {
        const device = store.db.devices[String(binding.device_id)] || {};
        return {
            id: binding.id,
            family_id: binding.family_id,
            device_id: binding.device_id,
            device_name: binding.device_name || device.name || "回家盒子",
            device_type: binding.device_type || "edge-agent",
            status: binding.status || "active",
            bound_at: binding.bound_at,
            last_seen_at: device.last_seen_at || binding.last_seen_at || null,
        };
    }

    function publicBindingCode(code) {
        return {
            id: code.id,
            family_id: code.family_id,
            code: code.code,
            status: code.status,
            note: code.note || "",
            expires_at: code.expires_at,
            created_at: code.created_at,
            used_at: code.used_at || null,
            device_id: code.device_id || "",
        };
    }

    function activeDeviceToken() {
        return [...store.db.device_tokens].reverse().find((item) => item.status === "active") || null;
    }

    function publicDeviceAuthStatus() {
        const token = activeDeviceToken();
        return {
            configured: Boolean(token),
            token: token ? {
                id: token.id,
                device_id: token.device_id,
                family_id: token.family_id,
                status: token.status,
                created_at: token.created_at,
                last_heartbeat_at: token.last_heartbeat_at || null,
            } : null,
        };
    }

    function normalizeCameraPayload(payload = {}, existing = {}) {
        const id = existing.id || payload.id || store.nextId("camera");
        const streamUrl = String(payload.stream_url || existing.stream_url || "").trim();
        const hasStreamUrl = Boolean(streamUrl);
        const explicitStatus = payload.status || existing.status || "";
        const defaultStatus = hasStreamUrl ? "pending_edge_sync" : "pending_edge_setup";
        return {
            id,
            family_id: normalizeNumber(payload.family_id, existing.family_id ?? store.db.families[0]?.id ?? 1),
            device_id: String(payload.device_id || existing.device_id || currentEdgeDeviceId()),
            name: String(payload.name || existing.name || "客厅主视"),
            room: String(payload.room || existing.room || "客厅"),
            stream_url: streamUrl,
            enabled: "enabled" in payload ? normalizeBool(payload.enabled) : ("enabled" in existing ? normalizeBool(existing.enabled) : true),
            status: String(explicitStatus || defaultStatus),
            sync_status: String(payload.sync_status || existing.sync_status || "pending_edge_sync"),
            source: String(payload.source || existing.source || "app_server_config"),
            username: payload.username ?? existing.username ?? null,
            password: payload.password !== undefined ? String(payload.password || "") : (existing.password || null),
            last_error: String(payload.last_error || existing.last_error || ""),
            last_seen_at: existing.last_seen_at || null,
            edge_reported_at: existing.edge_reported_at || null,
            created_at: existing.created_at || nowIso(),
            updated_at: nowIso(),
        };
    }

    function publicCamera(camera) {
        const { stream_url: _streamUrl, username: _username, password: _password, ...safeCamera } = camera;
        return {
            ...safeCamera,
            connection_owner: "edge_agent",
            password_set: Boolean(camera.password),
            has_stream_config: Boolean(camera.stream_url),
        };
    }

    function cameraConfigVersion() {
        const cameras = Object.values(store.db.cameras);
        const fingerprint = cameras
            .map((camera) => `${camera.id}:${camera.updated_at || ""}:${camera.enabled ? 1 : 0}:${camera.sync_status || ""}`)
            .sort()
            .join("|");
        return `camera-config-${crypto.createHash("sha1").update(fingerprint).digest("hex").slice(0, 12)}`;
    }

    function deviceCameraConfig(camera) {
        return {
            id: camera.id,
            camera_id: camera.id,
            family_id: camera.family_id || store.db.families[0]?.id || 1,
            device_id: camera.device_id || currentEdgeDeviceId(),
            name: camera.name,
            room: camera.room,
            enabled: Boolean(camera.enabled),
            status: camera.status || "pending_edge_setup",
            sync_status: camera.sync_status || "pending_edge_sync",
            source: camera.source || "app_server_config",
            stream_url: camera.stream_url || "",
            username: camera.username || "",
            password: camera.password || "",
            setup_required: !camera.stream_url,
            updated_at: camera.updated_at || null,
        };
    }

    function deviceConfigPayload() {
        return {
            ok: true,
            device_id: currentEdgeDeviceId(),
            generated_at: nowIso(),
            config_version: cameraConfigVersion(),
            cameras: Object.values(store.db.cameras).map(deviceCameraConfig),
            rules: {},
        };
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
        const token = activeDeviceToken();
        if (token?.device_id) return String(token.device_id);
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
            family_id: existing.family_id || store.db.families[0]?.id || 1,
            device_id: eventPayload.payload?.edge_upload?.edge_device_id || existing.device_id || currentEdgeDeviceId(),
            name: existing.name || room || `摄像头 ${rawCameraId}`,
            room: room || existing.room || "",
            enabled: "enabled" in existing ? existing.enabled : true,
            status: "online",
            sync_status: "edge_reported",
            source: existing.source || "edge_reported",
            stream_url: existing.stream_url || "",
            username: existing.username || "",
            password: existing.password || null,
            updated_at: nowIso(),
            edge_reported_at: nowIso(),
            last_seen_at: nowIso(),
            last_error: "",
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
        const issuedToken = store.db.device_tokens.find((item) => item.token === tokenFrom(req) && item.status === "active");
        if (issuedToken) {
            issuedToken.device_id = deviceId;
            issuedToken.last_heartbeat_at = nowIso();
        }
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
                const email = String(payload.email || "admin@gohome.local").trim();
                const user = store.db.users.find((item) => item.email === email) || store.db.users[0];
                if (!user) {
                    writeError(res, 401, "账号不存在");
                    return;
                }
                if (user.password && payload.password && String(user.password) !== String(payload.password)) {
                    writeError(res, 401, "密码不正确");
                    return;
                }
                write(res, 200, { token: appToken, user: publicUser(user) });
                return;
            }

            if (req.method === "POST" && (pathname === "/api/auth/register" || pathname === "/api/v1/identity/register")) {
                const payload = await parseJsonBody(req);
                const email = String(payload.email || `user-${Date.now()}@gohome.local`).trim();
                let user = store.db.users.find((item) => item.email === email);
                if (!user) {
                    user = {
                        id: store.nextId("user"),
                        email,
                        display_name: String(payload.display_name || payload.name || "回家用户"),
                        password: String(payload.password || ""),
                        created_at: nowIso(),
                    };
                    store.db.users.push(user);
                    store.save();
                }
                write(res, 200, { token: appToken, user: publicUser(user) });
                return;
            }

            if (req.method === "GET" && (pathname === "/api/users/me" || pathname === "/api/v1/identity/me")) {
                if (!requireApp(req, res)) return;
                const user = store.db.users[0];
                write(res, 200, publicUser(user));
                return;
            }

            if (req.method === "GET" && (pathname === "/api/families/mine" || pathname === "/api/v1/households/mine")) {
                if (!requireApp(req, res)) return;
                write(res, 200, store.db.families.map(publicFamily));
                return;
            }

            if (req.method === "POST" && (pathname === "/api/families" || pathname === "/api/v1/households")) {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req);
                const name = String(payload.name || payload.household_name || "我的家庭").trim();
                let family = store.db.families.find((item) => item.name === name);
                if (!family) {
                    family = {
                        id: store.nextId("family"),
                        name,
                        member_count: 1,
                        created_at: nowIso(),
                        updated_at: nowIso(),
                    };
                    store.db.families.push(family);
                    store.save();
                }
                write(res, 200, publicFamily(family));
                return;
            }

            if (req.method === "GET" && pathname === "/api/device-bindings") {
                if (!requireApp(req, res)) return;
                const familyId = normalizeNumber(url.searchParams.get("family_id"), store.db.families[0]?.id || 1);
                const bindings = store.db.device_bindings.filter((item) => Number(item.family_id) === Number(familyId));
                write(res, 200, bindings.map(publicBinding));
                return;
            }

            if (req.method === "POST" && pathname === "/api/device-bindings") {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req);
                const familyId = normalizeNumber(payload.family_id, store.db.families[0]?.id || 1);
                const family = selectedFamily(familyId);
                if (!family) {
                    writeError(res, 404, "family not found");
                    return;
                }
                const deviceId = String(payload.device_id || currentEdgeDeviceId());
                let binding = store.db.device_bindings.find((item) => Number(item.family_id) === Number(familyId) && item.device_id === deviceId);
                if (!binding) {
                    binding = {
                        id: store.nextId("binding"),
                        family_id: Number(familyId),
                        device_id: deviceId,
                        device_name: String(payload.device_name || "回家盒子"),
                        device_type: "edge-agent",
                        status: "active",
                        note: String(payload.note || ""),
                        bound_at: nowIso(),
                    };
                    store.db.device_bindings.push(binding);
                } else {
                    binding.status = "active";
                    binding.device_name = String(payload.device_name || binding.device_name || "回家盒子");
                    binding.note = String(payload.note || binding.note || "");
                }
                store.db.devices[deviceId] = {
                    ...(store.db.devices[deviceId] || {}),
                    id: deviceId,
                    device_id: deviceId,
                    name: binding.device_name,
                    status: "active",
                    last_seen_at: store.db.devices[deviceId]?.last_seen_at || null,
                    updated_at: nowIso(),
                };
                store.save();
                write(res, 200, publicBinding(binding));
                return;
            }

            const elderProfileMatch = pathname.match(/^\/api\/v1\/families\/([^/]+)\/elders\/([^/]+)\/profile$/);
            if (elderProfileMatch && req.method === "GET") {
                if (!requireApp(req, res)) return;
                const familyId = Number(elderProfileMatch[1]);
                const elderId = decodeURIComponent(elderProfileMatch[2]);
                const key = elderProfileKey(familyId, elderId);
                write(res, 200, store.db.elder_profiles[key] || defaultElderProfile(familyId, elderId));
                return;
            }

            if (elderProfileMatch && req.method === "PUT") {
                if (!requireApp(req, res)) return;
                const familyId = Number(elderProfileMatch[1]);
                const elderId = decodeURIComponent(elderProfileMatch[2]);
                if (!selectedFamily(familyId)) {
                    writeError(res, 404, "family not found");
                    return;
                }
                const payload = await parseJsonBody(req);
                const key = elderProfileKey(familyId, elderId);
                const existing = store.db.elder_profiles[key] || defaultElderProfile(familyId, elderId);
                store.db.elder_profiles[key] = {
                    ...existing,
                    ...payload,
                    id: elderId,
                    elder_id: elderId,
                    family_id: familyId,
                    updated_at: nowIso(),
                };
                store.save();
                write(res, 200, store.db.elder_profiles[key]);
                return;
            }

            const calendarMatch = pathname.match(/^\/api\/v1\/families\/([^/]+)\/calendar-events$/);
            if (calendarMatch && req.method === "GET") {
                if (!requireApp(req, res)) return;
                const familyId = Number(calendarMatch[1]);
                const elderId = url.searchParams.get("elder_id") || "";
                write(res, 200, store.db.calendar_events.filter((item) => (
                    Number(item.family_id) === familyId && (!elderId || item.elder_id === elderId)
                )));
                return;
            }

            if (calendarMatch && req.method === "POST") {
                if (!requireApp(req, res)) return;
                const familyId = Number(calendarMatch[1]);
                const payload = await parseJsonBody(req);
                const event = {
                    id: store.nextId("calendar_event"),
                    family_id: familyId,
                    elder_id: String(payload.elder_id || "elder_primary"),
                    title: String(payload.title || "家庭行程"),
                    starts_at: String(payload.starts_at || nowIso()),
                    note: String(payload.note || ""),
                    created_at: nowIso(),
                    updated_at: nowIso(),
                };
                store.db.calendar_events.push(event);
                store.save();
                write(res, 200, event);
                return;
            }

            const weatherMatch = pathname.match(/^\/api\/v1\/families\/([^/]+)\/weather-signals$/);
            if (weatherMatch && req.method === "GET") {
                if (!requireApp(req, res)) return;
                write(res, 200, {
                    family_id: Number(weatherMatch[1]),
                    city: url.searchParams.get("city") || "杭州",
                    condition: "多云",
                    temperature_c: 24,
                    humidity: 55,
                    advice: "环境舒适，适合午休。下午注意通风。",
                    updated_at: nowIso(),
                });
                return;
            }

            if (req.method === "GET" && (pathname === "/api/v1/devices" || pathname === "/api/v1/devices/current")) {
                if (!requireApp(req, res)) return;
                const device = {
                    device_id: currentEdgeDeviceId(),
                    name: store.db.devices[currentEdgeDeviceId()]?.name || "回家盒子",
                    status: store.db.devices[currentEdgeDeviceId()]?.status || "active",
                    last_seen_at: store.db.devices[currentEdgeDeviceId()]?.last_seen_at || null,
                    bindings: store.db.device_bindings.map(publicBinding),
                };
                write(res, 200, pathname.endsWith("/current") ? device : [device]);
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/devices/current/sync-state") {
                if (!requireApp(req, res)) return;
                write(res, 200, {
                    device_id: currentEdgeDeviceId(),
                    server_time: nowIso(),
                    config_version: cameraConfigVersion(),
                    cameras: Object.values(store.db.cameras).map(publicCamera),
                    rules_version: "local-demo-v1",
                    pending_commands: [],
                });
                return;
            }

            if (req.method === "GET" && pathname === "/api/device/binding-codes") {
                if (!requireApp(req, res)) return;
                const familyId = normalizeNumber(url.searchParams.get("family_id"), store.db.families[0]?.id || 1);
                write(res, 200, store.db.binding_codes
                    .filter((item) => Number(item.family_id) === Number(familyId))
                    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
                    .map(publicBindingCode));
                return;
            }

            if (req.method === "POST" && pathname === "/api/device/binding-codes") {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req);
                const familyId = normalizeNumber(payload.family_id, store.db.families[0]?.id || 1);
                if (!selectedFamily(familyId)) {
                    writeError(res, 404, "family not found");
                    return;
                }
                const code = {
                    id: store.nextId("binding_code"),
                    family_id: Number(familyId),
                    code: String(Math.floor(100000 + Math.random() * 900000)),
                    status: "active",
                    note: String(payload.note || ""),
                    expires_at: new Date(Date.now() + Math.max(1, normalizeNumber(payload.expires_in_minutes, 10)) * 60000).toISOString(),
                    created_at: nowIso(),
                };
                store.db.binding_codes
                    .filter((item) => Number(item.family_id) === Number(familyId) && item.status === "active")
                    .forEach((item) => { item.status = "revoked"; });
                store.db.binding_codes.push(code);
                store.save();
                write(res, 200, publicBindingCode(code));
                return;
            }

            if (req.method === "POST" && (pathname === "/api/device/token/exchange" || pathname === "/api/v1/device/token/exchange")) {
                const payload = await parseJsonBody(req);
                const code = store.db.binding_codes.find((item) => item.code === String(payload.code || "") && item.status === "active");
                if (!code || Date.parse(code.expires_at) < Date.now()) {
                    writeError(res, 400, "binding code invalid or expired");
                    return;
                }
                const deviceId = String(payload.device_id || currentEdgeDeviceId() || `edge-${crypto.randomBytes(6).toString("hex")}`);
                const token = `dev_${crypto.randomBytes(18).toString("hex")}`;
                const deviceTokenRecord = {
                    id: store.nextId("device_token"),
                    family_id: code.family_id,
                    device_id: deviceId,
                    token,
                    status: "active",
                    note: String(payload.note || code.note || ""),
                    created_at: nowIso(),
                    last_heartbeat_at: null,
                };
                store.db.device_tokens.forEach((item) => {
                    if (item.device_id === deviceId) item.status = "revoked";
                });
                store.db.device_tokens.push(deviceTokenRecord);
                code.status = "used";
                code.used_at = nowIso();
                code.device_id = deviceId;
                let binding = store.db.device_bindings.find((item) => Number(item.family_id) === Number(code.family_id) && item.device_id === deviceId);
                if (!binding) {
                    binding = {
                        id: store.nextId("binding"),
                        family_id: Number(code.family_id),
                        device_id: deviceId,
                        device_name: String(payload.device_name || "回家盒子"),
                        device_type: "edge-agent",
                        status: "active",
                        note: String(payload.note || ""),
                        bound_at: nowIso(),
                    };
                    store.db.device_bindings.push(binding);
                }
                store.db.devices[deviceId] = {
                    ...(store.db.devices[deviceId] || {}),
                    id: deviceId,
                    device_id: deviceId,
                    name: binding.device_name || "回家盒子",
                    status: "active",
                    updated_at: nowIso(),
                };
                store.save();
                write(res, 200, {
                    ok: true,
                    device_token: token,
                    token,
                    device_id: deviceId,
                    family_id: code.family_id,
                    binding: publicBinding(binding),
                    config: { upload_enabled: true },
                });
                return;
            }

            if (req.method === "GET" && pathname === "/api/device/auth-status") {
                if (!requireApp(req, res)) return;
                write(res, 200, publicDeviceAuthStatus());
                return;
            }

            if (req.method === "POST" && pathname === "/api/device/heartbeat/self") {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req);
                const token = activeDeviceToken();
                const deviceId = String(token?.device_id || currentEdgeDeviceId());
                store.db.devices[deviceId] = {
                    ...(store.db.devices[deviceId] || {}),
                    ...payload,
                    id: deviceId,
                    device_id: deviceId,
                    status: String(payload.status || "online"),
                    last_seen_at: nowIso(),
                };
                if (token) token.last_heartbeat_at = nowIso();
                store.save();
                write(res, 200, { ok: true, device: store.db.devices[deviceId], auth: publicDeviceAuthStatus() });
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
                write(res, 200, Object.values(store.db.cameras).map(publicCamera));
                return;
            }

            if (req.method === "POST" && pathname === "/api/cameras") {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req);
                const camera = normalizeCameraPayload(payload);
                store.db.cameras[String(camera.id)] = camera;
                store.save();
                write(res, 200, publicCamera(camera));
                return;
            }

            if (req.method === "POST" && pathname === "/api/cameras/test-connection") {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req);
                const streamUrl = String(payload.stream_url || "").trim();
                write(res, 200, {
                    ok: true,
                    status: streamUrl ? "pending_edge_verify" : "pending_edge_setup",
                    connection_owner: "edge_agent",
                    has_stream_config: Boolean(streamUrl),
                    latency_ms: streamUrl ? 42 : null,
                    message: streamUrl
                        ? "配置已保存到服务器，等待家庭盒子同步后实际抓帧验证。"
                        : "App 不直接连接摄像头，等待家庭盒子在本地完成接入。",
                });
                return;
            }

            const cameraMatch = pathname.match(/^\/api\/cameras\/([^/]+)$/);
            if (cameraMatch && req.method === "PATCH") {
                if (!requireApp(req, res)) return;
                const cameraId = String(cameraMatch[1]);
                const existing = store.db.cameras[cameraId];
                if (!existing) {
                    writeError(res, 404, "camera not found");
                    return;
                }
                const patch = await parseJsonBody(req);
                const camera = normalizeCameraPayload({ ...existing, ...patch, id: existing.id }, existing);
                store.db.cameras[cameraId] = camera;
                store.save();
                write(res, 200, publicCamera(camera));
                return;
            }

            if (cameraMatch && req.method === "DELETE") {
                if (!requireApp(req, res)) return;
                const cameraId = String(cameraMatch[1]);
                if (!store.db.cameras[cameraId]) {
                    writeError(res, 404, "camera not found");
                    return;
                }
                delete store.db.cameras[cameraId];
                store.save();
                write(res, 200, { ok: true, deleted: Number(cameraId) || cameraId });
                return;
            }

            const cameraTestMatch = pathname.match(/^\/api\/cameras\/([^/]+)\/test$/);
            if (cameraTestMatch && req.method === "POST") {
                if (!requireApp(req, res)) return;
                const camera = store.db.cameras[String(cameraTestMatch[1])];
                if (!camera) {
                    writeError(res, 404, "camera not found");
                    return;
                }
                camera.status = camera.stream_url ? "pending_edge_verify" : "pending_edge_setup";
                camera.sync_status = "pending_edge_sync";
                camera.last_error = "";
                camera.updated_at = nowIso();
                store.save();
                write(res, 200, {
                    ok: true,
                    camera: publicCamera(camera),
                    message: "已提交给家庭盒子，等待同步并回传在线状态。",
                });
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
                write(res, 200, deviceConfigPayload());
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
