#!/usr/bin/env node
"use strict";

const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const https = require("https");
const path = require("path");
const { URL } = require("url");

const DEFAULT_PORT = Number(process.env.GOHOME_APP_SERVER_PORT || 8788);
const DEFAULT_HOST = process.env.GOHOME_APP_SERVER_HOST || "0.0.0.0";
const DEFAULT_DEVICE_TOKEN = process.env.GOHOME_DEVICE_API_TOKEN || "gohome-local-device-token";
const DEFAULT_APP_TOKEN = process.env.GOHOME_APP_TOKEN || "gohome-local-app-token";
const DEFAULT_BOX_ADMIN_USERNAME = process.env.GOHOME_BOX_ADMIN_USERNAME || "admin";
const DEFAULT_BOX_ADMIN_PASSWORD = process.env.GOHOME_BOX_ADMIN_PASSWORD || "123456";
const DEFAULT_STORE_KIND = process.env.GOHOME_APP_STORE || (process.env.GOHOME_DATABASE_URL || process.env.DATABASE_URL ? "postgres" : "json");

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

function sha256(value) {
    if (!value) return "";
    return crypto.createHash("sha256").update(String(value)).digest("hex");
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

function normalizeRemoteAddress(value) {
    return String(value || "")
        .replace(/^::ffff:/, "")
        .replace(/^::1$/, "127.0.0.1")
        .trim();
}

function normalizeBaseUrl(value) {
    const raw = String(value || "").trim().replace(/\/+$/, "");
    if (!raw || !/^https?:\/\//i.test(raw)) return "";
    try {
        const parsed = new URL(raw);
        return `${parsed.protocol}//${parsed.host}`;
    } catch (_error) {
        return "";
    }
}

function maxExistingId(items) {
    return items.reduce((maxId, item) => {
        const id = Number(item?.id);
        return Number.isFinite(id) ? Math.max(maxId, id) : maxId;
    }, 0);
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
            care_card: 1,
            model_generation_job: 1,
            content_recommendation: 1,
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
        care_preferences: {},
        care_cards: [],
        model_providers: [],
        model_generation_jobs: [],
        content_sources: [],
        content_recommendations: [],
    };
}

class JsonStore {
    constructor(filePath) {
        this.kind = "json";
        this.filePath = filePath;
        ensureDir(path.dirname(filePath));
        this.db = normalizeDb(fs.existsSync(filePath)
            ? { ...createDefaultDb(), ...safeJsonParse(fs.readFileSync(filePath, "utf8"), {}) }
            : createDefaultDb());
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

function normalizeDb(db) {
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
    db.care_preferences = db.care_preferences && typeof db.care_preferences === "object" ? db.care_preferences : {};
    db.care_cards = Array.isArray(db.care_cards) ? db.care_cards : [];
    db.model_providers = Array.isArray(db.model_providers) ? db.model_providers : [];
    db.model_generation_jobs = Array.isArray(db.model_generation_jobs) ? db.model_generation_jobs : [];
    db.content_sources = Array.isArray(db.content_sources) ? db.content_sources : [];
    db.content_recommendations = Array.isArray(db.content_recommendations) ? db.content_recommendations : [];
    const idSources = {
        user: db.users,
        family: db.families,
        binding: db.device_bindings,
        binding_code: db.binding_codes,
        device_token: db.device_tokens,
        asset: db.assets,
        event: db.events,
        camera: Object.values(db.cameras),
        heartbeat: db.heartbeats,
        calendar_event: db.calendar_events,
        care_card: db.care_cards,
        model_generation_job: db.model_generation_jobs,
        content_recommendation: db.content_recommendations,
    };
    for (const [type, items] of Object.entries(idSources)) {
        db.next_ids[type] = Math.max(Number(db.next_ids[type] || 1), maxExistingId(items) + 1);
    }
    return db;
}

function createLocalAppServer(options = {}) {
    const rootDir = path.resolve(options.rootDir || process.cwd());
    const dataDir = path.resolve(options.dataDir || process.env.GOHOME_APP_SERVER_DATA_DIR || path.join(rootDir, "data", "app-server"));
    const mediaDir = path.join(dataDir, "media");
    const store = options.store || new JsonStore(path.join(dataDir, "db.json"));
    const deviceToken = String(options.deviceToken || DEFAULT_DEVICE_TOKEN);
    const appToken = String(options.appToken || DEFAULT_APP_TOKEN);
    const playbackTickets = new Map();
    const boxAdminSessions = new Map();
    const secretsPath = path.join(dataDir, "secrets.json");

    ensureDir(mediaDir);

    const defaultModelProviders = [
        {
            provider_id: "text-default",
            provider: "template",
            model: "care-template-v1",
            purpose: "care_text",
            enabled: true,
            configured: true,
        },
        {
            provider_id: "image-wan",
            provider: "wan",
            model: "wan2.7",
            purpose: "care_image",
            enabled: false,
            configured: false,
        },
    ];

    function readSecrets() {
        const secrets = fs.existsSync(secretsPath)
            ? safeJsonParse(fs.readFileSync(secretsPath, "utf8"), {})
            : {};
        return {
            version: 1,
            model_provider_api_keys: {
                ...(secrets.model_provider_api_keys || {}),
            },
        };
    }

    function writeSecrets(secrets) {
        ensureDir(path.dirname(secretsPath));
        fs.writeFileSync(secretsPath, `${JSON.stringify(secrets, null, 2)}\n`, { mode: 0o600 });
        try {
            fs.chmodSync(secretsPath, 0o600);
        } catch (_error) {
            // Best effort on filesystems that do not support chmod.
        }
    }

    function localProviderSecretRef(providerId) {
        return `local:model-provider:${providerId}`;
    }

    function providerEnvKeys(provider) {
        const providerId = String(provider.provider_id || "");
        const purpose = String(provider.purpose || "");
        const providerName = String(provider.provider || "");
        const keys = [];
        if (providerId === "text-default" || purpose === "care_text") {
            keys.push("GOHOME_TEXT_MODEL_API_KEY", "OPENAI_API_KEY");
        }
        if (providerId === "image-wan" || providerName === "wan" || purpose === "care_image") {
            keys.push("GOHOME_WAN_API_KEY", "DASHSCOPE_API_KEY", "WAN_API_KEY");
        }
        return [...new Set(keys)];
    }

    function hasLocalProviderSecret(providerId) {
        const record = readSecrets().model_provider_api_keys[String(providerId)] || null;
        return Boolean(record?.api_key);
    }

    function setLocalProviderSecret(providerId, apiKey) {
        const key = String(apiKey || "").trim();
        if (!key) return "";
        const secrets = readSecrets();
        secrets.model_provider_api_keys[String(providerId)] = {
            api_key: key,
            sha256: sha256(key),
            updated_at: nowIso(),
        };
        writeSecrets(secrets);
        return localProviderSecretRef(providerId);
    }

    function clearLocalProviderSecret(providerId) {
        const secrets = readSecrets();
        delete secrets.model_provider_api_keys[String(providerId)];
        writeSecrets(secrets);
    }

    function modelProviders() {
        const byId = new Map(defaultModelProviders.map((provider) => [provider.provider_id, { ...provider }]));
        for (const provider of store.db.model_providers) {
            if (!provider?.provider_id) continue;
            byId.set(provider.provider_id, { ...(byId.get(provider.provider_id) || {}), ...provider });
        }
        return [...byId.values()];
    }

    function providerSecretStatus(provider) {
        const envKey = providerEnvKeys(provider).find((key) => Boolean(process.env[key])) || "";
        const localSecret = hasLocalProviderSecret(provider.provider_id);
        const configuredRef = String(provider.api_key_secret_ref || "").trim();
        const requiresSecret = Boolean(provider.provider && provider.provider !== "template");
        const apiKeySet = Boolean(envKey || localSecret || configuredRef || provider.api_key_set);
        const secretMode = envKey
            ? "env"
            : (localSecret ? "local" : (configuredRef ? "secret_ref" : (requiresSecret ? "unset" : "not_required")));
        return {
            requires_secret: requiresSecret,
            api_key_set: apiKeySet,
            configured: requiresSecret ? apiKeySet : provider.configured !== false,
            secret_mode: secretMode,
            api_key_secret_ref: configuredRef || (localSecret ? localProviderSecretRef(provider.provider_id) : ""),
            env_keys: providerEnvKeys(provider),
            active_env_key: envKey,
        };
    }

    function publicModelProvider(provider) {
        const secret = providerSecretStatus(provider);
        return {
            provider_id: provider.provider_id,
            provider: provider.provider || "",
            model: provider.model || "",
            purpose: provider.purpose || "care_text",
            enabled: Boolean(provider.enabled),
            configured: secret.configured,
            api_key_set: secret.api_key_set,
            api_key_secret_ref: secret.api_key_secret_ref,
            requires_secret: secret.requires_secret,
            secret_mode: secret.secret_mode,
            env_keys: secret.env_keys,
            active_env_key: secret.active_env_key,
            created_at: provider.created_at || null,
            updated_at: provider.updated_at || null,
        };
    }

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
        const tokenHash = sha256(token);
        const issued = store.db.device_tokens.find((item) => item.status === "active" && (
            item.token === token || (item.token_hash && item.token_hash === tokenHash)
        ));
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
            local_camera_id: payload.local_camera_id ?? existing.local_camera_id ?? null,
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

    function isAppConfiguredCamera(camera = {}) {
        return String(camera.source || "app_server_config") !== "edge_reported";
    }

    function appConfigCameras() {
        return Object.values(store.db.cameras).filter(isAppConfiguredCamera);
    }

    function sameDeviceScope(camera, deviceId) {
        const cameraDeviceId = String(camera.device_id || "");
        const targetDeviceId = String(deviceId || "");
        return !cameraDeviceId || !targetDeviceId || cameraDeviceId === targetDeviceId;
    }

    function findAppCameraByLocalReport(report, rawCameraId, deviceId) {
        const localIds = [
            report.local_camera_id,
            report.edge_camera_id,
            report.local_id,
            rawCameraId,
        ]
            .filter((value) => value !== null && value !== undefined && value !== "")
            .map((value) => String(value));
        if (!localIds.length) return null;
        const localIdSet = new Set(localIds);
        return appConfigCameras().find((camera) => sameDeviceScope(camera, deviceId) && [
            camera.local_camera_id,
            camera.edge_camera_id,
            camera.local_id,
        ].some((value) => value !== null && value !== undefined && value !== "" && localIdSet.has(String(value)))) || null;
    }

    function resolveAppCameraForDeviceCameraId(rawCameraId, report = {}, deviceId = "") {
        if (rawCameraId === null || rawCameraId === undefined || rawCameraId === "") return null;
        const existingById = store.db.cameras[String(rawCameraId)] || null;
        if (existingById && isAppConfiguredCamera(existingById)) return existingById;
        return findAppCameraByLocalReport(report, rawCameraId, deviceId);
    }

    function inferredDeviceBaseUrl(req, runtime = {}) {
        const runtimeBase = normalizeBaseUrl(runtime.lan_url || runtime.service_url || runtime.api_base_url);
        if (runtimeBase) return runtimeBase;
        const remoteAddress = normalizeRemoteAddress(req.socket?.remoteAddress || req.connection?.remoteAddress || "");
        if (!remoteAddress || remoteAddress === "127.0.0.1") return "";
        const port = normalizeNumber(runtime.api_port || runtime.port, 8711);
        return normalizeBaseUrl(`http://${remoteAddress}:${port}`);
    }

    function streamProxyTokenForDevice(deviceId) {
        const issued = [...store.db.device_tokens]
            .reverse()
            .find((item) => item.status === "active" && (!deviceId || String(item.device_id || "") === String(deviceId)));
        return issued?.token || activeDeviceToken()?.token || deviceToken;
    }

    function streamProfileConfig(profile) {
        const normalized = String(profile || "mobile").trim().toLowerCase();
        if (normalized === "detail") return { fps: 5, width: 1280, height: 720, quality: 78, drop: 4 };
        if (normalized === "monitor") return { fps: 4, width: 960, height: 540, quality: 70, drop: 5 };
        return { fps: 3, width: 720, height: 405, quality: 64, drop: 6 };
    }

    function cameraStreamProxyTarget(req, cameraId) {
        const camera = store.db.cameras[String(cameraId)];
        if (!camera) return null;
        const localCameraId = normalizeNumber(camera.local_camera_id || camera.edge_camera_id || camera.local_id, null);
        if (!localCameraId) return null;
        const device = store.db.devices[String(camera.device_id || "")] || Object.values(store.db.devices)[0] || {};
        const runtime = device.runtime || {};
        const base = [
            camera.device_lan_url,
            device.lan_url,
            runtime.lan_url,
            device.service_url,
            runtime.service_url,
            inferredDeviceBaseUrl(req, runtime),
        ].map(normalizeBaseUrl).find(Boolean);
        if (!base) return null;
        return {
            base,
            localCameraId,
            token: streamProxyTokenForDevice(camera.device_id || device.device_id || device.id),
        };
    }

    function cameraConfigVersion() {
        const cameras = appConfigCameras();
        const fingerprint = cameras
            .map((camera) => JSON.stringify({
                id: camera.id,
                family_id: camera.family_id || null,
                device_id: camera.device_id || "",
                name: camera.name || "",
                room: camera.room || "",
                stream_url: camera.stream_url || "",
                username: camera.username || "",
                password: camera.password || "",
                enabled: Boolean(camera.enabled),
            }))
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
            cameras: appConfigCameras().map(deviceCameraConfig),
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

    function dateKeyShanghai(date = new Date()) {
        return new Intl.DateTimeFormat("en-CA", {
            timeZone: "Asia/Shanghai",
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
        }).format(date);
    }

    function defaultCarePreferences(familyId) {
        return {
            family_id: Number(familyId),
            elder_id: "elder_primary",
            frequency: "daily",
            quiet_hours: { start: "21:30", end: "08:00" },
            interests: ["天气", "养生", "家常", "戏曲"],
            text_model_enabled: false,
            image_generation_enabled: false,
            image_provider: "",
            image_model: "",
            content_recommendations_enabled: false,
            content_sources_enabled: false,
            updated_at: nowIso(),
        };
    }

    function carePreferences(familyId) {
        const key = String(familyId || store.db.families[0]?.id || 1);
        return store.db.care_preferences[key] || defaultCarePreferences(key);
    }

    function publicCarePreferences(preferences) {
        return {
            ...preferences,
            content_sources_enabled: Boolean(preferences.content_sources_enabled),
            content_recommendations_enabled: Boolean(preferences.content_recommendations_enabled),
            image_generation_enabled: Boolean(preferences.image_generation_enabled),
            text_model_enabled: Boolean(preferences.text_model_enabled),
        };
    }

    function publicCareCard(card) {
        return {
            id: card.id,
            card_id: card.card_id,
            family_id: card.family_id,
            elder_id: card.elder_id,
            card_date: card.card_date,
            card_type: card.card_type,
            title: card.title,
            body: card.body,
            facts: Array.isArray(card.facts) ? card.facts : [],
            source_message_ids: Array.isArray(card.source_message_ids) ? card.source_message_ids : [],
            image_mode: card.image_mode || "none",
            image_url: card.image_url || "",
            actions: Array.isArray(card.actions) ? card.actions : [],
            status: card.status || "open",
            generated_by: card.generated_by || "care-template-v1",
            source_summary: Array.isArray(card.source_summary) ? card.source_summary : [],
            content_recommendations: Array.isArray(card.content_recommendations) ? card.content_recommendations : [],
            created_at: card.created_at,
            updated_at: card.updated_at,
        };
    }

    function careCardFacts(familyId) {
        const cameras = appConfigCameras();
        const onlineCameras = cameras.filter((camera) => String(camera.status || "").toLowerCase() === "online");
        const recentCutoff = Date.now() - 24 * 60 * 60 * 1000;
        const recentEvents = store.db.events.filter((event) => {
            const timestamp = Date.parse(event.occurred_at || event.created_at || "");
            return Number.isFinite(timestamp) && timestamp >= recentCutoff;
        });
        const openEvents = recentEvents.filter((event) => !event.acknowledged);
        const criticalEvents = openEvents.filter((event) => event.level === "critical");
        const device = Object.values(store.db.devices)[0] || {};
        const family = selectedFamily(familyId) || store.db.families[0] || {};
        const profile = store.db.elder_profiles[elderProfileKey(family.id || familyId, "elder_primary")]
            || defaultElderProfile(family.id || familyId, "elder_primary");
        const facts = [];
        if (device.last_seen_at) {
            facts.push("家庭盒子在线，今天仍在同步状态。");
        } else {
            facts.push("家庭盒子还没有新的在线时间，建议先确认网络。");
        }
        if (cameras.length) {
            facts.push(`${onlineCameras.length}/${cameras.length} 路摄像头在线同步。`);
        } else {
            facts.push("还没有配置摄像头，亲情关怀只能使用家庭资料和日程。");
        }
        if (criticalEvents.length) {
            facts.push(`最近 24 小时有 ${criticalEvents.length} 条高优先级事件等待处理。`);
        } else if (openEvents.length) {
            facts.push(`最近 24 小时有 ${openEvents.length} 条普通提醒等待查看。`);
        } else {
            facts.push("最近 24 小时没有未处理的高优先级告警。");
        }
        facts.push(`${profile.display_name || "家人"} 所在城市按 ${profile.city || "杭州"} 生成天气问候。`);
        return { facts, cameras, onlineCameras, openEvents, criticalEvents, device, profile };
    }

    function generateCareCard(familyId, options = {}) {
        const targetFamilyId = Number(familyId || store.db.families[0]?.id || 1);
        const cardDate = dateKeyShanghai();
        const existing = store.db.care_cards.find((card) => (
            Number(card.family_id) === targetFamilyId && card.card_date === cardDate && card.card_type === "daily"
        ));
        if (existing && !options.force && existing.generated_by === "care-template-v2") return existing;
        const preferences = carePreferences(targetFamilyId);
        const { facts, onlineCameras, openEvents, criticalEvents, profile } = careCardFacts(targetFamilyId);
        const displayName = profile.display_name || "家人";
        const title = criticalEvents.length
            ? "今天有重要提醒需要先看"
            : "今天家里整体平稳";
        const body = criticalEvents.length
            ? `${displayName} 家里有高优先级事件等待确认，建议先查看证据，再联系家里。`
            : `${displayName} 家里设备仍在同步，当前没有未处理的高优先级告警。可以找个轻松的时间打个电话，问问今天过得怎么样。`;
        const sourceSummary = [
            "设备在线状态",
            "摄像头同步状态",
            "未处理事件",
            "老人资料",
        ];
        const card = {
            id: existing?.id || store.nextId("care_card"),
            card_id: existing?.card_id || `care-${targetFamilyId}-${cardDate}`,
            family_id: targetFamilyId,
            elder_id: preferences.elder_id || "elder_primary",
            card_date: cardDate,
            card_type: "daily",
            title,
            body,
            facts,
            source_message_ids: [],
            image_mode: preferences.image_generation_enabled ? "pending_provider" : "none",
            image_url: "",
            actions: [
                { key: "call", label: "打电话问候" },
                { key: "open_watch", label: onlineCameras.length ? "看看家里" : "查看设备" },
                { key: "open_events", label: openEvents.length ? "查看提醒" : "查看今日状态" },
            ],
            status: "open",
            generated_by: "care-template-v2",
            source_summary: sourceSummary,
            content_recommendations: [],
            created_at: existing?.created_at || nowIso(),
            updated_at: nowIso(),
        };
        if (existing) {
            Object.assign(existing, card);
            return existing;
        }
        store.db.care_cards.push(card);
        return card;
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
        const deviceId = String(eventPayload.device_id || eventPayload.payload?.edge_upload?.edge_device_id || currentEdgeDeviceId());
        const mapped = resolveAppCameraForDeviceCameraId(rawCameraId, {
            ...eventPayload,
            local_camera_id: eventPayload.local_camera_id || eventPayload.payload?.local_camera_id,
        }, deviceId);
        if (mapped) {
            const mappedKey = String(mapped.id);
            store.db.cameras[mappedKey] = {
                ...mapped,
                device_id: mapped.device_id || deviceId,
                status: mapped.status || "online",
                last_seen_at: nowIso(),
                edge_reported_at: nowIso(),
                last_error: "",
            };
            return store.db.cameras[mappedKey];
        }
        const existing = store.db.cameras[cameraKey] || {};
        store.db.cameras[cameraKey] = {
            id: rawCameraId,
            family_id: existing.family_id || store.db.families[0]?.id || 1,
            device_id: deviceId || existing.device_id || currentEdgeDeviceId(),
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

    function writeEmptyMjpeg(res) {
        const boundary = `gohome-${crypto.randomBytes(4).toString("hex")}`;
        res.writeHead(200, {
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-store, no-transform",
            "Connection": "close",
            "Content-Type": `multipart/x-mixed-replace; boundary=${boundary}`,
            "X-GoHome-Stream-State": "waiting_for_frame",
        });
        if (typeof res.flushHeaders === "function") res.flushHeaders();
    }

    function applyStreamParams(sourceUrl, req) {
        const requestedUrl = new URL(req.url, "http://local");
        const profile = requestedUrl.searchParams.get("profile") || "mobile";
        const defaults = streamProfileConfig(profile);
        sourceUrl.searchParams.set("profile", profile);
        for (const [key, value] of Object.entries(defaults)) {
            sourceUrl.searchParams.set(key, String(requestedUrl.searchParams.get(key) || value));
        }
        return sourceUrl;
    }

    function proxyMjpegRequest(req, res, sourceUrl, headers = {}, metadata = {}) {
        return new Promise((resolve) => {
            const transport = sourceUrl.protocol === "https:" ? https : http;
            const upstreamReq = transport.request(sourceUrl, {
                method: "GET",
                headers: {
                    Accept: "multipart/x-mixed-replace,image/*,*/*",
                    ...headers,
                },
                timeout: 3500,
            }, (upstreamRes) => {
                const status = Number(upstreamRes.statusCode || 0);
                if (status < 200 || status >= 300) {
                    upstreamRes.resume();
                    resolve(false);
                    return;
                }

                res.writeHead(200, {
                    "Access-Control-Allow-Origin": "*",
                    "Cache-Control": "no-store, no-transform",
                    "Connection": "close",
                    "Content-Type": upstreamRes.headers["content-type"] || "multipart/x-mixed-replace; boundary=frame",
                    "X-GoHome-Stream-State": "proxied",
                    ...metadata,
                });
                upstreamRes.pipe(res);
                upstreamRes.on("error", () => {
                    if (!res.destroyed) res.destroy();
                });
                req.on("close", () => {
                    upstreamReq.destroy();
                    upstreamRes.destroy();
                });
                resolve(true);
            });

            upstreamReq.on("timeout", () => {
                upstreamReq.destroy();
                resolve(false);
            });
            upstreamReq.on("error", () => resolve(false));
            upstreamReq.end();
        });
    }

    function requestBoxAdminCookie(base) {
        const cached = boxAdminSessions.get(base);
        if (cached?.cookie && Number(cached.expires_at || 0) > Date.now() + 60000) {
            return Promise.resolve(cached.cookie);
        }
        const loginUrl = new URL("/api/admin/auth/login", base);
        const body = Buffer.from(JSON.stringify({
            username: DEFAULT_BOX_ADMIN_USERNAME,
            password: DEFAULT_BOX_ADMIN_PASSWORD,
        }));
        return new Promise((resolve) => {
            const transport = loginUrl.protocol === "https:" ? https : http;
            const loginReq = transport.request(loginUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Content-Length": body.length,
                    Accept: "application/json",
                },
                timeout: 3000,
            }, (loginRes) => {
                loginRes.resume();
                if (Number(loginRes.statusCode || 0) < 200 || Number(loginRes.statusCode || 0) >= 300) {
                    resolve("");
                    return;
                }
                const setCookie = loginRes.headers["set-cookie"] || [];
                const rawCookie = (Array.isArray(setCookie) ? setCookie : [setCookie])
                    .map((item) => String(item).split(";")[0])
                    .find((item) => item.startsWith("gohome_admin_session="));
                if (!rawCookie) {
                    resolve("");
                    return;
                }
                boxAdminSessions.set(base, {
                    cookie: rawCookie,
                    expires_at: Date.now() + 11 * 60 * 60 * 1000,
                });
                resolve(rawCookie);
            });
            loginReq.on("timeout", () => {
                loginReq.destroy();
                resolve("");
            });
            loginReq.on("error", () => resolve(""));
            loginReq.write(body);
            loginReq.end();
        });
    }

    async function proxyCameraMjpeg(req, res, cameraId) {
        const target = cameraStreamProxyTarget(req, cameraId);
        if (!target) return false;

        const deviceUrl = applyStreamParams(new URL(`/api/v1/device/cameras/${target.localCameraId}/stream.mjpg`, target.base), req);
        const deviceProxied = await proxyMjpegRequest(req, res, deviceUrl, {
            Authorization: `Bearer ${target.token}`,
            "X-GoHome-Device-Token": target.token,
        }, {
            "X-GoHome-Device-Base": target.base,
            "X-GoHome-Local-Camera-Id": String(target.localCameraId),
            "X-GoHome-Proxy-Mode": "device-token",
        });
        if (deviceProxied || res.headersSent) return deviceProxied;

        const adminCookie = await requestBoxAdminCookie(target.base);
        if (!adminCookie) return false;
        const adminUrl = applyStreamParams(new URL(`/api/cameras/${target.localCameraId}/stream.mjpg`, target.base), req);
        return proxyMjpegRequest(req, res, adminUrl, { Cookie: adminCookie }, {
            "X-GoHome-Device-Base": target.base,
            "X-GoHome-Local-Camera-Id": String(target.localCameraId),
            "X-GoHome-Proxy-Mode": "admin-cookie",
        });
    }

    async function serveCameraMjpeg(req, res, cameraId) {
        if (!requireApp(req, res)) return;
        if (await proxyCameraMjpeg(req, res, cameraId)) return;
        writeEmptyMjpeg(res);
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
        await store.save();
        write(res, 200, { ok: true, asset });
    }

    async function handleDeviceEvent(req, res) {
        if (!requireDevice(req, res)) return;
        const payload = await parseJsonBody(req);
        const camera = upsertCamera(payload);
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
            room: String(payload.room || camera?.room || ""),
            camera_id: camera?.id || payload.camera_id || null,
            camera_name: String(payload.payload?.camera_name || camera?.name || ""),
            snapshot_path: String(payload.snapshot_path || asset?.snapshot_path || "").replace(/^\/+/, ""),
            media_asset_id: asset?.id || null,
            occurred_at: String(payload.occurred_at || nowIso()),
            acknowledged: false,
            resolution: "",
            payload: {
                ...(payload.payload || {}),
                edge_camera_id: payload.camera_id || null,
                app_camera_id: camera?.id || payload.camera_id || null,
            },
            created_at: nowIso(),
            updated_at: nowIso(),
        };
        const existing = store.db.events.find((item) => item.idempotency_key === event.idempotency_key);
        if (existing) {
            write(res, 200, { ok: true, event: publicEvent(existing), media_asset: asset || null, duplicate: true });
            return;
        }
        store.db.events.push(event);
        await store.save();
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
        await store.save();
        write(res, 200, { ok: true, server_time: nowIso(), config: {} });
    }

    function cameraSyncStatusFromReport(report) {
        const syncStatus = String(report.sync_status || "").trim();
        if (syncStatus) return syncStatus;
        if (report.applied === false) return "edge_error";
        const status = String(report.status || "").toLowerCase();
        if (["online", "configured", "disabled", "synced"].includes(status)) return "synced";
        if (["offline", "error", "failed"].includes(status)) return "edge_error";
        if (report.last_error) return "edge_error";
        return "edge_reported";
    }

    async function handleDeviceSync(req, res) {
        if (!requireDevice(req, res)) return;
        const payload = await parseJsonBody(req);
        const receivedAt = nowIso();
        const issuedToken = store.db.device_tokens.find((item) => item.token === tokenFrom(req) && item.status === "active");
        const deviceId = String(payload.device_id || issuedToken?.device_id || currentEdgeDeviceId() || "edge-local");
        const reportedStatus = payload.status && typeof payload.status === "object" ? payload.status : {};
        const existingDevice = store.db.devices[deviceId] || {};
        const runtime = payload.runtime || existingDevice.runtime || {};
        const deviceLanUrl = normalizeBaseUrl(runtime.lan_url || payload.lan_url || existingDevice.lan_url || inferredDeviceBaseUrl(req, runtime));
        const deviceServiceUrl = normalizeBaseUrl(runtime.service_url || payload.service_url || existingDevice.service_url || deviceLanUrl);
        const detectorBackend = String(payload.detector_backend || runtime.detector_backend || existingDevice.detector_backend || "").trim();
        const yoloModel = String(payload.yolo_model || runtime.yolo_model || existingDevice.yolo_model || "").trim();
        const yoloImgsz = normalizeNumber(payload.yolo_imgsz ?? runtime.yolo_imgsz ?? existingDevice.yolo_imgsz, null);

        if (issuedToken) {
            issuedToken.device_id = deviceId;
            issuedToken.last_heartbeat_at = receivedAt;
        }

        store.db.devices[deviceId] = {
            ...existingDevice,
            id: deviceId,
            device_id: deviceId,
            name: payload.device_name || existingDevice.name || "回家盒子",
            status: String(reportedStatus.status || payload.device_status || "online"),
            worker_running: payload.worker_running ?? existingDevice.worker_running ?? null,
            lan_url: deviceLanUrl || existingDevice.lan_url || "",
            service_url: deviceServiceUrl || existingDevice.service_url || "",
            last_seen_at: receivedAt,
            last_sync_at: receivedAt,
            reported_config_version: String(payload.config_version || payload.applied_config_version || ""),
            app_version: String(payload.app_version || existingDevice.app_version || ""),
            model_version: String(payload.model_version || existingDevice.model_version || ""),
            detector_backend: detectorBackend || existingDevice.detector_backend || "",
            yolo_model: yoloModel || existingDevice.yolo_model || "",
            yolo_imgsz: yoloImgsz ?? existingDevice.yolo_imgsz ?? null,
            runtime,
            sync_status: String(reportedStatus.sync_status || payload.sync_status || "reported"),
            last_error: String(reportedStatus.last_error || payload.last_error || ""),
            updated_at: receivedAt,
        };

        const cameraReports = Array.isArray(payload.cameras) ? payload.cameras : [];
        const updatedCameras = [];
        for (const report of cameraReports) {
            const rawCameraId = report.camera_id ?? report.id;
            if (rawCameraId === null || rawCameraId === undefined || rawCameraId === "") continue;
            const cameraKey = String(rawCameraId);
            const reportedStatus = String(report.status || "").toLowerCase();
            if (report.deleted === true || ["deleted", "removed"].includes(reportedStatus)) {
                continue;
            }
            const existingById = store.db.cameras[cameraKey] || null;
            const localMatch = (!existingById || !isAppConfiguredCamera(existingById))
                ? findAppCameraByLocalReport(report, rawCameraId, deviceId)
                : null;
            const targetKey = String(localMatch?.id || rawCameraId);
            const existing = localMatch || existingById || {};
            const reportLocalCameraId = report.local_camera_id ?? existing.local_camera_id ?? (!isAppConfiguredCamera(existing) ? rawCameraId : null);
            const camera = {
                ...existing,
                id: existing.id || rawCameraId,
                family_id: existing.family_id || issuedToken?.family_id || store.db.families[0]?.id || 1,
                device_id: String(report.device_id || existing.device_id || deviceId),
                name: String(existing.name || report.name || `摄像头 ${rawCameraId}`),
                room: String(existing.room || report.room || ""),
                enabled: "enabled" in existing ? normalizeBool(existing.enabled) : normalizeBool(report.enabled ?? true),
                status: String(report.status || existing.status || "edge_reported"),
                sync_status: cameraSyncStatusFromReport(report),
                source: String(existing.source || "edge_reported"),
                stream_url: existing.stream_url || String(report.stream_url || ""),
                username: existing.username || report.username || "",
                password: existing.password || null,
                local_camera_id: reportLocalCameraId,
                last_error: String(report.last_error || ""),
                last_seen_at: report.last_seen_at || (String(report.status || "").toLowerCase() === "online" ? receivedAt : existing.last_seen_at || null),
                edge_reported_at: receivedAt,
                created_at: existing.created_at || receivedAt,
                updated_at: existing.updated_at || receivedAt,
            };
            store.db.cameras[targetKey] = camera;
            updatedCameras.push(publicCamera(camera));
        }

        await store.save();
        write(res, 200, {
            ok: true,
            device_id: deviceId,
            received_at: receivedAt,
            reported_config_version: store.db.devices[deviceId].reported_config_version,
            current_config_version: cameraConfigVersion(),
            updated_cameras: updatedCameras,
            config: deviceConfigPayload(),
        });
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
                    store: store.kind || "json",
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
                    await store.save();
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
                    await store.save();
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
                await store.save();
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
                await store.save();
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
                await store.save();
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
                    cameras: appConfigCameras().map(publicCamera),
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
                await store.save();
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
                    token_hash: sha256(token),
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
                await store.save();
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
                await store.save();
                write(res, 200, { ok: true, device: store.db.devices[deviceId], auth: publicDeviceAuthStatus() });
                return;
            }

            if (req.method === "GET" && (pathname === "/api/app/device" || pathname === "/api/device")) {
                if (!requireApp(req, res)) return;
                const device = Object.values(store.db.devices)[0] || {};
                write(res, 200, {
                    device_id: currentEdgeDeviceId(),
                    name: device.name || "回家盒子",
                    worker_running: Boolean(device.worker_running),
                    detector_backend: device.detector_backend || "basic",
                    yolo_model: device.yolo_model || "",
                    yolo_imgsz: device.yolo_imgsz || null,
                    upload_agent: { configured: true, app_server_base_url: true },
                });
                return;
            }

            if (req.method === "GET" && (pathname === "/api/app/cameras" || pathname === "/api/cameras")) {
                if (!requireApp(req, res)) return;
                write(res, 200, appConfigCameras().map(publicCamera));
                return;
            }

            if (req.method === "POST" && pathname === "/api/cameras") {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req);
                const camera = normalizeCameraPayload(payload);
                store.db.cameras[String(camera.id)] = camera;
                await store.save();
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
                await store.save();
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
                await store.save();
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
                await store.save();
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

            if (req.method === "POST" && (pathname === "/api/v1/video/sessions" || pathname === "/api/app/playback-sessions")) {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req);
                const ticket = stableId("play-");
                playbackTickets.set(ticket, { payload, expires_at: Date.now() + 120000 });
                write(res, 200, { ticket, expires_at: new Date(Date.now() + 120000).toISOString() });
                return;
            }

            const streamMatch = pathname.match(/^\/api\/v1\/video\/cameras\/([^/]+)\/stream\.mjpg$/)
                || pathname.match(/^\/api\/app\/cameras\/([^/]+)\/stream\.mjpg$/);
            if (req.method === "GET" && streamMatch) {
                await serveCameraMjpeg(req, res, streamMatch[1]);
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

            if (req.method === "POST" && pathname === "/api/v1/device/sync") {
                await handleDeviceSync(req, res);
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
                await store.save();
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

            const carePreferenceMatch = pathname.match(/^\/api\/v1\/families\/([^/]+)\/care-preferences$/);
            if (carePreferenceMatch && req.method === "GET") {
                if (!requireApp(req, res)) return;
                write(res, 200, publicCarePreferences(carePreferences(carePreferenceMatch[1])));
                return;
            }

            if (carePreferenceMatch && req.method === "PUT") {
                if (!requireApp(req, res)) return;
                const familyId = Number(carePreferenceMatch[1]);
                if (!selectedFamily(familyId)) {
                    writeError(res, 404, "family not found");
                    return;
                }
                const payload = await parseJsonBody(req);
                const existing = carePreferences(familyId);
                store.db.care_preferences[String(familyId)] = publicCarePreferences({
                    ...existing,
                    frequency: String(payload.frequency || existing.frequency || "daily"),
                    quiet_hours: payload.quiet_hours && typeof payload.quiet_hours === "object" ? payload.quiet_hours : existing.quiet_hours,
                    interests: Array.isArray(payload.interests) ? payload.interests.map(String).filter(Boolean).slice(0, 20) : existing.interests,
                    text_model_enabled: "text_model_enabled" in payload ? normalizeBool(payload.text_model_enabled) : existing.text_model_enabled,
                    image_generation_enabled: "image_generation_enabled" in payload ? normalizeBool(payload.image_generation_enabled) : existing.image_generation_enabled,
                    image_provider: String(payload.image_provider || existing.image_provider || ""),
                    image_model: String(payload.image_model || existing.image_model || ""),
                    content_recommendations_enabled: "content_recommendations_enabled" in payload ? normalizeBool(payload.content_recommendations_enabled) : existing.content_recommendations_enabled,
                    content_sources_enabled: "content_sources_enabled" in payload ? normalizeBool(payload.content_sources_enabled) : existing.content_sources_enabled,
                    updated_at: nowIso(),
                });
                await store.save();
                write(res, 200, store.db.care_preferences[String(familyId)]);
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/app/care-cards/today") {
                if (!requireApp(req, res)) return;
                const familyId = normalizeNumber(url.searchParams.get("family_id"), store.db.families[0]?.id || 1);
                const card = generateCareCard(familyId);
                await store.save();
                write(res, 200, publicCareCard(card));
                return;
            }

            if (req.method === "POST" && pathname === "/api/v1/internal/care-cards/generate") {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req);
                const familyId = normalizeNumber(payload.family_id, store.db.families[0]?.id || 1);
                const card = generateCareCard(familyId, { force: normalizeBool(payload.force) });
                await store.save();
                write(res, 200, { ok: true, card: publicCareCard(card) });
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/model-providers") {
                if (!requireApp(req, res)) return;
                write(res, 200, modelProviders().map(publicModelProvider));
                return;
            }

            const modelProviderMatch = pathname.match(/^\/api\/v1\/model-providers\/([^/]+)$/);
            if (modelProviderMatch && req.method === "PUT") {
                if (!requireApp(req, res)) return;
                const providerId = decodeURIComponent(modelProviderMatch[1]);
                const payload = await parseJsonBody(req);
                const existingStored = store.db.model_providers.find((item) => item.provider_id === providerId) || {};
                const existing = modelProviders().find((item) => item.provider_id === providerId) || existingStored;
                let apiKeySecretRef = String(
                    "api_key_secret_ref" in payload ? payload.api_key_secret_ref : (existingStored.api_key_secret_ref || existing.api_key_secret_ref || "")
                ).trim();
                if ("api_key" in payload && String(payload.api_key || "").trim()) {
                    apiKeySecretRef = setLocalProviderSecret(providerId, payload.api_key);
                }
                const clearApiKey = normalizeBool(payload.clear_api_key);
                if (clearApiKey) {
                    clearLocalProviderSecret(providerId);
                    if (apiKeySecretRef === localProviderSecretRef(providerId)) apiKeySecretRef = "";
                }
                const next = {
                    provider_id: providerId,
                    provider: String(payload.provider || existing.provider || ""),
                    model: String(payload.model || existing.model || ""),
                    purpose: String(payload.purpose || existing.purpose || "care_text"),
                    enabled: "enabled" in payload ? normalizeBool(payload.enabled) : Boolean(existing.enabled),
                    configured: Boolean(existing.configured),
                    api_key_set: Boolean(!clearApiKey && (apiKeySecretRef || existingStored.api_key_set)),
                    api_key_secret_ref: apiKeySecretRef,
                    created_at: existingStored.created_at || nowIso(),
                    updated_at: nowIso(),
                };
                const publicNext = publicModelProvider(next);
                next.configured = publicNext.configured;
                next.api_key_set = publicNext.api_key_set && publicNext.secret_mode !== "env";
                const index = store.db.model_providers.findIndex((item) => item.provider_id === providerId);
                if (index >= 0) store.db.model_providers[index] = next;
                else store.db.model_providers.push(next);
                await store.save();
                write(res, 200, publicModelProvider(next));
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/ops/service-config") {
                if (!requireApp(req, res)) return;
                write(res, 200, {
                    ok: true,
                    service: "gohome-local-app-server",
                    store: store.kind || "json",
                    app_server_base_url: process.env.GOHOME_APP_SERVER_BASE_URL || `http://localhost:${DEFAULT_PORT}`,
                    model_providers: modelProviders().map(publicModelProvider),
                    secret_policy: {
                        local: "server_secret_file",
                        cloud: "secret_manager_or_kms",
                        database: "secret_ref_only",
                    },
                    generated_at: nowIso(),
                });
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

function appServerStoreKind(options = {}) {
    return String(options.storeKind || DEFAULT_STORE_KIND || "json").trim().toLowerCase();
}

function shouldUsePostgresStore(options = {}) {
    const storeKind = appServerStoreKind(options);
    return storeKind === "postgres" || storeKind === "pg";
}

function localJsonDbPath(rootDir, dataDir) {
    return path.join(dataDir || path.join(rootDir, "data", "app-server"), "db.json");
}

function initialDbFromJsonFallback(filePath) {
    return normalizeDb(fs.existsSync(filePath)
        ? { ...createDefaultDb(), ...safeJsonParse(fs.readFileSync(filePath, "utf8"), {}) }
        : createDefaultDb());
}

async function createLocalAppServerAsync(options = {}) {
    if (!shouldUsePostgresStore(options)) {
        return createLocalAppServer(options);
    }
    const rootDir = path.resolve(options.rootDir || process.cwd());
    const dataDir = path.resolve(options.dataDir || process.env.GOHOME_APP_SERVER_DATA_DIR || path.join(rootDir, "data", "app-server"));
    const databaseUrl = String(options.databaseUrl || process.env.GOHOME_DATABASE_URL || process.env.DATABASE_URL || "").trim();
    if (!databaseUrl) {
        throw new Error("GOHOME_DATABASE_URL is required when GOHOME_APP_STORE=postgres");
    }
    const ssl = process.env.GOHOME_DATABASE_SSL === "1" || process.env.GOHOME_DATABASE_SSL === "true"
        ? { rejectUnauthorized: false }
        : null;
    const { createPostgresStore } = require("./postgres-store");
    const store = await createPostgresStore({
        databaseUrl,
        ssl,
        initialDb: initialDbFromJsonFallback(localJsonDbPath(rootDir, dataDir)),
        normalizeDb,
    });
    return createLocalAppServer({ ...options, rootDir, dataDir, store });
}

if (require.main === module) {
    createLocalAppServerAsync({ rootDir: path.resolve(__dirname, "..") })
        .then((app) => {
            app.server.listen(DEFAULT_PORT, DEFAULT_HOST, () => {
                console.log(`GoHome local App server listening on http://${DEFAULT_HOST}:${DEFAULT_PORT}`);
                console.log(`Store: ${app.store.kind || "json"}`);
                console.log(`App token: ${app.appToken}`);
                console.log(`Device token: ${app.deviceToken}`);
                console.log(`Data dir: ${app.dataDir}`);
            });
        })
        .catch((error) => {
            console.error(error.message || error);
            process.exit(1);
        });
}

module.exports = { createLocalAppServer, createLocalAppServerAsync, createDefaultDb, normalizeDb };
