#!/usr/bin/env node
"use strict";

const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const https = require("https");
const path = require("path");
const { URL } = require("url");

function parseEnvValue(raw) {
    let value = String(raw || "").trim();
    if (!value) return "";
    if (value.length >= 2 && value[0] === value[value.length - 1] && ["\"", "'"].includes(value[0])) {
        const inner = value.slice(1, -1);
        return value[0] === "\"" ? inner.replace(/\\n/g, "\n").replace(/\\"/g, "\"").replace(/\\\\/g, "\\") : inner;
    }
    const commentIndex = value.indexOf(" #");
    if (commentIndex >= 0) value = value.slice(0, commentIndex).trim();
    return value;
}

function loadEnvFile(filePath, protectedKeys) {
    if (!fs.existsSync(filePath)) return false;
    const loadedKeys = new Set();
    for (const rawLine of fs.readFileSync(filePath, "utf8").split(/\r?\n/)) {
        let line = rawLine.trim();
        if (!line || line.startsWith("#")) continue;
        if (line.startsWith("export ")) line = line.slice(7).trim();
        const equalsIndex = line.indexOf("=");
        if (equalsIndex <= 0) continue;
        const key = line.slice(0, equalsIndex).trim();
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) continue;
        if (protectedKeys.has(key)) continue;
        process.env[key] = parseEnvValue(line.slice(equalsIndex + 1));
        loadedKeys.add(key);
    }
    for (const key of loadedKeys) protectedKeys.delete(key);
    return true;
}

function loadLocalEnv(rootDir = path.resolve(__dirname, "..")) {
    const protectedKeys = new Set(Object.keys(process.env));
    const loaded = [];
    for (const name of [".env", ".env.local"]) {
        const filePath = path.join(rootDir, name);
        if (loadEnvFile(filePath, protectedKeys)) loaded.push(filePath);
    }
    return loaded;
}

const LOADED_ENV_FILES = loadLocalEnv();

const DEFAULT_PORT = Number(process.env.GOHOME_APP_SERVER_PORT || 8788);
const DEFAULT_HOST = process.env.GOHOME_APP_SERVER_HOST || "0.0.0.0";
const DEFAULT_DEVICE_TOKEN = process.env.GOHOME_DEVICE_API_TOKEN || "gohome-local-device-token";
const DEFAULT_APP_TOKEN = process.env.GOHOME_APP_TOKEN || "gohome-local-app-token";
const DEFAULT_OPS_TOKEN = process.env.GOHOME_OPS_TOKEN || "";
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
    const opsToken = String(options.opsToken || DEFAULT_OPS_TOKEN);
    const playbackTickets = new Map();
    const boxAdminSessions = new Map();

    ensureDir(mediaDir);

    const defaultCareTextPrompt = [
        "你是回家 App 的亲情关怀卡片生成助手。",
        "请基于老人资料、日历、天气、热点信息、设备状态、摄像头状态和最近事件生成一张每日关怀卡片。",
        "输出必须温暖、克制、可解释，不替代安全告警，不编造没有事实依据的老人行为。",
        "返回 JSON：title、body、facts、suggested_actions、tone、image_brief。",
    ].join("\n");

    const defaultCareImagePrompt = [
        "生成一张 4:7 竖版温馨可爱漫画图文卡片。",
        "画面用于家属端每日亲情关怀，不是告警证据。",
        "风格：柔和、清爽、适合中文移动端展示。",
        "画面需要包含卡片标题和一两句简短中文关怀文字，文字必须清晰可读。",
        "不要出现监控感、恐慌感、医疗诊断感或真实老人肖像。",
    ].join("\n");

    function envFirst(keys, fallback = "") {
        for (const key of keys) {
            const value = String(process.env[key] || "").trim();
            if (value) return value;
        }
        return fallback;
    }

    function normalizeModelEndpoint(value, defaultPath = "") {
        const raw = String(value || "").trim().replace(/\/+$/, "");
        if (!raw) return "";
        if (!defaultPath || raw.endsWith(defaultPath)) return raw;
        if (/\/v\d+$/i.test(raw)) return `${raw}${defaultPath}`;
        return raw;
    }

    function multimodalRuntimeConfig() {
        return {
            capability_id: "multimodal-language",
            api_key: envFirst(["GOHOME_MULTIMODAL_API_KEY", "GOHOME_TEXT_MODEL_API_KEY", "OPENAI_API_KEY"]),
            base_url: normalizeModelEndpoint(
                envFirst(["GOHOME_MULTIMODAL_BASE_URL", "GOHOME_TEXT_MODEL_BASE_URL", "OPENAI_BASE_URL"]),
                "/chat/completions"
            ),
            model: envFirst(["GOHOME_MULTIMODAL_MODEL", "GOHOME_TEXT_MODEL", "OPENAI_MODEL"]),
            prompt: envFirst(["GOHOME_CARE_CARD_PROMPT"], defaultCareTextPrompt),
            prompt_source: process.env.GOHOME_CARE_CARD_PROMPT ? "env" : "default",
        };
    }

    function imageRuntimeConfig() {
        return {
            capability_id: "care-card-image",
            api_key: envFirst(["GOHOME_IMAGE_API_KEY", "GOHOME_WAN_API_KEY", "DASHSCOPE_API_KEY", "WAN_API_KEY"]),
            base_url: normalizeModelEndpoint(
                envFirst(["GOHOME_IMAGE_BASE_URL", "GOHOME_WAN_BASE_URL", "DASHSCOPE_BASE_URL", "WAN_BASE_URL"])
            ),
            model: envFirst(["GOHOME_IMAGE_MODEL", "GOHOME_WAN_MODEL", "WAN_MODEL"], "wan2.7-image"),
            prompt: envFirst(["GOHOME_CARE_IMAGE_PROMPT"], defaultCareImagePrompt),
            prompt_source: process.env.GOHOME_CARE_IMAGE_PROMPT ? "env" : "default",
        };
    }

    function modelCallsEnabled() {
        const value = String(process.env.GOHOME_CARE_MODEL_CALLS || "1").trim().toLowerCase();
        return !["0", "false", "off", "disabled"].includes(value);
    }

    function careImageCallsEnabled() {
        const value = String(process.env.GOHOME_CARE_IMAGE_CALLS || process.env.GOHOME_CARE_MODEL_CALLS || "1").trim().toLowerCase();
        return !["0", "false", "off", "disabled"].includes(value);
    }

    function imageRuntimeConfigured(runtime = imageRuntimeConfig()) {
        return Boolean(runtime.base_url && runtime.api_key && runtime.model);
    }

    function careImageRequested(preferences = {}) {
        return Boolean(preferences.image_generation_enabled || imageRuntimeConfigured());
    }

    function modelRequestTimeoutMs() {
        const value = Number(process.env.GOHOME_MODEL_REQUEST_TIMEOUT_MS || 60000);
        return Number.isFinite(value) && value >= 5000 ? value : 60000;
    }

    function careImageSize() {
        const value = String(process.env.GOHOME_CARE_IMAGE_SIZE || "1024*1792").trim();
        return /^\d{3,4}\*\d{3,4}$/.test(value) ? value : "1024*1792";
    }

    function careImagePollIntervalMs() {
        const value = Number(process.env.GOHOME_CARE_IMAGE_POLL_INTERVAL_MS || 2000);
        return Number.isFinite(value) && value >= 500 ? value : 2000;
    }

    function careImageMaxPolls() {
        const value = Number(process.env.GOHOME_CARE_IMAGE_MAX_POLLS || 30);
        return Number.isFinite(value) && value >= 1 ? value : 30;
    }

    function modelCapabilities() {
        const multimodal = multimodalRuntimeConfig();
        const image = imageRuntimeConfig();
        return [
            {
                capability_id: "multimodal-language",
                name: "多模态语言模型",
                type: "multimodal_language",
                scope: "care_card_generation",
                configured: Boolean(multimodal.base_url && multimodal.api_key && multimodal.model),
                enabled: Boolean(multimodal.base_url && multimodal.api_key && multimodal.model),
                base_url_set: Boolean(multimodal.base_url),
                api_key_set: Boolean(multimodal.api_key),
                model: multimodal.model,
                purpose_label: "每日关怀内容生成",
                prompt: multimodal.prompt,
                prompt_source: multimodal.prompt_source,
                env_keys: {
                    base_url: ["GOHOME_MULTIMODAL_BASE_URL", "GOHOME_TEXT_MODEL_BASE_URL", "OPENAI_BASE_URL"],
                    api_key: ["GOHOME_MULTIMODAL_API_KEY", "GOHOME_TEXT_MODEL_API_KEY", "OPENAI_API_KEY"],
                    model: ["GOHOME_MULTIMODAL_MODEL", "GOHOME_TEXT_MODEL", "OPENAI_MODEL"],
                    prompt: ["GOHOME_CARE_CARD_PROMPT"],
                },
                output_contract: "CareCard JSON: title/body/facts/actions/tone/image_brief",
            },
            {
                capability_id: "care-card-image",
                name: "生图模型",
                type: "image_generation",
                scope: "care_card_image_4x7",
                configured: Boolean(image.base_url && image.api_key && image.model),
                enabled: Boolean(image.base_url && image.api_key && image.model),
                base_url_set: Boolean(image.base_url),
                api_key_set: Boolean(image.api_key),
                model: image.model,
                purpose_label: "4:7 图文卡片生成",
                aspect_ratio: "4:7",
                prompt: image.prompt,
                prompt_source: image.prompt_source,
                env_keys: {
                    base_url: ["GOHOME_IMAGE_BASE_URL", "GOHOME_WAN_BASE_URL", "DASHSCOPE_BASE_URL", "WAN_BASE_URL"],
                    api_key: ["GOHOME_IMAGE_API_KEY", "GOHOME_WAN_API_KEY", "DASHSCOPE_API_KEY", "WAN_API_KEY"],
                    model: ["GOHOME_IMAGE_MODEL", "GOHOME_WAN_MODEL", "WAN_MODEL"],
                    prompt: ["GOHOME_CARE_IMAGE_PROMPT"],
                },
                output_contract: "4:7 non-evidence illustrated care card image with readable Chinese text",
            },
        ];
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

    function isLocalRequest(req) {
        const address = normalizeRemoteAddress(req.socket?.remoteAddress || "");
        return address === "127.0.0.1" || address === "localhost";
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

    function requireOps(req, res) {
        const url = new URL(req.url, "http://local");
        const token = tokenFrom(req) || url.searchParams.get("ops_token") || "";
        if (opsToken && token === opsToken) return true;
        if (!opsToken && isLocalRequest(req)) return true;
        writeError(res, 403, "后台配置仅限平台运维访问。");
        return false;
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

    function defaultCareSchedule() {
        return {
            enabled: true,
            delivery_time: "08:30",
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
            interest_topics: ["养生", "天气", "戏曲", "家常"],
            message_focus: "用轻松自然的语气提醒今天家里状态，顺带给一个适合打电话时聊的话题。",
            visit_reminder: {
                enabled: true,
                threshold_days: 14,
                location_tracking_enabled: false,
                last_visit_at: "",
            },
            anniversaries: [],
            updated_at: nowIso(),
        };
    }

    function normalizeTimeOfDay(value, fallback = "08:30") {
        const raw = String(value || "").trim();
        const match = raw.match(/^(\d{2}):(\d{2})$/);
        if (!match) return fallback;
        const hours = Number(match[1]);
        const minutes = Number(match[2]);
        return hours >= 0 && hours <= 23 && minutes >= 0 && minutes <= 59 ? raw : fallback;
    }

    function normalizeStringList(value, fallback = [], limit = 20) {
        const source = Array.isArray(value) ? value : fallback;
        return [...new Set(source.map((item) => String(item || "").trim()).filter(Boolean))].slice(0, limit);
    }

    function normalizeCareSchedule(value = {}) {
        const defaults = defaultCareSchedule();
        const input = value && typeof value === "object" ? value : {};
        const contentTypes = input.content_types && typeof input.content_types === "object" ? input.content_types : {};
        const visitReminder = input.visit_reminder && typeof input.visit_reminder === "object" ? input.visit_reminder : {};
        return {
            enabled: "enabled" in input ? normalizeBool(input.enabled) : defaults.enabled,
            delivery_time: normalizeTimeOfDay(input.delivery_time, defaults.delivery_time),
            timezone: String(input.timezone || defaults.timezone),
            channels: normalizeStringList(input.channels, defaults.channels, 6),
            content_types: {
                home_status: "home_status" in contentTypes ? normalizeBool(contentTypes.home_status) : defaults.content_types.home_status,
                elder_interest_topics: "elder_interest_topics" in contentTypes ? normalizeBool(contentTypes.elder_interest_topics) : defaults.content_types.elder_interest_topics,
                health_tips: "health_tips" in contentTypes ? normalizeBool(contentTypes.health_tips) : defaults.content_types.health_tips,
                weather: "weather" in contentTypes ? normalizeBool(contentTypes.weather) : defaults.content_types.weather,
                holidays: "holidays" in contentTypes ? normalizeBool(contentTypes.holidays) : defaults.content_types.holidays,
                anniversaries: "anniversaries" in contentTypes ? normalizeBool(contentTypes.anniversaries) : defaults.content_types.anniversaries,
                visit_reminder: "visit_reminder" in contentTypes ? normalizeBool(contentTypes.visit_reminder) : defaults.content_types.visit_reminder,
            },
            interest_topics: normalizeStringList(input.interest_topics, defaults.interest_topics, 20),
            message_focus: String(input.message_focus || defaults.message_focus).trim().slice(0, 400),
            visit_reminder: {
                enabled: "enabled" in visitReminder ? normalizeBool(visitReminder.enabled) : defaults.visit_reminder.enabled,
                threshold_days: Math.min(90, Math.max(1, normalizeNumber(visitReminder.threshold_days, defaults.visit_reminder.threshold_days))),
                location_tracking_enabled: normalizeBool(visitReminder.location_tracking_enabled),
                last_visit_at: /^\d{4}-\d{2}-\d{2}$/.test(String(visitReminder.last_visit_at || ""))
                    ? String(visitReminder.last_visit_at)
                    : "",
            },
            anniversaries: (Array.isArray(input.anniversaries) ? input.anniversaries : [])
                .map((item) => ({
                    label: String(item?.label || "").trim(),
                    date: String(item?.date || "").trim(),
                    repeat: String(item?.repeat || "yearly").trim() || "yearly",
                }))
                .filter((item) => item.label && /^\d{4}-\d{2}-\d{2}$/.test(item.date))
                .slice(0, 20),
            updated_at: nowIso(),
        };
    }

    function normalizeCareMetadata(metadata = {}) {
        const source = metadata && typeof metadata === "object" ? metadata : {};
        return {
            ...source,
            care_card_schedule: normalizeCareSchedule(source.care_card_schedule),
        };
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
            metadata: normalizeCareMetadata(),
            updated_at: nowIso(),
        };
    }

    function carePreferences(familyId) {
        const key = String(familyId || store.db.families[0]?.id || 1);
        const preferences = store.db.care_preferences[key] || defaultCarePreferences(key);
        preferences.metadata = normalizeCareMetadata(preferences.metadata || {});
        return preferences;
    }

    function publicCarePreferences(preferences) {
        return {
            ...preferences,
            content_sources_enabled: Boolean(preferences.content_sources_enabled),
            content_recommendations_enabled: Boolean(preferences.content_recommendations_enabled),
            image_generation_enabled: Boolean(preferences.image_generation_enabled),
            text_model_enabled: Boolean(preferences.text_model_enabled),
            metadata: normalizeCareMetadata(preferences.metadata || {}),
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

    function modelJob(payload) {
        const timestamp = nowIso();
        return {
            id: String(store.nextId("model_generation_job")),
            family_id: String(payload.family_id || ""),
            provider_id: "",
            purpose: String(payload.purpose || "care_text"),
            model: String(payload.model || ""),
            prompt_version: String(payload.prompt_version || ""),
            input_hash: String(payload.input_hash || ""),
            output_status: String(payload.output_status || "pending"),
            request_payload: payload.request_payload && typeof payload.request_payload === "object" ? payload.request_payload : {},
            response_payload: payload.response_payload && typeof payload.response_payload === "object" ? payload.response_payload : {},
            error_message: String(payload.error_message || ""),
            metadata: payload.metadata && typeof payload.metadata === "object" ? payload.metadata : {},
            created_at: timestamp,
            updated_at: timestamp,
        };
    }

    function updateModelJob(job, patch) {
        Object.assign(job, patch, { updated_at: nowIso() });
        return job;
    }

    function recentCalendarEvents(familyId, elderId = "elder_primary") {
        const now = Date.now();
        const horizon = now + 14 * 24 * 60 * 60 * 1000;
        return store.db.calendar_events
            .filter((event) => Number(event.family_id) === Number(familyId) && (!elderId || event.elder_id === elderId))
            .filter((event) => {
                const timestamp = Date.parse(event.starts_at || "");
                return Number.isFinite(timestamp) && timestamp >= now - 24 * 60 * 60 * 1000 && timestamp <= horizon;
            })
            .slice(0, 8)
            .map((event) => ({
                title: event.title,
                starts_at: event.starts_at,
                note: event.note || "",
            }));
    }

    function careCardModelContext(familyId, parts) {
        const family = selectedFamily(familyId) || store.db.families[0] || {};
        const preferences = parts.preferences || carePreferences(familyId);
        const profile = parts.profile || defaultElderProfile(familyId, preferences.elder_id || "elder_primary");
        const cameras = Array.isArray(parts.cameras) ? parts.cameras : appConfigCameras();
        const device = parts.device || Object.values(store.db.devices)[0] || {};
        return {
            generated_at: nowIso(),
            card_date: dateKeyShanghai(),
            locale: "zh-CN",
            family: {
                id: family.id || familyId,
                name: family.name || "默认家庭",
            },
            elder: {
                id: profile.elder_id || profile.id || "elder_primary",
                display_name: profile.display_name || "家人",
                relationship: profile.relationship || "",
                city: profile.city || "杭州",
                health_notes: profile.health_notes || "",
            },
            preferences: {
                frequency: preferences.frequency || "daily",
                interests: Array.isArray(preferences.interests) ? preferences.interests.slice(0, 12) : [],
                content_recommendations_enabled: Boolean(preferences.content_recommendations_enabled),
                image_generation_enabled: Boolean(preferences.image_generation_enabled),
                care_card_schedule: preferences.metadata?.care_card_schedule || defaultCareSchedule(),
            },
            facts: Array.isArray(parts.facts) ? parts.facts : [],
            device: {
                device_id: device.device_id || device.id || currentEdgeDeviceId(),
                name: device.name || "回家盒子",
                status: device.status || "",
                last_seen_at: device.last_seen_at || null,
            },
            cameras: cameras.slice(0, 8).map((camera) => ({
                id: camera.id,
                name: camera.name || "",
                room: camera.room || "",
                status: camera.status || "",
                last_seen_at: camera.last_seen_at || camera.updated_at || null,
            })),
            recent_events: (Array.isArray(parts.openEvents) ? parts.openEvents : []).slice(0, 8).map((event) => ({
                id: event.id,
                level: event.level,
                type: event.event_type,
                summary: event.summary,
                room: event.room || "",
                occurred_at: event.occurred_at || event.created_at,
                acknowledged: Boolean(event.acknowledged),
            })),
            critical_event_count: Array.isArray(parts.criticalEvents) ? parts.criticalEvents.length : 0,
            calendar_events: recentCalendarEvents(familyId, profile.elder_id || profile.id || "elder_primary"),
            weather: {
                city: profile.city || "杭州",
                condition: "多云",
                temperature_c: 24,
                advice: "环境舒适，适合午休。下午注意通风。",
            },
        };
    }

    function extractJsonObject(text) {
        const raw = String(text || "").trim();
        if (!raw) return null;
        try {
            return JSON.parse(raw);
        } catch (_error) {
            // Continue with fenced or embedded JSON extraction.
        }
        const fenced = raw.match(/```(?:json)?\s*([\s\S]*?)```/i);
        if (fenced) {
            try {
                return JSON.parse(fenced[1].trim());
            } catch (_error) {
                // Continue with brace extraction.
            }
        }
        const start = raw.indexOf("{");
        const end = raw.lastIndexOf("}");
        if (start >= 0 && end > start) {
            try {
                return JSON.parse(raw.slice(start, end + 1));
            } catch (_error) {
                return null;
            }
        }
        return null;
    }

    function sanitizeModelCareCard(parsed) {
        if (!parsed || typeof parsed !== "object") return null;
        const title = String(parsed.title || "").trim().slice(0, 40);
        const body = String(parsed.body || "").trim().slice(0, 280);
        if (!title || !body) return null;
        const facts = Array.isArray(parsed.facts)
            ? parsed.facts.map((item) => String(item || "").trim()).filter(Boolean).slice(0, 5)
            : [];
        const suggestedActions = Array.isArray(parsed.suggested_actions)
            ? parsed.suggested_actions.map((item) => String(item || "").trim()).filter(Boolean).slice(0, 3)
            : [];
        return {
            title,
            body,
            facts,
            suggested_actions: suggestedActions,
            tone: String(parsed.tone || "warm").trim().slice(0, 32),
            image_brief: String(parsed.image_brief || "").trim().slice(0, 180),
        };
    }

    async function callMultimodalCareModel(context) {
        const runtime = multimodalRuntimeConfig();
        if (!modelCallsEnabled()) throw new Error("model calls disabled");
        if (!runtime.base_url || !runtime.api_key || !runtime.model) throw new Error("multimodal model is not configured");
        const requestPayload = {
            model: runtime.model,
            messages: [
                { role: "system", content: runtime.prompt },
                {
                    role: "user",
                    content: [
                        "请根据以下结构化上下文生成今日关怀卡片。",
                        "必须只输出 JSON，不要输出解释文字。",
                        JSON.stringify(context),
                    ].join("\n\n"),
                },
            ],
            temperature: 0.6,
            max_tokens: 1600,
            response_format: { type: "json_object" },
            enable_thinking: false,
            thinking_budget: 128,
        };
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), modelRequestTimeoutMs());
        try {
            const response = await fetch(runtime.base_url, {
                method: "POST",
                headers: {
                    Authorization: `Bearer ${runtime.api_key}`,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(requestPayload),
                signal: controller.signal,
            });
            const responseText = await response.text();
            let responsePayload = safeJsonParse(responseText, null);
            if (!response.ok) {
                const detail = responsePayload?.error?.message || responsePayload?.message || responseText.slice(0, 200);
                throw new Error(`model request failed: ${response.status} ${detail}`);
            }
            if (!responsePayload || typeof responsePayload !== "object") {
                responsePayload = { raw_text: responseText };
            }
            const content = responsePayload.choices?.[0]?.message?.content
                || responsePayload.output_text
                || responsePayload.text
                || "";
            const parsed = extractJsonObject(content);
            const card = sanitizeModelCareCard(parsed);
            if (!card) {
                const error = new Error("model response is not valid CareCard JSON");
                error.response_payload = {
                    id: responsePayload.id || "",
                    model: responsePayload.model || runtime.model,
                    usage: responsePayload.usage || {},
                    content_preview: String(content || responseText || "").slice(0, 1200),
                };
                throw error;
            }
            return {
                card,
                request_payload: {
                    model: requestPayload.model,
                    messages: requestPayload.messages,
                    temperature: requestPayload.temperature,
                    max_tokens: requestPayload.max_tokens,
                    response_format: requestPayload.response_format,
                    enable_thinking: requestPayload.enable_thinking,
                    thinking_budget: requestPayload.thinking_budget,
                },
                response_payload: {
                    id: responsePayload.id || "",
                    model: responsePayload.model || runtime.model,
                    usage: responsePayload.usage || {},
                    parsed: card,
                },
            };
        } finally {
            clearTimeout(timeout);
        }
    }

    function sleep(ms) {
        return new Promise((resolve) => setTimeout(resolve, ms));
    }

    function compactPromptText(value, limit = 90) {
        const text = String(value || "").replace(/\s+/g, " ").trim();
        if (text.length <= limit) return text;
        return `${text.slice(0, Math.max(0, limit - 3))}...`;
    }

    function careImageBrief(card) {
        const recommendation = (Array.isArray(card.content_recommendations) ? card.content_recommendations : [])
            .find((item) => item?.type === "image_brief" || item?.summary);
        return String(recommendation?.summary || recommendation?.title || "").trim();
    }

    function buildCareImagePrompt(card, context, runtime = imageRuntimeConfig()) {
        const facts = (Array.isArray(card.facts) ? card.facts : []).slice(0, 4).map((item) => String(item || "").trim()).filter(Boolean);
        const schedule = context?.preferences?.care_card_schedule || {};
        const topicText = Array.isArray(schedule.interest_topics) && schedule.interest_topics.length
            ? schedule.interest_topics.slice(0, 5).join("、")
            : "天气、养生、家常";
        return [
            runtime.prompt,
            "",
            `卡片标题：${compactPromptText(card.title, 28)}`,
            `卡片短句：${compactPromptText(card.body, 64)}`,
            facts.length ? `事实依据摘要：${facts.join("；")}` : "",
            `老人兴趣话题：${topicText}`,
            careImageBrief(card) ? `视觉建议：${compactPromptText(careImageBrief(card), 90)}` : "",
            "生成要求：竖版 4:7，温馨可爱漫画风，画面像一张可直接发给家人的中文关怀图文卡。",
            "中文字只保留标题和短句，必须清晰、端正、无错别字。",
            "不要画真实监控画面、真实老人肖像、跌倒火灾等危险证据画面，也不要制造恐慌。",
        ].filter(Boolean).join("\n");
    }

    function buildCareImageRequestPayload(card, context, runtime = imageRuntimeConfig()) {
        const payload = {
            model: runtime.model,
            input: {
                messages: [
                    {
                        role: "user",
                        content: [
                            { text: buildCareImagePrompt(card, context, runtime) },
                        ],
                    },
                ],
            },
            parameters: {
                size: careImageSize(),
                watermark: false,
            },
        };
        if (/^wan2\.6-image$/i.test(String(runtime.model || ""))) {
            payload.parameters.enable_interleave = true;
            payload.parameters.max_images = 1;
        } else {
            payload.parameters.n = 1;
            payload.parameters.thinking_mode = true;
        }
        return payload;
    }

    function imageRequestMode(runtime = imageRuntimeConfig()) {
        const explicit = String(process.env.GOHOME_IMAGE_REQUEST_MODE || "").trim().toLowerCase();
        if (["sync", "async"].includes(explicit)) return explicit;
        return /\/multimodal-generation\/generation$/i.test(String(runtime.base_url || "")) ? "sync" : "async";
    }

    function syncCareImageRequestPayload(requestPayload) {
        if (!requestPayload?.parameters?.enable_interleave) return requestPayload;
        return {
            ...requestPayload,
            parameters: {
                ...(requestPayload.parameters || {}),
                stream: true,
            },
        };
    }

    async function fetchJsonWithTimeout(url, options = {}) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), modelRequestTimeoutMs());
        try {
            const response = await fetch(url, {
                ...options,
                signal: controller.signal,
            });
            const responseText = await response.text();
            const payload = safeJsonParse(responseText, { raw_text: responseText.slice(0, 1200) });
            if (!response.ok) {
                const detail = payload?.message || payload?.error?.message || payload?.code || responseText.slice(0, 200);
                const error = new Error(`image model request failed: ${response.status} ${detail}`);
                error.response_payload = payload;
                throw error;
            }
            return payload;
        } finally {
            clearTimeout(timeout);
        }
    }

    function parseDashScopePayloadText(responseText) {
        const direct = safeJsonParse(responseText, null);
        if (direct && typeof direct === "object") return direct;
        const streamEvents = [];
        for (const rawLine of String(responseText || "").split(/\r?\n/)) {
            const line = rawLine.trim();
            if (!line.startsWith("data:")) continue;
            const data = line.slice(5).trim();
            if (!data || data === "[DONE]") continue;
            const parsed = safeJsonParse(data, null);
            if (parsed && typeof parsed === "object") streamEvents.push(parsed);
        }
        if (streamEvents.length) {
            const last = streamEvents[streamEvents.length - 1] || {};
            return {
                stream_events: streamEvents,
                output: last.output || {},
                usage: last.usage || {},
                request_id: last.request_id || "",
            };
        }
        return { raw_text: String(responseText || "").slice(0, 1200) };
    }

    async function fetchDashScopeSyncPayload(url, requestPayload, runtime) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), modelRequestTimeoutMs());
        const headers = {
            Authorization: `Bearer ${runtime.api_key}`,
            "Content-Type": "application/json",
            Accept: "application/json",
        };
        if (requestPayload?.parameters?.enable_interleave && requestPayload?.parameters?.stream) {
            headers["X-DashScope-Sse"] = "enable";
            headers.Accept = "text/event-stream,application/json";
        }
        try {
            const response = await fetch(url, {
                method: "POST",
                headers,
                body: JSON.stringify(requestPayload),
                signal: controller.signal,
            });
            const responseText = await response.text();
            const payload = parseDashScopePayloadText(responseText);
            if (!response.ok) {
                const detail = payload?.message || payload?.error?.message || payload?.code || responseText.slice(0, 200);
                const error = new Error(`image model request failed: ${response.status} ${detail}`);
                error.response_payload = payload;
                throw error;
            }
            return payload;
        } finally {
            clearTimeout(timeout);
        }
    }

    function dashScopeTaskUrl(baseUrl, taskId) {
        const parsed = new URL(baseUrl);
        let prefix = "/api/v1";
        const index = parsed.pathname.indexOf("/api/v1/");
        if (index >= 0) {
            prefix = parsed.pathname.slice(0, index + "/api/v1".length);
        } else if (parsed.pathname.endsWith("/api/v1")) {
            prefix = parsed.pathname;
        }
        return `${parsed.origin}${prefix}/tasks/${encodeURIComponent(taskId)}`;
    }

    function imageTaskId(payload) {
        return String(payload?.output?.task_id || payload?.task_id || payload?.task?.id || "").trim();
    }

    function imageTaskStatus(payload) {
        return String(payload?.output?.task_status || payload?.task_status || payload?.status || payload?.output?.status || "").trim().toUpperCase();
    }

    function dashScopePayloadError(payload) {
        if (!payload || typeof payload !== "object") return "";
        if (payload.code && payload.message) return `${payload.code}: ${payload.message}`;
        const events = Array.isArray(payload.stream_events) ? payload.stream_events : [];
        const eventError = events.find((event) => event?.code && event?.message);
        return eventError ? `${eventError.code}: ${eventError.message}` : "";
    }

    function collectImageUrls(value, urls = []) {
        if (value === null || value === undefined) return urls;
        if (typeof value === "string") {
            const text = value.trim();
            if (/^data:image\//i.test(text) || /^https?:\/\//i.test(text)) urls.push(text);
            return urls;
        }
        if (Array.isArray(value)) {
            value.forEach((item) => collectImageUrls(item, urls));
            return urls;
        }
        if (typeof value === "object") {
            ["image", "image_url", "url"].forEach((key) => {
                if (typeof value[key] === "string") collectImageUrls(value[key], urls);
            });
            Object.entries(value).forEach(([key, item]) => {
                if (!["image", "image_url", "url"].includes(key)) collectImageUrls(item, urls);
            });
        }
        return urls;
    }

    function extractImageUrl(payload) {
        const urls = collectImageUrls(payload);
        return urls.find((url) => /^data:image\//i.test(url) || /\.(png|jpe?g|webp)(?:[?#].*)?$/i.test(new URL(url).pathname)) || urls[0] || "";
    }

    async function downloadGeneratedImage(imageUrl) {
        const dataMatch = String(imageUrl || "").match(/^data:(image\/[a-z0-9.+-]+)?(;base64)?,([\s\S]+)$/i);
        if (dataMatch) {
            const contentType = dataMatch[1] || "image/png";
            const buffer = dataMatch[2]
                ? Buffer.from(dataMatch[3], "base64")
                : Buffer.from(decodeURIComponent(dataMatch[3]), "utf8");
            return { buffer, content_type: contentType };
        }
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), modelRequestTimeoutMs());
        try {
            const response = await fetch(imageUrl, {
                headers: { Accept: "image/avif,image/webp,image/png,image/jpeg,image/*,*/*" },
                signal: controller.signal,
            });
            if (!response.ok) throw new Error(`image download failed: ${response.status}`);
            const contentType = String(response.headers.get("content-type") || "image/png").split(";")[0].trim() || "image/png";
            const buffer = Buffer.from(await response.arrayBuffer());
            if (!buffer.length) throw new Error("image download returned empty content");
            return { buffer, content_type: contentType };
        } finally {
            clearTimeout(timeout);
        }
    }

    function imageExtension(contentType, sourceUrl = "") {
        const type = String(contentType || "").toLowerCase();
        if (type.includes("jpeg") || type.includes("jpg")) return ".jpg";
        if (type.includes("webp")) return ".webp";
        if (type.includes("png")) return ".png";
        try {
            const ext = path.extname(new URL(sourceUrl).pathname).toLowerCase();
            if ([".jpg", ".jpeg", ".png", ".webp"].includes(ext)) return ext === ".jpeg" ? ".jpg" : ext;
        } catch (_error) {
            // Fall back to PNG below.
        }
        return ".png";
    }

    function storeCareCardImageAsset(card, familyId, imageBuffer, contentType, sourceUrl = "") {
        const assetId = store.nextId("asset");
        const extension = imageExtension(contentType, sourceUrl);
        const safeCardId = String(card.card_id || `care-${familyId}-${dateKeyShanghai()}`).replace(/[^\w.-]+/g, "_").slice(0, 90);
        const fileName = `${assetId}-${safeCardId}${extension}`;
        const relativePath = `care-cards/${dateKeyShanghai()}/${fileName}`;
        const target = path.join(mediaDir, ...relativePath.split("/"));
        ensureDir(path.dirname(target));
        fs.writeFileSync(target, imageBuffer);
        const timestamp = nowIso();
        const asset = {
            id: assetId,
            family_id: Number(familyId),
            device_id: "",
            camera_id: null,
            file_name: fileName,
            content_type: contentType || "image/png",
            snapshot_path: relativePath,
            relative_path: relativePath,
            storage_provider: "local",
            storage_key: relativePath,
            edge_event_id: "",
            size: imageBuffer.length,
            metadata: {
                purpose: "care_card_image",
                card_id: card.card_id || "",
            },
            created_at: timestamp,
            updated_at: timestamp,
            url: `/api/v1/video/media/snapshots/${encodeURIComponent(relativePath)}`,
        };
        store.db.assets.push(asset);
        return asset;
    }

    async function callCareImageModel(card, context) {
        const runtime = imageRuntimeConfig();
        if (!careImageCallsEnabled()) throw new Error("image model calls disabled");
        if (!imageRuntimeConfigured(runtime)) throw new Error("image model is not configured");
        let requestPayload = buildCareImageRequestPayload(card, context, runtime);
        const mode = imageRequestMode(runtime);
        const createPayload = mode === "sync"
            ? await fetchDashScopeSyncPayload(runtime.base_url, syncCareImageRequestPayload(requestPayload), runtime)
            : await fetchJsonWithTimeout(runtime.base_url, {
                method: "POST",
                headers: {
                    Authorization: `Bearer ${runtime.api_key}`,
                    "Content-Type": "application/json",
                    "X-DashScope-Async": "enable",
                },
                body: JSON.stringify(requestPayload),
            });
        if (mode === "sync") requestPayload = syncCareImageRequestPayload(requestPayload);
        let finalPayload = createPayload;
        let taskId = imageTaskId(createPayload);
        let taskStatus = imageTaskStatus(createPayload);
        const payloadError = dashScopePayloadError(createPayload);
        if (payloadError) {
            const error = new Error(payloadError);
            error.response_payload = createPayload;
            throw error;
        }
        let imageUrl = extractImageUrl(createPayload);
        if (mode === "async" && !imageUrl && taskId) {
            const taskUrl = dashScopeTaskUrl(runtime.base_url, taskId);
            for (let index = 0; index < careImageMaxPolls(); index += 1) {
                await sleep(careImagePollIntervalMs());
                finalPayload = await fetchJsonWithTimeout(taskUrl, {
                    method: "GET",
                    headers: {
                        Authorization: `Bearer ${runtime.api_key}`,
                        Accept: "application/json",
                    },
                });
                taskStatus = imageTaskStatus(finalPayload);
                imageUrl = extractImageUrl(finalPayload);
                if (imageUrl) break;
                if (["FAILED", "CANCELED", "UNKNOWN"].includes(taskStatus)) {
                    const error = new Error(`image task ${taskStatus.toLowerCase()}`);
                    error.response_payload = finalPayload;
                    throw error;
                }
            }
        }
        if (!imageUrl) {
            const error = new Error(taskId ? "image task finished without image url" : "image model response did not include image url");
            error.response_payload = finalPayload;
            throw error;
        }
        const downloaded = await downloadGeneratedImage(imageUrl);
        return {
            image_url: imageUrl,
            image_buffer: downloaded.buffer,
            content_type: downloaded.content_type,
            request_payload: {
                model: requestPayload.model,
                input: requestPayload.input,
                parameters: requestPayload.parameters,
            },
            response_payload: {
                task_id: taskId,
                task_status: taskStatus || imageTaskStatus(finalPayload) || "SUCCEEDED",
                request_mode: mode,
                request_id: finalPayload?.request_id || finalPayload?.output?.task_id || "",
                image_url_set: true,
                content_type: downloaded.content_type,
                size_bytes: downloaded.buffer.length,
                usage: finalPayload?.usage || {},
            },
        };
    }

    async function ensureCareCardImage(card, familyId, parts = {}) {
        const preferences = parts.preferences || carePreferences(familyId);
        if (!careImageRequested(preferences)) {
            if (!card.image_url) card.image_mode = "none";
            return false;
        }
        if (card.image_url && card.image_mode === "generated") return true;
        if (card.image_mode === "failed_provider" && !parts.forceImage) return false;
        const runtime = imageRuntimeConfig();
        if (!careImageCallsEnabled() || !imageRuntimeConfigured(runtime)) {
            if (!card.image_url) card.image_mode = "pending_provider";
            return false;
        }
        card.image_mode = "pending_provider";
        const context = careCardModelContext(familyId, { ...parts, preferences });
        const inputHash = sha256(JSON.stringify({
            card: {
                title: card.title,
                body: card.body,
                facts: card.facts,
                card_date: card.card_date,
            },
            context,
            image_size: careImageSize(),
            prompt_source: runtime.prompt_source,
        }));
        const job = modelJob({
            family_id: familyId,
            purpose: "care_card_image_generation",
            model: runtime.model,
            prompt_version: `care-image:${runtime.prompt_source}`,
            input_hash: inputHash,
            output_status: "pending",
            request_payload: {
                capability_id: runtime.capability_id,
                card_id: card.card_id,
            },
            metadata: {
                capability_id: runtime.capability_id,
                provider: "dashscope-wan",
                aspect_ratio: "4:7",
            },
        });
        store.db.model_generation_jobs.push(job);
        try {
            const imageResult = await callCareImageModel(card, context);
            const asset = storeCareCardImageAsset(card, familyId, imageResult.image_buffer, imageResult.content_type, imageResult.image_url);
            card.image_mode = "generated";
            card.image_url = asset.snapshot_path;
            card.updated_at = nowIso();
            card.source_summary = [...new Set([...(Array.isArray(card.source_summary) ? card.source_summary : []), "生图模型"])];
            updateModelJob(job, {
                output_status: "succeeded",
                request_payload: {
                    capability_id: runtime.capability_id,
                    ...imageResult.request_payload,
                },
                response_payload: {
                    ...imageResult.response_payload,
                    media_asset_id: asset.id,
                    snapshot_path: asset.snapshot_path,
                },
            });
            return true;
        } catch (error) {
            if (!card.image_url) card.image_mode = "failed_provider";
            card.updated_at = nowIso();
            card.source_summary = [...new Set([...(Array.isArray(card.source_summary) ? card.source_summary : []), "生图失败，已保留文字卡片"])];
            updateModelJob(job, {
                output_status: "failed",
                error_message: error.message || "image model request failed",
                response_payload: error.response_payload || { fallback: "text_card" },
            });
            return false;
        }
    }

    function daysSinceDateString(value) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ""))) return null;
        const timestamp = Date.parse(`${value}T00:00:00+08:00`);
        if (!Number.isFinite(timestamp)) return null;
        return Math.max(0, Math.floor((Date.now() - timestamp) / (24 * 60 * 60 * 1000)));
    }

    function careCardFacts(familyId, preferences = carePreferences(familyId)) {
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
        const schedule = preferences.metadata?.care_card_schedule || defaultCareSchedule();
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
        if (schedule.content_types?.visit_reminder && schedule.visit_reminder?.enabled) {
            const daysSinceVisit = daysSinceDateString(schedule.visit_reminder.last_visit_at);
            if (daysSinceVisit !== null) {
                facts.push(`距离上次回家已经 ${daysSinceVisit} 天，提醒阈值是 ${schedule.visit_reminder.threshold_days} 天。`);
            } else {
                facts.push(`已开启回家间隔提醒，阈值是 ${schedule.visit_reminder.threshold_days} 天。`);
            }
        }
        if (schedule.content_types?.elder_interest_topics && schedule.interest_topics?.length) {
            facts.push(`老人关心的话题包括：${schedule.interest_topics.slice(0, 6).join("、")}。`);
        }
        if (schedule.content_types?.anniversaries && schedule.anniversaries?.length) {
            facts.push(`已配置 ${schedule.anniversaries.length} 个纪念日提醒。`);
        }
        if (schedule.message_focus) {
            facts.push(`本次关怀重点：${schedule.message_focus}`);
        }
        facts.push(`${profile.display_name || "家人"} 所在城市按 ${profile.city || "杭州"} 生成天气问候。`);
        return { facts, cameras, onlineCameras, openEvents, criticalEvents, device, profile };
    }

    async function generateCareCard(familyId, options = {}) {
        const targetFamilyId = Number(familyId || store.db.families[0]?.id || 1);
        const cardDate = dateKeyShanghai();
        const preferences = carePreferences(targetFamilyId);
        const existing = store.db.care_cards.find((card) => (
            Number(card.family_id) === targetFamilyId && card.card_date === cardDate && card.card_type === "daily"
        ));
        if (existing && !options.force) {
            if (careImageRequested(preferences) && !existing.image_url && existing.image_mode !== "failed_provider") {
                const existingParts = careCardFacts(targetFamilyId, preferences);
                await ensureCareCardImage(existing, targetFamilyId, { ...existingParts, preferences });
            }
            return existing;
        }
        const factParts = careCardFacts(targetFamilyId, preferences);
        const { facts, onlineCameras, openEvents, criticalEvents, profile } = factParts;
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
            image_mode: careImageRequested(preferences) ? "pending_provider" : "none",
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
        const runtime = multimodalRuntimeConfig();
        const canUseModel = modelCallsEnabled() && runtime.base_url && runtime.api_key && runtime.model;
        if (canUseModel) {
            const context = careCardModelContext(targetFamilyId, { ...factParts, preferences });
            const inputHash = sha256(JSON.stringify(context));
            const job = modelJob({
                family_id: targetFamilyId,
                purpose: "care_card_generation",
                model: runtime.model,
                prompt_version: `care-card:${runtime.prompt_source}`,
                input_hash: inputHash,
                output_status: "pending",
                request_payload: {
                    capability_id: runtime.capability_id,
                    context,
                },
                metadata: {
                    capability_id: runtime.capability_id,
                    provider: "multimodal-language",
                },
            });
            store.db.model_generation_jobs.push(job);
            try {
                const modelResult = await callMultimodalCareModel(context);
                updateModelJob(job, {
                    output_status: "succeeded",
                    request_payload: modelResult.request_payload,
                    response_payload: modelResult.response_payload,
                });
                const generated = modelResult.card;
                card.title = generated.title;
                card.body = generated.body;
                card.facts = generated.facts.length ? generated.facts : facts;
                card.actions = [
                    { key: "call", label: generated.suggested_actions[0] || "打电话问候" },
                    { key: "open_watch", label: generated.suggested_actions[1] || (onlineCameras.length ? "看看家里" : "查看设备") },
                    { key: "open_events", label: generated.suggested_actions[2] || (openEvents.length ? "查看提醒" : "查看今日状态") },
                ];
                card.generated_by = `model:${runtime.model}`;
                card.source_summary = [
                    ...sourceSummary,
                    "多模态语言模型",
                ];
                card.content_recommendations = generated.image_brief
                    ? [{ type: "image_brief", title: "关怀卡片配图建议", summary: generated.image_brief }]
                    : [];
            } catch (error) {
                updateModelJob(job, {
                    output_status: "failed",
                    error_message: error.message || "model request failed",
                    response_payload: error.response_payload || {
                        fallback: "care-template-v2",
                    },
                });
                card.source_summary = [
                    ...sourceSummary,
                    "模型生成失败，已使用模板兜底",
                ];
            }
        }
        await ensureCareCardImage(card, targetFamilyId, { ...factParts, preferences, forceImage: options.force });
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
        if (pathname === "/ops.html" && !requireOps(req, res)) return;
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
                const nextMetadata = payload.metadata && typeof payload.metadata === "object"
                    ? normalizeCareMetadata({ ...(existing.metadata || {}), ...payload.metadata })
                    : normalizeCareMetadata(existing.metadata || {});
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
                    metadata: nextMetadata,
                    updated_at: nowIso(),
                });
                await store.save();
                write(res, 200, store.db.care_preferences[String(familyId)]);
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/app/care-cards/today") {
                if (!requireApp(req, res)) return;
                const familyId = normalizeNumber(url.searchParams.get("family_id"), store.db.families[0]?.id || 1);
                const card = await generateCareCard(familyId);
                await store.save();
                write(res, 200, publicCareCard(card));
                return;
            }

            if (req.method === "POST" && pathname === "/api/v1/internal/care-cards/generate") {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req);
                const familyId = normalizeNumber(payload.family_id, store.db.families[0]?.id || 1);
                const card = await generateCareCard(familyId, { force: normalizeBool(payload.force) });
                await store.save();
                write(res, 200, { ok: true, card: publicCareCard(card) });
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/model-providers") {
                if (!requireOps(req, res)) return;
                write(res, 200, modelCapabilities().map((capability) => ({
                    provider_id: capability.capability_id,
                    provider: capability.type,
                    model: capability.model,
                    purpose: capability.scope,
                    enabled: capability.enabled,
                    configured: capability.configured,
                    api_key_set: capability.api_key_set,
                    base_url_set: capability.base_url_set,
                    secret_mode: capability.api_key_set ? "env" : "unset",
                })));
                return;
            }

            const modelProviderMatch = pathname.match(/^\/api\/v1\/model-providers\/([^/]+)$/);
            if (modelProviderMatch && req.method === "PUT") {
                if (!requireOps(req, res)) return;
                writeError(res, 405, "模型底层配置由平台方通过服务器环境变量或云端 Secret Manager 管理。");
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/ops/service-config") {
                if (!requireOps(req, res)) return;
                const capabilities = modelCapabilities();
                write(res, 200, {
                    ok: true,
                    service: "gohome-local-app-server",
                    store: store.kind || "json",
                    app_server_base_url: process.env.GOHOME_APP_SERVER_BASE_URL || `http://localhost:${DEFAULT_PORT}`,
                    env_files: LOADED_ENV_FILES,
                    model_capabilities: capabilities,
                    secret_policy: {
                        local: "server_env",
                        cloud: "secret_manager_or_kms",
                        database: "no_plain_secret",
                        user_configurable: false,
                    },
                    user_visible: false,
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
