#!/usr/bin/env node
"use strict";

const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const https = require("https");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
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

function normalizeChinaPhone(value) {
    const digits = String(value || "").replace(/\D/g, "");
    if (/^1\d{10}$/.test(digits)) return digits;
    if (/^861\d{10}$/.test(digits)) return digits.slice(2);
    return "";
}

function phoneAccountEmail(phone) {
    const normalized = normalizeChinaPhone(phone);
    return normalized ? `${normalized}@phone.gohome.local` : "";
}

function phoneFromAccountEmail(email) {
    const match = String(email || "").trim().toLowerCase().match(/^(\d{11})@phone\.gohome\.local$/);
    return match ? normalizeChinaPhone(match[1]) : "";
}

function authIdentityFromPayload(payload = {}, fallbackEmail = "") {
    const rawPhone = payload.phone || payload.mobile_phone || payload.mobile || payload.phone_number || "";
    const phone = normalizeChinaPhone(rawPhone || (/^\d[\d\s-]{8,}$/.test(String(payload.email || "")) ? payload.email : ""));
    if (phone) {
        return { email: phoneAccountEmail(phone), phone, isPhone: true };
    }
    const email = String(payload.email || fallbackEmail || "").trim().toLowerCase();
    return { email, phone: phoneFromAccountEmail(email), isPhone: Boolean(phoneFromAccountEmail(email)) };
}

function redactedSecret(value) {
    const text = String(value || "");
    if (!text) return "";
    if (text.length <= 10) return "set";
    return `${text.slice(0, 6)}...${text.slice(-4)}`;
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

function defaultRules(timestamp = nowIso()) {
    return {
        capture_interval_seconds: 5,
        motion_threshold: 0.015,
        black_brightness_threshold: 18,
        black_contrast_threshold: 8,
        yolo_confidence: 0.35,
        no_motion_seconds: 900,
        no_person_seconds: 900,
        offline_enabled: true,
        black_screen_enabled: true,
        no_motion_enabled: true,
        person_detection_enabled: true,
        fall_detection_enabled: true,
        fall_score_threshold: 0.5,
        fall_confirm_frames: 2,
        fall_confirm_seconds: 4,
        fall_recover_frames: 2,
        activity_detection_enabled: true,
        fire_detection_enabled: true,
        fire_event_score_threshold: 0.62,
        fire_motion_threshold: 0.12,
        fire_temporal_threshold: 0.35,
        fire_confirm_frames: 3,
        notification_enabled: true,
        updated_at: timestamp,
    };
}

function clampNumber(value, fallback, min, max) {
    const number = normalizeNumber(value, fallback);
    return Math.min(max, Math.max(min, number));
}

function normalizeRules(value = {}, base = defaultRules()) {
    const input = value && typeof value === "object" ? value : {};
    const boolFrom = (key) => (key in input ? normalizeBool(input[key]) : Boolean(base[key]));
    return {
        ...base,
        capture_interval_seconds: clampNumber(input.capture_interval_seconds, base.capture_interval_seconds, 1, 3600),
        motion_threshold: clampNumber(input.motion_threshold, base.motion_threshold, 0, 1),
        black_brightness_threshold: clampNumber(input.black_brightness_threshold, base.black_brightness_threshold, 0, 255),
        black_contrast_threshold: clampNumber(input.black_contrast_threshold, base.black_contrast_threshold, 0, 255),
        yolo_confidence: clampNumber(input.yolo_confidence, base.yolo_confidence, 0.01, 1),
        no_motion_seconds: clampNumber(input.no_motion_seconds, base.no_motion_seconds, 10, 86400),
        no_person_seconds: clampNumber(input.no_person_seconds, base.no_person_seconds, 10, 86400),
        offline_enabled: boolFrom("offline_enabled"),
        black_screen_enabled: boolFrom("black_screen_enabled"),
        no_motion_enabled: boolFrom("no_motion_enabled"),
        person_detection_enabled: boolFrom("person_detection_enabled"),
        fall_detection_enabled: boolFrom("fall_detection_enabled"),
        fall_score_threshold: clampNumber(input.fall_score_threshold, base.fall_score_threshold, 0, 1),
        fall_confirm_frames: clampNumber(input.fall_confirm_frames, base.fall_confirm_frames, 1, 120),
        fall_confirm_seconds: clampNumber(input.fall_confirm_seconds, base.fall_confirm_seconds, 0, 300),
        fall_recover_frames: clampNumber(input.fall_recover_frames, base.fall_recover_frames, 1, 120),
        activity_detection_enabled: boolFrom("activity_detection_enabled"),
        fire_detection_enabled: boolFrom("fire_detection_enabled"),
        fire_event_score_threshold: clampNumber(input.fire_event_score_threshold, base.fire_event_score_threshold, 0, 1),
        fire_motion_threshold: clampNumber(input.fire_motion_threshold, base.fire_motion_threshold, 0, 1),
        fire_temporal_threshold: clampNumber(input.fire_temporal_threshold, base.fire_temporal_threshold, 0, 1),
        fire_confirm_frames: clampNumber(input.fire_confirm_frames, base.fire_confirm_frames, 1, 120),
        notification_enabled: boolFrom("notification_enabled"),
        updated_at: String(input.updated_at || base.updated_at || nowIso()),
    };
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

function compactCareCards(cards = []) {
    const byCardId = new Map();
    const byDailyKey = new Map();
    const merged = [];
    const newerThan = (a, b) => Date.parse(a?.updated_at || a?.created_at || "") >= Date.parse(b?.updated_at || b?.created_at || "");
    const dailyKey = (card) => [
        card?.family_id || "",
        card?.elder_id || "elder_primary",
        card?.card_date || "",
        card?.card_type || "daily",
    ].join("|");
    const mergeCard = (base, next) => {
        const preferred = newerThan(next, base) ? next : base;
        const fallback = preferred === next ? base : next;
        return {
            ...fallback,
            ...preferred,
            facts: Array.isArray(preferred.facts) && preferred.facts.length ? preferred.facts : (fallback.facts || []),
            actions: Array.isArray(preferred.actions) && preferred.actions.length ? preferred.actions : (fallback.actions || []),
            source_summary: Array.isArray(preferred.source_summary) && preferred.source_summary.length ? preferred.source_summary : (fallback.source_summary || []),
            content_recommendations: Array.isArray(preferred.content_recommendations) && preferred.content_recommendations.length
                ? preferred.content_recommendations
                : (fallback.content_recommendations || []),
            image_url: preferred.image_url || fallback.image_url || "",
            image_mode: preferred.image_url ? preferred.image_mode : (preferred.image_mode || fallback.image_mode || "none"),
        };
    };

    for (const raw of Array.isArray(cards) ? cards : []) {
        if (!raw || typeof raw !== "object") continue;
        const card = {
            ...raw,
            card_id: String(raw.card_id || `care-${raw.family_id || "family"}-${raw.card_date || dateKeyShanghai()}`),
            elder_id: String(raw.elder_id || "elder_primary"),
            card_type: String(raw.card_type || "daily"),
        };
        const keys = [`card:${card.card_id}`, `daily:${dailyKey(card)}`];
        const existingIndex = keys.map((key) => byCardId.get(key) ?? byDailyKey.get(key)).find((index) => index !== undefined);
        if (existingIndex === undefined) {
            const index = merged.length;
            merged.push(card);
            keys.forEach((key) => {
                if (key.startsWith("card:")) byCardId.set(key, index);
                else byDailyKey.set(key, index);
            });
            continue;
        }
        merged[existingIndex] = mergeCard(merged[existingIndex], card);
        const refreshed = merged[existingIndex];
        byCardId.set(`card:${refreshed.card_id}`, existingIndex);
        byDailyKey.set(`daily:${dailyKey(refreshed)}`, existingIndex);
    }
    return merged;
}

function createDefaultDb() {
    const timestamp = nowIso();
    return {
        version: 1,
        created_at: timestamp,
        updated_at: timestamp,
        active_user_id: 1,
        next_ids: {
            user: 2,
            family: 2,
            family_member: 1,
            elder_profile: 1,
            app_session: 1,
            binding: 1,
            binding_code: 1,
            device_token: 1,
            asset: 1,
            event: 1,
            camera: 1,
            heartbeat: 1,
            calendar_event: 1,
            care_card: 1,
            app_message: 1,
            notification_delivery: 1,
            app_push_token: 1,
            scheduler_run: 1,
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
                created_by_user_id: 1,
                created_at: timestamp,
            },
        ],
        family_members: [
            {
                id: "1:owner:1",
                family_id: 1,
                user_id: 1,
                role: "owner",
                status: "active",
                joined_at: timestamp,
                created_at: timestamp,
                updated_at: timestamp,
            },
        ],
        elder_profiles: {},
        app_sessions: [],
        device_bindings: [],
        binding_codes: [],
        device_tokens: [],
        devices: {},
        cameras: {},
        assets: [],
        events: [],
        heartbeats: [],
        rules: defaultRules(timestamp),
        family_rules: {
            1: defaultRules(timestamp),
        },
        calendar_events: [],
        care_preferences: {},
        care_cards: [],
        app_messages: [],
        notification_deliveries: [],
        app_push_tokens: [],
        scheduler_runs: [],
        model_providers: [],
        model_generation_jobs: [],
        content_sources: [],
        content_recommendations: [],
    };
}

function createEmptyDb() {
    const db = createDefaultDb();
    db.active_user_id = null;
    db.users = [];
    db.families = [];
    db.family_members = [];
    db.family_rules = {};
    return db;
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
    const hadActiveUserId = db.active_user_id !== undefined && db.active_user_id !== null;
    db.next_ids = { ...defaults.next_ids, ...(db.next_ids || {}) };
    db.active_user_id = Number(db.active_user_id || defaults.active_user_id);
    db.users = Array.isArray(db.users) ? db.users : defaults.users;
    if (!hadActiveUserId) {
        const recentNonAdmin = [...db.users].reverse().find((item) => item.email !== "admin@gohome.local");
        if (recentNonAdmin) db.active_user_id = recentNonAdmin.id;
    }
    db.families = Array.isArray(db.families) ? db.families : defaults.families;
    db.family_members = Array.isArray(db.family_members) ? db.family_members : [];
    if (!db.family_members.length && db.families.length && db.users.length) {
        const owner = db.users.find((item) => Number(item.id) === Number(db.active_user_id))
            || [...db.users].reverse().find((item) => item.email !== "admin@gohome.local")
            || db.users[0];
        db.family_members = db.families.map((family) => ({
            id: `${family.id}:owner:${owner.id}`,
            family_id: family.id,
            user_id: owner.id,
            role: "owner",
            status: "active",
            joined_at: family.created_at || db.created_at,
            created_at: family.created_at || db.created_at,
            updated_at: family.updated_at || family.created_at || db.created_at,
        }));
    }
    for (const family of db.families) {
        if (family.created_by_user_id) continue;
        const owners = db.family_members.filter((item) => (
            Number(item.family_id) === Number(family.id)
            && String(item.status || "active") === "active"
            && String(item.role || "member") === "owner"
        ));
        const nonAdminOwner = owners.find((item) => {
            const user = db.users.find((candidate) => Number(candidate.id) === Number(item.user_id));
            return user && user.email !== "admin@gohome.local";
        });
        const creator = nonAdminOwner || owners[0] || db.family_members.find((item) => (
            Number(item.family_id) === Number(family.id)
            && String(item.status || "active") === "active"
        ));
        family.created_by_user_id = creator?.user_id || null;
    }
    db.elder_profiles = db.elder_profiles && typeof db.elder_profiles === "object" ? db.elder_profiles : {};
    db.app_sessions = Array.isArray(db.app_sessions) ? db.app_sessions : [];
    db.device_bindings = Array.isArray(db.device_bindings) ? db.device_bindings : [];
    db.binding_codes = Array.isArray(db.binding_codes) ? db.binding_codes : [];
    db.device_tokens = Array.isArray(db.device_tokens) ? db.device_tokens : [];
    db.devices = db.devices && typeof db.devices === "object" ? db.devices : {};
    Object.entries(db.devices).forEach(([key, device]) => {
        if (!device || typeof device !== "object") {
            delete db.devices[key];
            return;
        }
        device.device_id = device.device_id || device.id || key;
        device.id = device.id || device.device_id;
        device.metadata = device.metadata && typeof device.metadata === "object" && !Array.isArray(device.metadata)
            ? device.metadata
            : {};
    });
    db.cameras = db.cameras && typeof db.cameras === "object" ? db.cameras : {};
    db.assets = Array.isArray(db.assets) ? db.assets : [];
    db.events = Array.isArray(db.events) ? db.events : [];
    db.heartbeats = Array.isArray(db.heartbeats) ? db.heartbeats : [];
    db.rules = normalizeRules(db.rules || defaults.rules, defaults.rules);
    db.family_rules = db.family_rules && typeof db.family_rules === "object" && !Array.isArray(db.family_rules)
        ? db.family_rules
        : {};
    for (const family of db.families) {
        const key = String(family.id);
        db.family_rules[key] = normalizeRules(db.family_rules[key] || db.rules, db.rules);
    }
    db.calendar_events = Array.isArray(db.calendar_events) ? db.calendar_events : [];
    db.care_preferences = db.care_preferences && typeof db.care_preferences === "object" ? db.care_preferences : {};
    db.care_cards = compactCareCards(Array.isArray(db.care_cards) ? db.care_cards : []);
    db.app_messages = Array.isArray(db.app_messages) ? db.app_messages : [];
    db.notification_deliveries = Array.isArray(db.notification_deliveries) ? db.notification_deliveries : [];
    db.app_push_tokens = Array.isArray(db.app_push_tokens) ? db.app_push_tokens : [];
    db.scheduler_runs = Array.isArray(db.scheduler_runs) ? db.scheduler_runs : [];
    db.model_providers = Array.isArray(db.model_providers) ? db.model_providers : [];
    db.model_generation_jobs = Array.isArray(db.model_generation_jobs) ? db.model_generation_jobs : [];
    db.content_sources = Array.isArray(db.content_sources) ? db.content_sources : [];
    db.content_recommendations = Array.isArray(db.content_recommendations) ? db.content_recommendations : [];
    const idSources = {
        user: db.users,
        family: db.families,
        family_member: db.family_members,
        app_session: db.app_sessions,
        binding: db.device_bindings,
        binding_code: db.binding_codes,
        device_token: db.device_tokens,
        asset: db.assets,
        event: db.events,
        camera: Object.values(db.cameras),
        heartbeat: db.heartbeats,
        calendar_event: db.calendar_events,
        care_card: db.care_cards,
        app_message: db.app_messages,
        notification_delivery: db.notification_deliveries,
        app_push_token: db.app_push_tokens,
        scheduler_run: db.scheduler_runs,
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
    const { AuthService } = require("./native-api/auth-service");
    const authService = options.authService || new AuthService({
        mode: options.authMode || process.env.GOHOME_AUTH_MODE || "production",
        demoOtp: options.demoOtp || process.env.GOHOME_DEMO_OTP || "",
        secret: options.authSecret || process.env.GOHOME_AUTH_SECRET || "",
        smsProvider: options.smsProvider || null,
    });
    const playbackTickets = new Map();
    const boxAdminSessions = new Map();
    const providerCache = new Map();
    const careCardGenerationJobs = new Map();
    const liveFrameCache = new Map();
    const liveFrameSequence = new Map();
    let schedulerRunning = false;
    let visionVerificationRunning = false;
    const LIVE_FRAME_TTL_MS = 10000;

    ensureDir(mediaDir);

    const defaultCareTextPrompt = [
        "你是回家 App 的联系灵感编辑。",
        "请基于家庭资料、日历、天气、关注话题、设备状态和最近事件，整理一条今天值得联系家里的具体理由。",
        "这不是监控播报、健康教育或系统通知；目标是让成年子女自然地开启一次联系。",
        "标题要像生活方式资讯标题，描述一个具体时刻或话题，不要写成命令、口号或功能名称。",
        "正文先交代一个真实依据，再给一句能直接拿来开场的话；语气平等、自然，不教育用户，也不教育家里人。",
        "普通关怀的标题和正文不要播报设备在线、无异常或无告警；这些状态只能放在 facts 里作为内容依据。",
        "不要使用“提醒喝水”“注意身体”“多陪陪家人”“聊聊家常”“今天问个安”“家里一切平稳”等机械表达。",
        "不要默认使用老人、妈妈、爸爸等身份标签；只有用户资料明确要求且句子确有必要时才使用称呼。",
        "如果没有安全事件，也必须从天气、周末、节假日、纪念日、回家间隔或老人兴趣中选择一个真实信号作为主题。",
        "热点或内容搜索结果只能作为温和话题候选，不要照抄耸动标题、负面标题或平台水印式标题。",
        "家属通常不在家里，行动建议只能是打电话、发微信、约定回家或准备节日问候，禁止写成递茶、端水、送到手边或陪在身边。",
        "不要编造老人真实行为、健康结论、实时天气、手机定位距离或未接入的数据。",
        "高优先级安全事件要明确要求先确认；普通关怀不能渲染风险，也不要引导查看监控。",
        "输出必须是 JSON，字段为 title、body、facts、suggested_actions、tone、image_brief。",
        "title 不超过 18 个中文字符，body 不超过 88 个中文字符，facts 最多 3 条，每条只写一个可核验依据。",
        "suggested_actions 最多 3 条，优先给打电话、发消息、准备节日问候；普通关怀不要引导去看监控。",
        "tone 只能使用 warm、calm、alert、seasonal、memory 中的一个。",
        "image_brief 只描述一幅无文字的生活场景图片，不要包含海报、排版、监控证据或真实人物肖像。",
    ].join("\n");

    const defaultVisionVerificationPrompt = [
        "你是家庭守护事件的视觉复核模型，只根据输入图片和结构化边缘证据判断当前画面。",
        "你不能根据单张图片诊断疾病，也不能声称已经确认真实事故；你只负责复核画面是否支持边缘候选。",
        "必须只输出一个 JSON 对象，不要输出 Markdown、解释前缀或额外字段。",
        "JSON 必须包含 person_count、posture、surface、emergency、confidence、reason、suggested_event_type。",
        "person_count 是 0 到 20 的整数。",
        "posture 只能是 standing、sitting、squatting、bending、lying、fallen、unknown。",
        "surface 只能是 floor、bed、sofa、chair、unknown。",
        "emergency 是布尔值；只有画面明显支持需要家属立即确认的跌倒、长时间倒地或火灾线索时才为 true。",
        "confidence 是 0 到 1 的数字，表示本次视觉判断把握度。",
        "reason 使用不超过 120 个中文字符描述可见事实，不得编造持续时间、身份、疾病或画面外情况。",
        "suggested_event_type 只能是 fall_candidate、prolonged_floor_lying、fire_candidate、none、uncertain。",
        "如果图片模糊、遮挡、无人或不足以判断，使用 unknown/uncertain，不能强行确认。",
        "床或沙发上的正常躺卧通常不应判为紧急；持续时长以结构化边缘证据为准，不从单图猜测。",
        "必须区分人物与猫狗。猫狗不计入 person_count，宠物在地面、床或沙发上不能当作人物躺倒或跌倒证据。",
    ].join("\n");

    const defaultCareImagePrompt = [
        "生成一张横向 4:3 的写实生活方式静物摄影。",
        "固定视觉系统：纯白或接近纯白占主要面积，黑色只用于少量真实物件，姜黄色 #D49A24 只作为一个小面积点睛色；允许中性灰和自然材质本色。",
        "自然日光、真实材质、克制构图、轻微景深；主体明确，画面干净但保留生活痕迹。",
        "使用近景或中近景，完整铺满画幅，不添加二次画布、留白版式或图形设计层。",
        "所有物件表面保持纯色和无标识，电子设备保持熄屏。",
        "画面中不要出现任何文字、汉字、字母、数字、日期、品牌、logo、水印、标签、手机界面或可读钟表。",
        "禁止水彩、蜡笔、儿童绘本、Q 版漫画、卡通人物、怀旧年画、3D 盲盒和模板化 AI 插画风格。",
        "禁止大面积米黄、棕色、粉色、橙色渐变，禁止任何外轮廓、圆角边框、相框、厚重阴影、金色边框、发光文字、贴纸、角标、奖章、logo 和水印。",
        "不要出现真实老人肖像、监控画面、跌倒、火灾、医疗诊断、恐慌表情或红色警报风格。",
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

    function visionVerificationRuntimeConfig() {
        const multimodal = multimodalRuntimeConfig();
        return {
            ...multimodal,
            capability_id: "vision-event-verification",
            prompt: envFirst(["GOHOME_VISION_VERIFICATION_PROMPT"], defaultVisionVerificationPrompt),
            prompt_source: process.env.GOHOME_VISION_VERIFICATION_PROMPT ? "env" : "default",
        };
    }

    function imageRuntimeConfig() {
        const prompt = envFirst(["GOHOME_CARE_IMAGE_PROMPT"], defaultCareImagePrompt);
        return {
            capability_id: "care-card-image",
            api_key: envFirst(["GOHOME_IMAGE_API_KEY", "GOHOME_WAN_API_KEY", "DASHSCOPE_API_KEY", "WAN_API_KEY"]),
            base_url: normalizeModelEndpoint(
                envFirst(["GOHOME_IMAGE_BASE_URL", "GOHOME_WAN_BASE_URL", "DASHSCOPE_BASE_URL", "WAN_BASE_URL"])
            ),
            model: envFirst(["GOHOME_IMAGE_MODEL", "GOHOME_WAN_MODEL", "WAN_MODEL"], "wan2.7-image"),
            prompt,
            prompt_source: process.env.GOHOME_CARE_IMAGE_PROMPT ? "env" : "default",
            prompt_fingerprint: sha256(prompt).slice(0, 12),
        };
    }

    function weatherRuntimeConfig() {
        const qweatherKey = envFirst(["GOHOME_QWEATHER_API_KEY", "QWEATHER_API_KEY", "HEFENG_WEATHER_API_KEY", "GOHOME_WEATHER_API_KEY"]);
        const configuredProvider = envFirst(["GOHOME_WEATHER_PROVIDER"], qweatherKey ? "qweather" : "none").toLowerCase();
        const provider = ["qweather", "open-meteo", "none", "off", "disabled"].includes(configuredProvider)
            ? configuredProvider
            : "qweather";
        return {
            capability_id: "weather-signals",
            provider,
            api_key: qweatherKey,
            base_url: envFirst(["GOHOME_QWEATHER_BASE_URL", "QWEATHER_BASE_URL", "GOHOME_WEATHER_BASE_URL"], "https://devapi.qweather.com").replace(/\/+$/, ""),
            geo_base_url: envFirst(["GOHOME_QWEATHER_GEO_BASE_URL", "QWEATHER_GEO_BASE_URL"], "https://geoapi.qweather.com").replace(/\/+$/, ""),
            auth_mode: envFirst(["GOHOME_QWEATHER_AUTH_MODE", "QWEATHER_AUTH_MODE"], "auto").toLowerCase(),
        };
    }

    function contentSearchRuntimeConfig() {
        const tavilyKey = envFirst(["GOHOME_TAVILY_API_KEY", "TAVILY_API_KEY", "GOHOME_SEARCH_API_KEY"]);
        const configuredProvider = envFirst(["GOHOME_SEARCH_PROVIDER", "GOHOME_CONTENT_SEARCH_PROVIDER"], tavilyKey ? "tavily" : "none").toLowerCase();
        const provider = ["tavily", "none", "off", "disabled"].includes(configuredProvider)
            ? configuredProvider
            : "tavily";
        return {
            capability_id: "content-search",
            provider,
            api_key: tavilyKey,
            base_url: envFirst(["GOHOME_TAVILY_BASE_URL", "TAVILY_BASE_URL", "GOHOME_SEARCH_BASE_URL"], "https://api.tavily.com/search").replace(/\/+$/, ""),
            max_results: Math.max(2, Math.min(8, normalizeNumber(process.env.GOHOME_TAVILY_MAX_RESULTS, 5))),
        };
    }

    function modelCallsEnabled() {
        const value = String(process.env.GOHOME_CARE_MODEL_CALLS || "1").trim().toLowerCase();
        return !["0", "false", "off", "disabled"].includes(value);
    }

    function visionVerificationEnabled() {
        const value = String(process.env.GOHOME_VISION_VERIFICATION_ENABLED || "1").trim().toLowerCase();
        return !["0", "false", "off", "disabled"].includes(value);
    }

    function visionVerificationTimeoutMs() {
        const value = Number(process.env.GOHOME_VISION_VERIFICATION_TIMEOUT_MS || 30000);
        return Number.isFinite(value) && value >= 5000 ? value : 30000;
    }

    function visionVerificationMaxAttempts() {
        const value = Number(process.env.GOHOME_VISION_VERIFICATION_MAX_ATTEMPTS || 3);
        return Number.isFinite(value) ? Math.max(1, Math.min(5, Math.round(value))) : 3;
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

    function imageGenerationTimeoutMs() {
        const value = Number(process.env.GOHOME_CARE_IMAGE_TIMEOUT_MS || 120000);
        return Number.isFinite(value) && value >= 30000 ? value : 120000;
    }

    function providerRequestTimeoutMs() {
        const value = Number(process.env.GOHOME_PROVIDER_REQUEST_TIMEOUT_MS || 12000);
        return Number.isFinite(value) && value >= 2000 ? value : 12000;
    }

    function careImageSize() {
        const value = String(process.env.GOHOME_CARE_IMAGE_SIZE || "1280*960").trim();
        return /^\d{3,4}\*\d{3,4}$/.test(value) ? value : "1280*960";
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
        const verification = visionVerificationRuntimeConfig();
        const image = imageRuntimeConfig();
        const weather = weatherRuntimeConfig();
        const contentSearch = contentSearchRuntimeConfig();
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
                capability_id: "vision-event-verification",
                name: "守护事件视觉复核",
                type: "multimodal_language",
                scope: "safety_event_evidence",
                configured: Boolean(verification.base_url && verification.api_key && verification.model),
                enabled: Boolean(visionVerificationEnabled() && verification.base_url && verification.api_key && verification.model),
                base_url_set: Boolean(verification.base_url),
                api_key_set: Boolean(verification.api_key),
                model: verification.model,
                purpose_label: "跌倒、长时间倒地和火灾事件图片复核",
                prompt: verification.prompt,
                prompt_source: verification.prompt_source,
                env_keys: {
                    enabled: ["GOHOME_VISION_VERIFICATION_ENABLED"],
                    prompt: ["GOHOME_VISION_VERIFICATION_PROMPT"],
                },
                output_contract: "VisionVerification JSON: person_count/posture/surface/emergency/confidence/reason/suggested_event_type",
            },
            {
                capability_id: "care-card-image",
                name: "生图模型",
                type: "image_generation",
                scope: "care_card_image_4x3",
                configured: Boolean(image.base_url && image.api_key && image.model),
                enabled: Boolean(image.base_url && image.api_key && image.model),
                base_url_set: Boolean(image.base_url),
                api_key_set: Boolean(image.api_key),
                model: image.model,
                purpose_label: "4:3 无字生活场景图生成",
                aspect_ratio: "4:3",
                prompt: image.prompt,
                prompt_source: image.prompt_source,
                env_keys: {
                    base_url: ["GOHOME_IMAGE_BASE_URL", "GOHOME_WAN_BASE_URL", "DASHSCOPE_BASE_URL", "WAN_BASE_URL"],
                    api_key: ["GOHOME_IMAGE_API_KEY", "GOHOME_WAN_API_KEY", "DASHSCOPE_API_KEY", "WAN_API_KEY"],
                    model: ["GOHOME_IMAGE_MODEL", "GOHOME_WAN_MODEL", "WAN_MODEL"],
                    prompt: ["GOHOME_CARE_IMAGE_PROMPT"],
                },
                output_contract: "4:3 text-free editorial lifestyle image; copy is rendered by the app",
            },
            {
                capability_id: "weather-signals",
                name: "天气数据源",
                type: "weather_provider",
                scope: "care_card_weather_context",
                configured: weather.provider === "open-meteo" || Boolean(weather.provider === "qweather" && weather.api_key),
                enabled: !["none", "off", "disabled"].includes(weather.provider),
                base_url_set: Boolean(weather.base_url),
                api_key_set: Boolean(weather.api_key) || weather.provider === "open-meteo",
                model: weather.provider,
                purpose_label: "每日关怀天气上下文",
                env_keys: {
                    provider: ["GOHOME_WEATHER_PROVIDER"],
                    base_url: ["GOHOME_QWEATHER_BASE_URL", "QWEATHER_BASE_URL", "GOHOME_WEATHER_BASE_URL"],
                    geo_base_url: ["GOHOME_QWEATHER_GEO_BASE_URL", "QWEATHER_GEO_BASE_URL"],
                    api_key: ["GOHOME_QWEATHER_API_KEY", "QWEATHER_API_KEY", "HEFENG_WEATHER_API_KEY", "GOHOME_WEATHER_API_KEY"],
                    auth_mode: ["GOHOME_QWEATHER_AUTH_MODE", "QWEATHER_AUTH_MODE"],
                },
                output_contract: "WeatherSignal: city/condition/temperature/humidity/advice/source",
            },
            {
                capability_id: "content-search",
                name: "内容搜索源",
                type: "content_search",
                scope: "elder_interest_topic_candidates",
                configured: Boolean(contentSearch.provider === "tavily" && contentSearch.api_key),
                enabled: contentSearch.provider === "tavily",
                base_url_set: Boolean(contentSearch.base_url),
                api_key_set: Boolean(contentSearch.api_key),
                model: contentSearch.provider,
                purpose_label: "老人兴趣热点和文章视频候选",
                env_keys: {
                    provider: ["GOHOME_SEARCH_PROVIDER", "GOHOME_CONTENT_SEARCH_PROVIDER"],
                    base_url: ["GOHOME_TAVILY_BASE_URL", "TAVILY_BASE_URL", "GOHOME_SEARCH_BASE_URL"],
                    api_key: ["GOHOME_TAVILY_API_KEY", "TAVILY_API_KEY", "GOHOME_SEARCH_API_KEY"],
                    max_results: ["GOHOME_TAVILY_MAX_RESULTS"],
                },
                output_contract: "ContentRecommendation[]: title/url/source/summary/topic",
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

    function cookieMap(req) {
        return Object.fromEntries(String(req.headers.cookie || "")
            .split(";")
            .map((part) => part.trim())
            .filter(Boolean)
            .map((part) => {
                const equalsIndex = part.indexOf("=");
                if (equalsIndex < 0) return [part, ""];
                const key = part.slice(0, equalsIndex).trim();
                const value = part.slice(equalsIndex + 1).trim();
                try {
                    return [key, decodeURIComponent(value)];
                } catch (_error) {
                    return [key, value];
                }
            }));
    }

    function appSessionCookieHeader(token) {
        const encoded = encodeURIComponent(String(token || ""));
        return `gohome_app_session=${encoded}; Max-Age=2592000; Path=/; SameSite=Lax`;
    }

    function clearAppSessionCookieHeader() {
        return "gohome_app_session=; Max-Age=0; Path=/; SameSite=Lax";
    }

    function tokenFrom(req) {
        const header = String(req.headers.authorization || "");
        const match = header.match(/^Bearer\s+(.+)$/i);
        if (match) return match[1].trim();
        return cookieMap(req).gohome_app_session || "";
    }

    function sessionForToken(token) {
        if (!token) return null;
        const tokenHash = sha256(token);
        const now = Date.now();
        return [...store.db.app_sessions]
            .reverse()
            .find((session) => (
                session.status === "active"
                && (session.token === token || session.token_hash === tokenHash)
                && (!session.expires_at || Date.parse(session.expires_at) > now)
            )) || null;
    }

    function issueAppSession(user) {
        const token = `app_${crypto.randomBytes(18).toString("hex")}`;
        const timestamp = nowIso();
        const session = {
            id: `session-${crypto.randomUUID()}`,
            token,
            token_hash: sha256(token),
            user_id: user.id,
            status: "active",
            created_at: timestamp,
            updated_at: timestamp,
            last_seen_at: timestamp,
            expires_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
            revoked_at: null,
        };
        store.db.app_sessions.push(session);
        return session;
    }

    function isLocalRequest(req) {
        const address = normalizeRemoteAddress(req.socket?.remoteAddress || "");
        return address === "127.0.0.1" || address === "localhost";
    }

    function isLocalBrowserRequest(req) {
        const rawHost = String(req.headers.host || "").split(":")[0].trim().toLowerCase();
        return ["127.0.0.1", "localhost", "::1", "[::1]"].includes(rawHost);
    }

    function cloudDeviceClaimsEnabled() {
        const configured = String(process.env.GOHOME_ALLOW_CLOUD_DEVICE_CLAIMS || "").trim().toLowerCase();
        if (configured) return ["1", "true", "yes", "on"].includes(configured);
        return process.env.NODE_ENV !== "production";
    }

    function issuedDeviceTokenFromRequest(req) {
        const token = tokenFrom(req);
        const tokenHash = sha256(token);
        return store.db.device_tokens.find((item) => item.status === "active" && (
            item.token === token || (item.token_hash && item.token_hash === tokenHash)
        )) || null;
    }

    function requireDevice(req, res) {
        const token = tokenFrom(req);
        const issued = issuedDeviceTokenFromRequest(req);
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
            if (ticket.user_id) req.appUserId = ticket.user_id;
            return true;
        }
        const session = sessionForToken(token);
        if (session) {
            session.last_seen_at = nowIso();
            req.appUserId = session.user_id;
            return true;
        }
        if (token === appToken) {
            req.appUserId = store.db.active_user_id;
            return true;
        }
        if (token !== appToken) {
            writeError(res, 401, "请先登录回家 App。");
            return false;
        }
        req.appUserId = store.db.active_user_id;
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
        const phone = user.phone || phoneFromAccountEmail(user.email);
        return {
            id: user.id,
            email: user.email,
            phone,
            display_name: user.display_name,
            created_at: user.created_at,
        };
    }

    function activeAppUser(req = null) {
        const userId = req?.appUserId || store.db.active_user_id;
        return store.db.users.find((item) => Number(item.id) === Number(userId))
            || [...store.db.users].reverse().find((item) => item.email !== "admin@gohome.local")
            || store.db.users[0];
    }

    function familyIdsForUser(userId) {
        const ids = store.db.family_members
            .filter((item) => String(item.status || "active") === "active" && Number(item.user_id) === Number(userId))
            .map((item) => Number(item.family_id));
        return new Set(ids);
    }

    function familiesForUser(userId) {
        const ids = familyIdsForUser(userId);
        return store.db.families.filter((family) => ids.has(Number(family.id)));
    }

    function syncFamilyMemberCount(familyId) {
        const family = selectedFamily(familyId);
        if (!family) return null;
        family.member_count = store.db.family_members.filter((item) => (
            String(item.status || "active") === "active"
            && Number(item.family_id) === Number(familyId)
        )).length || 1;
        family.updated_at = nowIso();
        return family;
    }

    function ensureFamilyMember(familyId, userId, role = "owner") {
        let member = store.db.family_members.find((item) => (
            Number(item.family_id) === Number(familyId)
            && Number(item.user_id) === Number(userId)
        ));
        if (!member) {
            member = {
                id: `${familyId}:${role}:${userId}`,
                family_id: Number(familyId),
                user_id: Number(userId),
                role,
                status: "active",
                joined_at: nowIso(),
                created_at: nowIso(),
                updated_at: nowIso(),
            };
            store.db.family_members.push(member);
        } else {
            member.status = "active";
            member.role = member.role || role;
            member.updated_at = nowIso();
        }
        syncFamilyMemberCount(familyId);
        return member;
    }

    function userCanAccessFamily(userId, familyId) {
        return familyIdsForUser(userId).has(Number(familyId));
    }

    function familyMemberForUser(userId, familyId) {
        return store.db.family_members.find((item) => (
            Number(item.family_id) === Number(familyId)
            && Number(item.user_id) === Number(userId)
            && String(item.status || "active") === "active"
        )) || null;
    }

    function userCanManageFamily(userId, familyId) {
        const family = selectedFamily(familyId);
        const member = familyMemberForUser(userId, familyId);
        return Boolean(member && family && Number(family.created_by_user_id) === Number(userId));
    }

    function requireFamilyAccess(req, res, familyId) {
        const user = activeAppUser(req);
        if (!selectedFamily(familyId)) {
            writeError(res, 404, "family not found");
            return false;
        }
        if (!userCanAccessFamily(user.id, familyId)) {
            writeError(res, 403, "当前账号无权访问该家庭。");
            return false;
        }
        return true;
    }

    function requireFamilyOwner(req, res, familyId) {
        if (!requireFamilyAccess(req, res, familyId)) return false;
        const user = activeAppUser(req);
        if (!userCanManageFamily(user.id, familyId)) {
            writeError(res, 403, "只有家庭创建者可以修改这项配置。");
            return false;
        }
        return true;
    }

    function publicFamily(family) {
        const activeMembers = store.db.family_members.filter((item) => (
            String(item.status || "active") === "active"
            && Number(item.family_id) === Number(family.id)
        )).length;
        return {
            id: family.id,
            name: family.name,
            member_count: activeMembers || Number(family.member_count || 1),
            join_code: familyJoinCode(family),
            created_at: family.created_at,
            updated_at: family.updated_at || family.created_at,
        };
    }

    function familyJoinCode(family) {
        if (!family) return "";
        const hash = sha256(`${family.id}:${family.created_at || ""}:${family.name || ""}`).slice(0, 6).toUpperCase();
        return `GH-${family.id}-${hash}`;
    }

    function familyForJoinCode(code) {
        const normalized = String(code || "").trim().toUpperCase().replace(/\s+/g, "");
        if (!normalized) return null;
        const match = normalized.match(/^GH-?(\d+)-?([A-F0-9]{6})$/i);
        if (!match) return null;
        const family = selectedFamily(Number(match[1]));
        if (!family) return null;
        return familyJoinCode(family).replace(/\s+/g, "").toUpperCase() === normalized ? family : null;
    }

    function selectedFamily(familyId = null) {
        if (familyId !== null && familyId !== undefined && familyId !== "") {
            return store.db.families.find((item) => Number(item.id) === Number(familyId)) || null;
        }
        return null;
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
            district: "",
            phone: "",
            mobile_phone: "",
            home_phone: "",
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

    function ensureElderProfile(familyId, elderId = "elder_primary") {
        const family = selectedFamily(familyId);
        if (!family) return null;
        const key = elderProfileKey(family.id, elderId);
        if (!store.db.elder_profiles[key]) {
            store.db.elder_profiles[key] = defaultElderProfile(family.id, elderId);
        }
        return store.db.elder_profiles[key];
    }

    function existingElderProfile(familyId, elderId = "elder_primary") {
        const family = selectedFamily(familyId);
        if (!family) return null;
        return store.db.elder_profiles[elderProfileKey(family.id, elderId)] || null;
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

    function objectValue(value) {
        return value && typeof value === "object" && !Array.isArray(value) ? value : {};
    }

    function normalizeClaimCode(value) {
        return String(value || "").trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
    }

    function deviceSerial(deviceOrId = {}) {
        const device = typeof deviceOrId === "object" && deviceOrId ? deviceOrId : store.db.devices[String(deviceOrId)] || {};
        const deviceId = String(device.device_id || device.id || deviceOrId || "").trim();
        const metadata = objectValue(device.metadata);
        const existing = String(metadata.serial_number || device.serial_number || "").trim();
        if (existing) return existing;
        const suffix = normalizeClaimCode(deviceId).slice(-8) || crypto.randomBytes(4).toString("hex").toUpperCase();
        return `GH-${suffix}`;
    }

    function ensureDeviceMetadata(deviceId, patch = {}) {
        const key = String(deviceId || "").trim();
        if (!key) return {};
        const device = store.db.devices[key] || { id: key, device_id: key, name: "回家盒子", status: "online" };
        const metadata = {
            ...objectValue(device.metadata),
            ...objectValue(patch),
        };
        metadata.serial_number = String(metadata.serial_number || deviceSerial({ ...device, metadata })).trim();
        store.db.devices[key] = {
            ...device,
            id: key,
            device_id: key,
            metadata,
            updated_at: nowIso(),
        };
        return metadata;
    }

    function deviceHasActiveBinding(deviceId) {
        return store.db.device_bindings.some((item) => (
            String(item.device_id || "") === String(deviceId || "")
            && String(item.status || "active") !== "revoked"
        ));
    }

    function deviceBoundToOtherFamily(deviceId, familyId) {
        return store.db.device_bindings.some((item) => (
            String(item.device_id || "") === String(deviceId || "")
            && String(item.status || "active") !== "revoked"
            && Number(item.family_id) !== Number(familyId)
        ));
    }

    function publicClaimableDevice(device) {
        const deviceId = String(device.device_id || device.id || "");
        const metadata = ensureDeviceMetadata(deviceId);
        return {
            device_id: deviceId,
            serial_number: metadata.serial_number || deviceSerial(device),
            name: device.name || "回家盒子",
            status: device.status || "online",
            last_seen_at: device.last_seen_at || null,
            claim_status: deviceHasActiveBinding(deviceId) || device.family_id ? "bound" : "claimable",
        };
    }

    function claimCodeMatchesDevice(device, claimCode) {
        const normalized = normalizeClaimCode(claimCode);
        if (!normalized) return false;
        const metadata = ensureDeviceMetadata(device.device_id || device.id);
        const configuredClaim = normalizeClaimCode(process.env.GOHOME_DEVICE_CLAIM_CODE || "");
        if (configuredClaim && normalized === configuredClaim) return true;
        const hash = String(metadata.claim_code_hash || "").trim();
        if (hash && sha256(normalized) === hash) return true;
        const serial = normalizeClaimCode(metadata.serial_number || deviceSerial(device));
        const deviceId = normalizeClaimCode(device.device_id || device.id || "");
        if (serial && normalized === serial) return true;
        if (deviceId && (normalized === deviceId || normalized === deviceId.slice(-8) || normalized === deviceId.slice(-12))) return true;
        return false;
    }

    function bindDeviceToFamily({ familyId, deviceId, deviceName = "回家盒子", note = "", userId = null }) {
        const normalizedFamilyId = normalizeNumber(familyId, null);
        const normalizedDeviceId = String(deviceId || "").trim();
        if (!normalizedFamilyId || !normalizedDeviceId || !selectedFamily(normalizedFamilyId)) return null;
        let binding = store.db.device_bindings.find((item) => (
            Number(item.family_id) === Number(normalizedFamilyId)
            && String(item.device_id) === normalizedDeviceId
        ));
        if (!binding) {
            binding = {
                id: store.nextId("binding"),
                family_id: normalizedFamilyId,
                device_id: normalizedDeviceId,
                device_name: String(deviceName || "回家盒子"),
                device_type: "edge-agent",
                status: "active",
                note: String(note || ""),
                bound_at: nowIso(),
                created_at: nowIso(),
                updated_at: nowIso(),
            };
            store.db.device_bindings.push(binding);
        } else {
            binding.status = "active";
            binding.device_name = String(deviceName || binding.device_name || "回家盒子");
            binding.note = String(note || binding.note || "");
            binding.updated_at = nowIso();
        }

        const existingDevice = store.db.devices[normalizedDeviceId] || {};
        const metadata = {
            ...objectValue(existingDevice.metadata),
            serial_number: objectValue(existingDevice.metadata).serial_number || deviceSerial({ ...existingDevice, device_id: normalizedDeviceId }),
            claim_status: "bound",
            claimed_at: nowIso(),
            claimed_by_family_id: normalizedFamilyId,
            claimed_by_user_id: userId || null,
        };
        store.db.devices[normalizedDeviceId] = {
            ...existingDevice,
            id: normalizedDeviceId,
            device_id: normalizedDeviceId,
            family_id: normalizedFamilyId,
            name: binding.device_name || existingDevice.name || "回家盒子",
            device_type: existingDevice.device_type || "edge-agent",
            status: existingDevice.status || "active",
            metadata,
            updated_at: nowIso(),
        };
        store.db.device_tokens.forEach((token) => {
            if (String(token.device_id || "") === normalizedDeviceId && token.status === "active") {
                token.family_id = normalizedFamilyId;
                token.updated_at = nowIso();
            }
        });
        return binding;
    }

    function unbindDeviceFromFamily({ familyId, bindingId = "", deviceId = "" }) {
        const normalizedFamilyId = normalizeNumber(familyId, null);
        const binding = store.db.device_bindings.find((item) => (
            Number(item.family_id) === Number(normalizedFamilyId)
            && String(item.status || "active") !== "revoked"
            && (!bindingId || String(item.id) === String(bindingId))
            && (!deviceId || String(item.device_id) === String(deviceId))
        ));
        if (!binding) return null;

        const normalizedDeviceId = String(binding.device_id || "").trim();
        const timestamp = nowIso();
        store.db.device_bindings.forEach((item) => {
            if (String(item.device_id || "") !== normalizedDeviceId) return;
            if (String(item.status || "active") === "revoked") return;
            item.status = "revoked";
            item.updated_at = timestamp;
            item.unbound_at = timestamp;
        });
        store.db.device_tokens.forEach((token) => {
            if (String(token.device_id || "") !== normalizedDeviceId) return;
            token.status = "revoked";
            token.revoked_at = timestamp;
            token.updated_at = timestamp;
        });

        const removedCameraIds = Object.values(store.db.cameras)
            .filter((camera) => (
                Number(camera.family_id) === Number(normalizedFamilyId)
                && String(camera.device_id || "") === normalizedDeviceId
            ))
            .map((camera) => String(camera.id));
        detachCameraReferences(removedCameraIds, timestamp);
        removedCameraIds.forEach((cameraId) => {
            delete store.db.cameras[cameraId];
        });

        const existingDevice = store.db.devices[normalizedDeviceId] || {};
        store.db.devices[normalizedDeviceId] = {
            ...existingDevice,
            id: normalizedDeviceId,
            device_id: normalizedDeviceId,
            family_id: null,
            metadata: {
                ...objectValue(existingDevice.metadata),
                claim_status: "claimable",
                claimed_by_family_id: null,
                claimed_by_user_id: null,
                unbound_at: timestamp,
            },
            updated_at: timestamp,
        };
        return {
            binding,
            device: store.db.devices[normalizedDeviceId],
            removed_camera_count: removedCameraIds.length,
            removed_camera_ids: removedCameraIds,
        };
    }

    function detachCameraReferences(cameraIds, timestamp = nowIso()) {
        const ids = new Set((cameraIds || []).map(String));
        if (!ids.size) return;
        for (const asset of store.db.assets) {
            if (!ids.has(String(asset.camera_id || ""))) continue;
            asset.camera_id = null;
            asset.updated_at = timestamp;
        }
        for (const event of store.db.events) {
            if (!ids.has(String(event.camera_id || ""))) continue;
            event.camera_id = null;
            event.updated_at = timestamp;
        }
    }

    async function deletePersistedRows(rows) {
        if (typeof store.deleteRow !== "function") return;
        for (const item of rows || []) {
            await store.deleteRow(item.table, item.id);
        }
    }

    function cleanupVerifyData(options = {}) {
        const dryRun = normalizeBool(options.dry_run || options.dryRun);
        const idText = (value) => String(value ?? "");
        const verifyUsers = store.db.users.filter((user) => (
            /^verify-[^@]+@gohome\.local$/i.test(String(user.email || ""))
            || /^流程自检/.test(String(user.display_name || ""))
        ));
        const verifyUserIds = new Set(verifyUsers.map((user) => idText(user.id)));
        const verifyFamilies = store.db.families.filter((family) => /^流程自检-/.test(String(family.name || "")));
        const verifyFamilyIds = new Set(verifyFamilies.map((family) => idText(family.id)));
        const verifyDeviceIds = new Set(store.db.device_bindings
            .filter((binding) => verifyFamilyIds.has(idText(binding.family_id)) || /^verify-onboarding-/.test(String(binding.device_id || "")))
            .map((binding) => idText(binding.device_id)));
        const verifyCameraIds = new Set(Object.values(store.db.cameras || {})
            .filter((camera) => verifyFamilyIds.has(idText(camera.family_id)))
            .map((camera) => idText(camera.id)));
        const deleted = {};
        const persistenceDeletes = [];

        function countArray(key, predicate, table = key, primaryKey = (item) => item.id) {
            const items = Array.isArray(store.db[key]) ? store.db[key] : [];
            const removed = items.filter(predicate);
            const removeCount = removed.length;
            deleted[key] = removeCount;
            if (!dryRun && removeCount) {
                removed.forEach((item) => persistenceDeletes.push({ table, id: idText(primaryKey(item)) }));
                store.db[key] = items.filter((item) => !predicate(item));
            }
        }

        function countObject(key, predicate, table = key, primaryKey = (value, entryKey) => value.id || entryKey) {
            const object = store.db[key] && typeof store.db[key] === "object" ? store.db[key] : {};
            const entries = Object.entries(object);
            const removed = entries.filter(([entryKey, value]) => predicate(value, entryKey));
            const removeCount = removed.length;
            deleted[key] = removeCount;
            if (!dryRun && removeCount) {
                removed.forEach(([entryKey, value]) => persistenceDeletes.push({ table, id: idText(primaryKey(value, entryKey)) }));
                store.db[key] = Object.fromEntries(entries.filter(([entryKey, value]) => !predicate(value, entryKey)));
            }
        }

        countArray("app_sessions", (session) => verifyUserIds.has(idText(session.user_id)));
        countArray("family_members", (member) => verifyUserIds.has(idText(member.user_id)) || verifyFamilyIds.has(idText(member.family_id)));
        countArray("users", (user) => verifyUserIds.has(idText(user.id)));
        countArray("families", (family) => verifyFamilyIds.has(idText(family.id)));
        countArray("device_bindings", (binding) => (
            verifyFamilyIds.has(idText(binding.family_id))
            || verifyDeviceIds.has(idText(binding.device_id))
        ));
        countArray("binding_codes", (code) => verifyFamilyIds.has(idText(code.family_id)));
        countArray("device_tokens", (token) => verifyFamilyIds.has(idText(token.family_id)) || verifyDeviceIds.has(idText(token.device_id)));
        countArray("heartbeats", (heartbeat) => verifyDeviceIds.has(idText(heartbeat.device_id)), "device_heartbeats");
        countObject("devices", (device, key) => verifyDeviceIds.has(idText(device.device_id || device.id || key)), "devices", (device, key) => device.device_id || device.id || key);
        countObject("cameras", (camera) => verifyFamilyIds.has(idText(camera.family_id)));
        countArray("assets", (asset) => verifyFamilyIds.has(idText(asset.family_id)) || verifyCameraIds.has(idText(asset.camera_id)), "media_assets");
        countArray("events", (event) => verifyFamilyIds.has(idText(event.family_id)) || verifyCameraIds.has(idText(event.camera_id)));
        countArray("calendar_events", (event) => verifyFamilyIds.has(idText(event.family_id)));
        countObject("elder_profiles", (profile, key) => verifyFamilyIds.has(idText(profile.family_id)) || [...verifyFamilyIds].some((familyId) => String(key).startsWith(`${familyId}:`)), "elder_profiles", (profile, key) => `${profile.family_id || String(key).split(":")[0]}:${profile.elder_id || String(key).split(":")[1] || "elder_primary"}`);
        countObject("care_preferences", (preferences, key) => verifyFamilyIds.has(idText(preferences.family_id)) || verifyFamilyIds.has(idText(key)), "care_preferences", (preferences, key) => preferences.family_id || key);
        countObject("family_rules", (_rules, key) => verifyFamilyIds.has(idText(key)), "care_rules", (_rules, key) => `${key}:edge_rules`);
        countArray("care_cards", (card) => verifyFamilyIds.has(idText(card.family_id)));
        countArray("app_messages", (message) => verifyFamilyIds.has(idText(message.family_id)) || verifyUserIds.has(idText(message.user_id)));
        countArray("notification_deliveries", (delivery) => verifyFamilyIds.has(idText(delivery.family_id)) || verifyUserIds.has(idText(delivery.user_id)));
        countArray("app_push_tokens", (token) => verifyFamilyIds.has(idText(token.family_id)) || verifyUserIds.has(idText(token.user_id)));
        countArray("scheduler_runs", (run) => verifyFamilyIds.has(idText(run.family_id)));
        countArray("model_generation_jobs", (job) => verifyFamilyIds.has(idText(job.family_id)));
        countArray("content_sources", (source) => verifyFamilyIds.has(idText(source.family_id)));
        countArray("content_recommendations", (recommendation) => verifyFamilyIds.has(idText(recommendation.family_id)));

        if (!dryRun) {
            if (verifyUserIds.has(idText(store.db.active_user_id))) {
                const replacement = store.db.users.find((user) => !verifyUserIds.has(idText(user.id)) && user.email !== "admin@gohome.local")
                    || store.db.users.find((user) => !verifyUserIds.has(idText(user.id)))
                    || null;
                store.db.active_user_id = replacement?.id || null;
            }
            for (const family of store.db.families) {
                family.member_count = store.db.family_members.filter((member) => (
                    String(member.status || "active") === "active"
                    && Number(member.family_id) === Number(family.id)
                )).length || 1;
                family.updated_at = family.updated_at || nowIso();
            }
        }

        return {
            ok: true,
            dry_run: dryRun,
            targets: {
                users: verifyUsers.map((user) => ({ id: user.id, email: user.email })),
                families: verifyFamilies.map((family) => ({ id: family.id, name: family.name })),
            },
            deleted,
            persistence_deletes: persistenceDeletes,
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
            family_id: normalizeNumber(payload.family_id, existing.family_id ?? null),
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

    function appConfigCameras(familyIds = null) {
        const allowedFamilyIds = familyIds instanceof Set ? familyIds : null;
        return Object.values(store.db.cameras).filter((camera) => {
            if (!isAppConfiguredCamera(camera)) return false;
            if (!allowedFamilyIds) return true;
            if (!camera.family_id) return false;
            return allowedFamilyIds.has(Number(camera.family_id));
        });
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
        const localCameraIds = [
            camera.local_camera_id,
            camera.edge_camera_id,
            camera.local_id,
            cameraId,
        ]
            .map((value) => normalizeNumber(value, null))
            .filter(Boolean)
            .filter((value, index, values) => values.indexOf(value) === index);
        if (!localCameraIds.length) return null;
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
            localCameraIds,
            token: streamProxyTokenForDevice(camera.device_id || device.device_id || device.id),
        };
    }

    function cameraConfigVersion(familyId = null) {
        const familyIds = familyId ? new Set([Number(familyId)]) : null;
        const cameras = appConfigCameras(familyIds);
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

    function fallbackRulesFamilyId() {
        const binding = store.db.device_bindings.find((item) => String(item.status || "active") !== "revoked");
        return normalizeNumber(binding?.family_id || store.db.families[0]?.id, null);
    }

    function currentRules(familyId = null) {
        const resolvedFamilyId = normalizeNumber(familyId, fallbackRulesFamilyId());
        store.db.rules = normalizeRules(store.db.rules || defaultRules(), store.db.rules || defaultRules());
        store.db.family_rules = store.db.family_rules && typeof store.db.family_rules === "object"
            ? store.db.family_rules
            : {};
        if (!resolvedFamilyId) return store.db.rules;
        const key = String(resolvedFamilyId);
        store.db.family_rules[key] = normalizeRules(store.db.family_rules[key] || store.db.rules, store.db.rules);
        return store.db.family_rules[key];
    }

    function deviceVisionCapabilities(device = {}, cameras = []) {
        const runtime = device.runtime && typeof device.runtime === "object" ? device.runtime : {};
        const worker = runtime.worker && typeof runtime.worker === "object" ? runtime.worker : {};
        const reported = {
            ...((device.vision_capabilities && typeof device.vision_capabilities === "object") ? device.vision_capabilities : {}),
            ...((runtime.vision_capabilities && typeof runtime.vision_capabilities === "object") ? runtime.vision_capabilities : {}),
            ...((worker.vision_capabilities && typeof worker.vision_capabilities === "object") ? worker.vision_capabilities : {}),
        };
        const backend = String(device.detector_backend || runtime.detector_backend || worker.detector_backend || "").trim().toLowerCase();
        const demoCamera = Array.isArray(cameras) && cameras.some((camera) => String(camera.stream_url || "").trim().toLowerCase().startsWith("demo:"));
        const modelBackends = new Set(["yolo", "demo", "rtmpose", "pose"]);
        const anyCapability = (...values) => values.some((value) => normalizeBool(value));
        const poseEnabled = anyCapability(
            reported.pose_detection,
            runtime.pose_enabled,
            runtime.pose_detection_enabled,
            worker.pose_enabled,
            worker.pose_detection_enabled,
            backend === "rtmpose",
            backend === "pose"
        );
        const modelReported = normalizeBool(reported.person_detection)
            || modelBackends.has(backend)
            || Boolean(device.yolo_model || runtime.yolo_model || worker.yolo_model)
            || demoCamera;
        const backendLabel = reported.backend_label
            || (backend === "yolo"
                ? "YOLO 人形模型"
                : backend === "demo"
                    ? "演示视觉管线"
                    : backend === "rtmpose" || backend === "pose" || poseEnabled
                        ? "RTMPose 姿态模型"
                        : backend === "basic"
                            ? "基础视觉检测"
                            : "盒子视觉管线");
        return {
            quality_detection: true,
            motion_detection: true,
            person_detection: modelReported,
            no_person_detection: normalizeBool(reported.no_person_detection) || modelReported,
            fall_candidate: normalizeBool(reported.fall_candidate) || modelReported || poseEnabled,
            activity_candidate: reported.activity_candidate === undefined ? true : normalizeBool(reported.activity_candidate),
            fire_candidate: reported.fire_candidate === undefined ? true : normalizeBool(reported.fire_candidate),
            pose_detection: poseEnabled,
            backend: backend || "unknown",
            backend_label: backendLabel,
        };
    }

    function rulesVersion(familyId = null) {
        return `rules-${crypto.createHash("sha1").update(JSON.stringify(currentRules(familyId))).digest("hex").slice(0, 12)}`;
    }

    function deviceConfigVersion(familyId = null) {
        return `device-config-${crypto.createHash("sha1").update(`${cameraConfigVersion(familyId)}|${rulesVersion(familyId)}`).digest("hex").slice(0, 12)}`;
    }

    function deviceCameraConfig(camera) {
        return {
            id: camera.id,
            camera_id: camera.id,
            family_id: camera.family_id || null,
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

    function deviceConfigPayload(options = {}) {
        const familyId = normalizeNumber(options.family_id ?? options.familyId, null);
        const familyIds = familyId ? new Set([familyId]) : new Set();
        const device = store.db.devices[String(options.device_id || currentEdgeDeviceId())] || {};
        return {
            ok: true,
            device_id: options.device_id || currentEdgeDeviceId(),
            generated_at: nowIso(),
            config_version: deviceConfigVersion(familyId),
            cameras: appConfigCameras(familyIds).map(deviceCameraConfig),
            rules: currentRules(familyId),
            rules_version: rulesVersion(familyId),
            maintenance: objectValue(objectValue(device.metadata).maintenance_command),
        };
    }

    function publicEvent(event) {
        const camera = store.db.cameras[String(event.camera_id)] || {};
        const asset = event.media_asset_id
            ? store.db.assets.find((item) => Number(item.id) === Number(event.media_asset_id))
            : null;
        const evidenceMedia = (event.payload?.evidence_media_assets || [])
            .map((entry) => {
                const evidenceAsset = store.db.assets.find((item) => Number(item.id) === Number(entry?.asset_id || entry?.id));
                if (!evidenceAsset) return null;
                return {
                    asset_id: evidenceAsset.id,
                    role: entry.role || evidenceAsset.evidence_frame_role || "evidence",
                    captured_at: entry.captured_at || evidenceAsset.captured_at || evidenceAsset.created_at || "",
                    postures: Array.isArray(entry.postures) ? entry.postures : [],
                };
            })
            .filter(Boolean)
            .slice(0, 3);
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
            updated_at: event.updated_at || event.created_at,
            acknowledged: Boolean(event.acknowledged),
            resolution: event.resolution || "",
            snapshot_path: event.snapshot_path || asset?.snapshot_path || "",
            snapshot_url: event.snapshot_path || asset?.snapshot_path || "",
            media_asset_id: asset?.id || null,
            evidence_media: evidenceMedia,
            payload: event.payload || {},
        };
    }

    function publicEventSummary(event) {
        const camera = store.db.cameras[String(event.camera_id)] || {};
        const asset = event.media_asset_id
            ? store.db.assets.find((item) => Number(item.id) === Number(event.media_asset_id))
            : null;
        const incident = event.payload?.incident || null;
        const verification = event.payload?.verification || null;
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
            updated_at: event.updated_at || event.created_at,
            acknowledged: Boolean(event.acknowledged),
            resolution: event.resolution || "",
            snapshot_path: event.snapshot_path || asset?.snapshot_path || "",
            snapshot_url: event.snapshot_path || asset?.snapshot_path || "",
            media_asset_id: asset?.id || null,
            payload: {
                ...(incident ? { incident: {
                    status: incident.status || "",
                    primary_event_id: incident.primary_event_id || event.id,
                } } : {}),
                ...(verification ? { verification: {
                    status: verification.status || "",
                    decision: verification.decision || "",
                } } : {}),
            },
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
                local_hotspots: true,
                health_tips: true,
                anti_fraud: false,
                culture_entertainment: true,
                weather: true,
                holidays: true,
                anniversaries: true,
                visit_reminder: true,
            },
            content_region: {
                city: "",
                district: "",
            },
            interest_topics: ["养生", "天气", "戏曲", "家常", "本地生活"],
            message_focus: "用轻松自然的语气提醒今天家里状态，顺带给一个适合打电话时聊的话题。",
            visit_reminder: {
                enabled: true,
                threshold_days: 14,
                location_tracking_enabled: false,
                last_visit_at: "",
                next_visit_at: "",
            },
            delivery_rules: {
                daily_digest: { enabled: true, mode: "daily_digest" },
                home_status: { enabled: true, mode: "daily_digest_plus_exception", exception_push_enabled: true },
                elder_interest_topics: { enabled: true, mode: "daily_digest" },
                local_hotspots: { enabled: true, mode: "daily_digest_region" },
                health_tips: { enabled: true, mode: "daily_digest" },
                anti_fraud: { enabled: false, mode: "low_frequency" },
                culture_entertainment: { enabled: true, mode: "daily_digest" },
                weather: { enabled: true, mode: "daily_digest_provider" },
                holidays: { enabled: true, mode: "holiday_window", days_before: 1 },
                anniversaries: { enabled: true, mode: "annual_window", days_before: 3 },
                visit_reminder: { enabled: true, mode: "threshold", threshold_days: 14 },
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
        const contentRegion = input.content_region && typeof input.content_region === "object" ? input.content_region : {};
        const visitReminder = input.visit_reminder && typeof input.visit_reminder === "object" ? input.visit_reminder : {};
        const deliveryRules = input.delivery_rules && typeof input.delivery_rules === "object" ? input.delivery_rules : {};
        const ruleObject = (key) => deliveryRules[key] && typeof deliveryRules[key] === "object" ? deliveryRules[key] : {};
        return {
            enabled: "enabled" in input ? normalizeBool(input.enabled) : defaults.enabled,
            delivery_time: normalizeTimeOfDay(input.delivery_time, defaults.delivery_time),
            timezone: String(input.timezone || defaults.timezone),
            channels: normalizeStringList(input.channels, defaults.channels, 6),
            content_types: {
                home_status: "home_status" in contentTypes ? normalizeBool(contentTypes.home_status) : defaults.content_types.home_status,
                elder_interest_topics: "elder_interest_topics" in contentTypes ? normalizeBool(contentTypes.elder_interest_topics) : defaults.content_types.elder_interest_topics,
                local_hotspots: "local_hotspots" in contentTypes ? normalizeBool(contentTypes.local_hotspots) : defaults.content_types.local_hotspots,
                health_tips: "health_tips" in contentTypes ? normalizeBool(contentTypes.health_tips) : defaults.content_types.health_tips,
                anti_fraud: "anti_fraud" in contentTypes ? normalizeBool(contentTypes.anti_fraud) : defaults.content_types.anti_fraud,
                culture_entertainment: "culture_entertainment" in contentTypes ? normalizeBool(contentTypes.culture_entertainment) : defaults.content_types.culture_entertainment,
                weather: "weather" in contentTypes ? normalizeBool(contentTypes.weather) : defaults.content_types.weather,
                holidays: "holidays" in contentTypes ? normalizeBool(contentTypes.holidays) : defaults.content_types.holidays,
                anniversaries: "anniversaries" in contentTypes ? normalizeBool(contentTypes.anniversaries) : defaults.content_types.anniversaries,
                visit_reminder: "visit_reminder" in contentTypes ? normalizeBool(contentTypes.visit_reminder) : defaults.content_types.visit_reminder,
            },
            content_region: {
                city: String(contentRegion.city || defaults.content_region.city || "").trim().slice(0, 24),
                district: String(contentRegion.district || defaults.content_region.district || "").trim().slice(0, 24),
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
                next_visit_at: /^\d{4}-\d{2}-\d{2}$/.test(String(visitReminder.next_visit_at || ""))
                    ? String(visitReminder.next_visit_at)
                    : "",
            },
            delivery_rules: {
                daily_digest: {
                    enabled: "enabled" in ruleObject("daily_digest") ? normalizeBool(ruleObject("daily_digest").enabled) : defaults.delivery_rules.daily_digest.enabled,
                    mode: String(ruleObject("daily_digest").mode || defaults.delivery_rules.daily_digest.mode),
                },
                home_status: {
                    enabled: "enabled" in ruleObject("home_status") ? normalizeBool(ruleObject("home_status").enabled) : defaults.delivery_rules.home_status.enabled,
                    mode: String(ruleObject("home_status").mode || defaults.delivery_rules.home_status.mode),
                    exception_push_enabled: "exception_push_enabled" in ruleObject("home_status")
                        ? normalizeBool(ruleObject("home_status").exception_push_enabled)
                        : defaults.delivery_rules.home_status.exception_push_enabled,
                },
                elder_interest_topics: {
                    enabled: "enabled" in ruleObject("elder_interest_topics") ? normalizeBool(ruleObject("elder_interest_topics").enabled) : defaults.delivery_rules.elder_interest_topics.enabled,
                    mode: String(ruleObject("elder_interest_topics").mode || defaults.delivery_rules.elder_interest_topics.mode),
                },
                local_hotspots: {
                    enabled: "enabled" in ruleObject("local_hotspots") ? normalizeBool(ruleObject("local_hotspots").enabled) : defaults.delivery_rules.local_hotspots.enabled,
                    mode: String(ruleObject("local_hotspots").mode || defaults.delivery_rules.local_hotspots.mode),
                },
                health_tips: {
                    enabled: "enabled" in ruleObject("health_tips") ? normalizeBool(ruleObject("health_tips").enabled) : defaults.delivery_rules.health_tips.enabled,
                    mode: String(ruleObject("health_tips").mode || defaults.delivery_rules.health_tips.mode),
                },
                anti_fraud: {
                    enabled: "enabled" in ruleObject("anti_fraud") ? normalizeBool(ruleObject("anti_fraud").enabled) : defaults.delivery_rules.anti_fraud.enabled,
                    mode: String(ruleObject("anti_fraud").mode || defaults.delivery_rules.anti_fraud.mode),
                },
                culture_entertainment: {
                    enabled: "enabled" in ruleObject("culture_entertainment") ? normalizeBool(ruleObject("culture_entertainment").enabled) : defaults.delivery_rules.culture_entertainment.enabled,
                    mode: String(ruleObject("culture_entertainment").mode || defaults.delivery_rules.culture_entertainment.mode),
                },
                weather: {
                    enabled: "enabled" in ruleObject("weather") ? normalizeBool(ruleObject("weather").enabled) : defaults.delivery_rules.weather.enabled,
                    mode: String(ruleObject("weather").mode || defaults.delivery_rules.weather.mode),
                },
                holidays: {
                    enabled: "enabled" in ruleObject("holidays") ? normalizeBool(ruleObject("holidays").enabled) : defaults.delivery_rules.holidays.enabled,
                    mode: String(ruleObject("holidays").mode || defaults.delivery_rules.holidays.mode),
                    days_before: Math.min(30, Math.max(0, normalizeNumber(ruleObject("holidays").days_before, defaults.delivery_rules.holidays.days_before))),
                },
                anniversaries: {
                    enabled: "enabled" in ruleObject("anniversaries") ? normalizeBool(ruleObject("anniversaries").enabled) : defaults.delivery_rules.anniversaries.enabled,
                    mode: String(ruleObject("anniversaries").mode || defaults.delivery_rules.anniversaries.mode),
                    days_before: Math.min(30, Math.max(0, normalizeNumber(ruleObject("anniversaries").days_before, defaults.delivery_rules.anniversaries.days_before))),
                },
                visit_reminder: {
                    enabled: "enabled" in ruleObject("visit_reminder") ? normalizeBool(ruleObject("visit_reminder").enabled) : defaults.delivery_rules.visit_reminder.enabled,
                    mode: String(ruleObject("visit_reminder").mode || defaults.delivery_rules.visit_reminder.mode),
                    threshold_days: Math.min(90, Math.max(1, normalizeNumber(ruleObject("visit_reminder").threshold_days, visitReminder.threshold_days || defaults.delivery_rules.visit_reminder.threshold_days))),
                },
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

    function normalizePresenceMonitoring(value = {}) {
        const source = value && typeof value === "object" ? value : {};
        const allowedModes = new Set(["active", "away", "travel", "hospital", "paused", "paused_until"]);
        const mode = allowedModes.has(String(source.mode || "")) ? String(source.mode) : "active";
        const parsedPausedUntil = Date.parse(source.paused_until || "");
        return {
            enabled: "enabled" in source ? normalizeBool(source.enabled) : true,
            mode,
            paused_until: Number.isFinite(parsedPausedUntil) ? new Date(parsedPausedUntil).toISOString() : "",
            reason: String(source.reason || "").trim().slice(0, 120),
            updated_at: String(source.updated_at || nowIso()),
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
            content_recommendations_enabled: true,
            content_sources_enabled: true,
            metadata: normalizeCareMetadata(),
            updated_at: nowIso(),
        };
    }

    function carePreferences(familyId) {
        const key = String(familyId || "");
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

    function publicAppMessage(message) {
        return {
            id: message.message_id || message.id,
            message_id: message.message_id || message.id,
            family_id: message.family_id,
            user_id: message.user_id || "",
            care_card_id: message.care_card_id || "",
            event_id: message.event_id || "",
            message_type: message.message_type || "care",
            title: message.title || "",
            subtitle: message.subtitle || "",
            body: message.body || "",
            facts: Array.isArray(message.facts) ? message.facts : [],
            actions: Array.isArray(message.actions) ? message.actions : [],
            source: Array.isArray(message.source) ? message.source : [],
            source_event_ids: Array.isArray(message.source_event_ids) ? message.source_event_ids : [],
            priority: message.priority || "normal",
            status: message.status || "open",
            generated_by: message.generated_by || "notification-service",
            scheduled_for: message.scheduled_for || "",
            delivered_at: message.delivered_at || "",
            read_at: message.read_at || "",
            created_at: message.created_at,
            updated_at: message.updated_at,
        };
    }

    function publicNotificationDelivery(delivery) {
        return {
            id: delivery.id,
            family_id: delivery.family_id,
            user_id: delivery.user_id || "",
            message_id: delivery.message_id || "",
            channel: delivery.channel || "app_push",
            provider: delivery.provider || "app_message",
            target_type: delivery.target_type || "family",
            target_id: delivery.target_id || "",
            status: delivery.status || "queued",
            title: delivery.title || "",
            body: delivery.body || "",
            error_message: delivery.error_message || "",
            scheduled_for: delivery.scheduled_for || "",
            sent_at: delivery.sent_at || "",
            delivered_at: delivery.delivered_at || "",
            clicked_at: delivery.clicked_at || "",
            created_at: delivery.created_at,
            updated_at: delivery.updated_at,
        };
    }

    function publicAppPushToken(token) {
        return {
            id: token.id,
            family_id: token.family_id,
            user_id: token.user_id || "",
            app_install_id: token.app_install_id || "",
            platform: token.platform || "",
            token_preview: token.token_preview || "",
            status: token.status || "active",
            device_name: token.device_name || "",
            app_version: token.app_version || "",
            last_seen_at: token.last_seen_at || "",
            created_at: token.created_at,
            updated_at: token.updated_at,
        };
    }

    function appPushProviderConfigured() {
        return Boolean(envFirst(["GOHOME_APNS_KEY_ID", "GOHOME_APNS_AUTH_KEY", "GOHOME_PUSH_PROVIDER"]));
    }

    function tokenPreview(value) {
        const text = String(value || "").trim();
        if (!text) return "";
        if (text.length <= 10) return "***";
        return `${text.slice(0, 4)}...${text.slice(-4)}`;
    }

    function upsertAppMessage(payload = {}) {
        const timestamp = nowIso();
        const familyId = normalizeNumber(payload.family_id, null);
        if (!familyId) throw new Error("family_id required for app message");
        const messageId = String(payload.message_id || `msg-${familyId}-${sha256(JSON.stringify(payload)).slice(0, 16)}`);
        const idempotencyKey = String(payload.idempotency_key || messageId);
        let message = store.db.app_messages.find((item) => (
            String(item.message_id || item.id) === messageId
            || String(item.idempotency_key || "") === idempotencyKey
        ));
        const patch = {
            message_id: messageId,
            family_id: familyId,
            user_id: payload.user_id || "",
            care_card_id: String(payload.care_card_id || ""),
            event_id: String(payload.event_id || ""),
            message_type: String(payload.message_type || "care"),
            title: String(payload.title || "一条新的关怀提醒").trim().slice(0, 80),
            subtitle: String(payload.subtitle || "").trim().slice(0, 160),
            body: String(payload.body || "").trim().slice(0, 600),
            facts: normalizeStringList(payload.facts, [], 6),
            actions: Array.isArray(payload.actions) ? payload.actions.slice(0, 6) : [],
            source: Array.isArray(payload.source) ? payload.source.slice(0, 8) : [],
            source_event_ids: normalizeStringList(payload.source_event_ids, [], 12),
            priority: String(payload.priority || "normal"),
            status: String(payload.status || "open"),
            generated_by: String(payload.generated_by || "notification-service"),
            idempotency_key: idempotencyKey,
            metadata: payload.metadata && typeof payload.metadata === "object" ? payload.metadata : {},
            scheduled_for: payload.scheduled_for || "",
            delivered_at: payload.delivered_at || "",
            updated_at: timestamp,
        };
        if (!message) {
            message = {
                id: store.nextId("app_message"),
                ...patch,
                read_at: "",
                created_at: timestamp,
            };
            store.db.app_messages.push(message);
        } else {
            Object.assign(message, {
                ...patch,
                status: message.status === "read" && patch.status === "open" ? "read" : patch.status,
                read_at: message.read_at || "",
            });
        }
        return message;
    }

    function queueNotificationDelivery(message, options = {}) {
        const timestamp = nowIso();
        const familyId = normalizeNumber(message.family_id, null);
        if (!familyId) return [];
        const channel = String(options.channel || "app_push");
        const activeTokens = store.db.app_push_tokens.filter((token) => (
            Number(token.family_id) === Number(familyId)
            && String(token.status || "active") === "active"
        ));
        const targets = activeTokens.length
            ? activeTokens.map((token) => ({ type: "push_token", id: token.id, user_id: token.user_id || "" }))
            : [{ type: "family", id: String(familyId), user_id: "" }];
        const deliveries = [];
        for (const target of targets) {
            const idempotencyKey = [
                "delivery",
                message.message_id || message.id,
                channel,
                target.type,
                target.id,
            ].join(":");
            let delivery = store.db.notification_deliveries.find((item) => String(item.idempotency_key || "") === idempotencyKey);
            const hasPushProvider = appPushProviderConfigured();
            const status = target.type === "push_token"
                ? (hasPushProvider ? "queued" : "simulated")
                : "app_message_only";
            const patch = {
                family_id: familyId,
                user_id: target.user_id || message.user_id || "",
                message_id: message.message_id || message.id,
                channel,
                provider: hasPushProvider ? "apns" : "app_message",
                target_type: target.type,
                target_id: String(target.id || ""),
                status,
                title: message.title || "",
                body: message.subtitle || message.body || "",
                error_message: hasPushProvider || target.type !== "push_token" ? "" : "APNs provider not configured; recorded as in-app delivery.",
                request_payload: {
                    message_type: message.message_type,
                    priority: message.priority,
                    actions: message.actions || [],
                },
                response_payload: {},
                idempotency_key: idempotencyKey,
                scheduled_for: options.scheduled_for || message.scheduled_for || "",
                updated_at: timestamp,
            };
            if (!delivery) {
                delivery = {
                    id: store.nextId("notification_delivery"),
                    ...patch,
                    sent_at: status === "simulated" || status === "app_message_only" ? timestamp : "",
                    delivered_at: status === "simulated" || status === "app_message_only" ? timestamp : "",
                    clicked_at: "",
                    created_at: timestamp,
                };
                store.db.notification_deliveries.push(delivery);
            } else {
                Object.assign(delivery, patch);
            }
            deliveries.push(delivery);
        }
        if (!message.delivered_at) message.delivered_at = timestamp;
        message.updated_at = timestamp;
        return deliveries;
    }

    function shanghaiTimeParts(date = new Date()) {
        return new Intl.DateTimeFormat("en-GB", {
            timeZone: "Asia/Shanghai",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
        }).formatToParts(date).reduce((acc, part) => {
            if (part.type !== "literal") acc[part.type] = part.value;
            return acc;
        }, {});
    }

    function timeOfDayMinutes(value) {
        const match = String(value || "").trim().match(/^(\d{2}):(\d{2})$/);
        if (!match) return null;
        return Number(match[1]) * 60 + Number(match[2]);
    }

    function currentShanghaiMinutes(date = new Date()) {
        const parts = shanghaiTimeParts(date);
        return Number(parts.hour || 0) * 60 + Number(parts.minute || 0);
    }

    function dailyCareMessageId(familyId, dateKey = dateKeyShanghai()) {
        return `care-daily-${familyId}-${dateKey}`;
    }

    function dailyCareDue(familyId, schedule, options = {}) {
        if (options.force) return true;
        if (!schedule?.enabled || schedule.delivery_rules?.daily_digest?.enabled === false) return false;
        const dueMinutes = timeOfDayMinutes(schedule.delivery_time || "08:30");
        if (dueMinutes !== null && currentShanghaiMinutes() < dueMinutes) return false;
        const existing = store.db.app_messages.find((message) => (
            Number(message.family_id) === Number(familyId)
            && String(message.message_id || "") === dailyCareMessageId(familyId)
        ));
        return !existing;
    }

    function createCareCardMessage(card, preferences, options = {}) {
        const schedule = preferences.metadata?.care_card_schedule || defaultCareSchedule();
        const family = selectedFamily(card.family_id) || {};
        const dateKey = card.card_date || dateKeyShanghai();
        const message = upsertAppMessage({
            message_id: dailyCareMessageId(card.family_id, dateKey),
            idempotency_key: `daily-care:${card.family_id}:${dateKey}`,
            family_id: card.family_id,
            care_card_id: card.card_id,
            message_type: "care_card",
            title: card.title || "今日关怀已生成",
            subtitle: `${family.name || "当前家庭"} · ${schedule.delivery_time || "08:30"} 每日汇总`,
            body: card.body || "今日关怀卡片已经生成。",
            facts: Array.isArray(card.facts) ? card.facts.slice(0, 3) : [],
            actions: [
                { key: "open_care_card", label: "查看关怀卡" },
                { key: "call", label: "打电话问候" },
                { key: "message", label: "发微信问候" },
            ],
            source: [
                { type: "care_card", id: card.card_id },
                { type: "schedule", delivery_time: schedule.delivery_time || "08:30" },
            ],
            priority: "normal",
            generated_by: card.generated_by ? `scheduler:${card.generated_by}` : "scheduler",
            scheduled_for: options.scheduled_for || "",
        });
        if (!Array.isArray(card.source_message_ids)) card.source_message_ids = [];
        if (!card.source_message_ids.includes(message.message_id)) {
            card.source_message_ids.push(message.message_id);
            card.updated_at = nowIso();
        }
        return message;
    }

    function createEventAlertMessage(event) {
        const camera = store.db.cameras[String(event.camera_id)] || {};
        return upsertAppMessage({
            message_id: `event-alert-${event.id}`,
            idempotency_key: `event-alert:${event.id}`,
            family_id: event.family_id || camera.family_id,
            event_id: event.id,
            message_type: event.level === "critical" ? "alert" : "explain",
            title: event.event_type === "camera_offline"
                ? `${event.camera_name || event.room || "摄像头"} 暂时没有返回画面`
                : (event.summary || "家里有提醒待确认"),
            subtitle: `${event.room || event.camera_name || "摄像头"} · ${event.event_type}`,
            body: event.event_type === "camera_offline"
                ? "家庭盒子暂时没有拿到这路画面，会继续重试。"
                : (event.payload?.rule?.reason || event.summary || "请先查看事件证据，再联系家里。"),
            facts: [event.event_type, event.level].filter(Boolean),
            actions: [{ key: "open_event", label: "查看事件" }],
            source_event_ids: [event.id],
            source: [{ type: "event", id: event.id }],
            priority: event.level === "critical" ? "high" : "normal",
            generated_by: "event-notification-service",
        });
    }

    const SAFETY_INCIDENT_TYPES = new Set([
        "fall_candidate",
        "prolonged_floor_lying",
        "fire_candidate",
        "long_absence",
    ]);

    const INCIDENT_REMINDER_STATUSES = new Set(["active", "verifying", "confirmed", "uncertain"]);

    function incidentCorrelationWindowMs() {
        return Math.max(5000, normalizeNumber(process.env.GOHOME_INCIDENT_CORRELATION_WINDOW_SECONDS, 45) * 1000);
    }

    function incidentEvents(incidentId) {
        const cleanId = String(incidentId || "");
        if (!cleanId) return [];
        return store.db.events.filter((item) => String(item.payload?.incident?.incident_id || "") === cleanId);
    }

    function incidentPrimaryEvent(event) {
        const incident = event?.payload?.incident || {};
        const primaryId = incident.primary_event_id || event?.id;
        return store.db.events.find((item) => String(item.id) === String(primaryId)) || event;
    }

    function appendIncidentTransition(event, status, source, details = {}) {
        const incident = ensureSafetyIncident(event);
        if (!incident) return null;
        const transitions = Array.isArray(incident.transitions) ? incident.transitions : [];
        const previous = transitions[transitions.length - 1];
        if (previous?.status === status && previous?.source === source) return incident;
        transitions.push({
            status,
            source,
            at: nowIso(),
            ...details,
        });
        incident.transitions = transitions.slice(-24);
        incident.status = status;
        return incident;
    }

    function correlateSafetyIncident(event) {
        if (!SAFETY_INCIDENT_TYPES.has(event.event_type) || event.event_type === "long_absence" || isValidationEvent(event)) return null;
        const occurredAt = Date.parse(event.occurred_at || event.created_at || nowIso());
        const match = store.db.events
            .filter((item) => (
                Number(item.family_id) === Number(event.family_id)
                && item.event_type === event.event_type
                && !isValidationEvent(item)
                && !item.acknowledged
                && !["rejected", "resolved", "acknowledged"].includes(String(item.payload?.incident?.status || ""))
            ))
            .filter((item) => {
                const existingAt = Date.parse(item.occurred_at || item.created_at || "");
                return Number.isFinite(existingAt) && Number.isFinite(occurredAt)
                    && Math.abs(occurredAt - existingAt) <= incidentCorrelationWindowMs();
            })
            .sort((a, b) => Date.parse(a.occurred_at || a.created_at || "") - Date.parse(b.occurred_at || b.created_at || ""))[0];
        if (!match) return null;
        const primary = incidentPrimaryEvent(match);
        const primaryIncident = ensureSafetyIncident(primary);
        event.payload = event.payload && typeof event.payload === "object" ? event.payload : {};
        event.payload.incident = {
            ...primaryIncident,
            incident_id: primaryIncident.incident_id,
            primary_event_id: primary.id,
            source_event_ids: [...new Set([...(primaryIncident.source_event_ids || [primary.id]), event.id])],
            source_camera_ids: [...new Set([...(primaryIncident.source_camera_ids || [primary.camera_id]), event.camera_id].filter(Boolean))],
        };
        primaryIncident.source_event_ids = event.payload.incident.source_event_ids;
        primaryIncident.source_camera_ids = event.payload.incident.source_camera_ids;
        primary.updated_at = nowIso();
        return primary;
    }

    function ensureSafetyIncident(event) {
        if (!SAFETY_INCIDENT_TYPES.has(event.event_type)) return null;
        event.payload = event.payload && typeof event.payload === "object" ? event.payload : {};
        const existing = event.payload.incident && typeof event.payload.incident === "object" ? event.payload.incident : {};
        const defaultStatus = VISION_VERIFICATION_EVENT_TYPES.has(event.event_type) ? "verifying" : "confirmed";
        event.payload.incident = {
            incident_id: existing.incident_id || `incident-${event.idempotency_key || event.id}`,
            primary_event_id: existing.primary_event_id || event.id,
            status: event.acknowledged ? "acknowledged" : (existing.status || defaultStatus),
            started_at: existing.started_at || event.occurred_at || event.created_at || nowIso(),
            acknowledged_at: existing.acknowledged_at || "",
            resolved_at: existing.resolved_at || "",
            last_reminder_bucket: existing.last_reminder_bucket || "",
            reminder_count: Number(existing.reminder_count || 0),
            source_event_ids: [...new Set([...(existing.source_event_ids || []), event.id])],
            source_camera_ids: [...new Set([...(existing.source_camera_ids || []), event.camera_id].filter(Boolean))],
            transitions: Array.isArray(existing.transitions) ? existing.transitions.slice(-24) : [],
        };
        return event.payload.incident;
    }

    function archiveIncidentMessages(incidentId, options = {}) {
        const eventIds = new Set(incidentEvents(incidentId).map((event) => String(event.id)));
        for (const message of store.db.app_messages) {
            const sources = Array.isArray(message.source_event_ids) ? message.source_event_ids.map(String) : [];
            const incidentSource = (message.source || []).some((item) => (
                item?.type === "safety_incident" && String(item.id || "") === String(incidentId)
            ));
            if (!incidentSource && !sources.some((id) => eventIds.has(id))) continue;
            if (options.except_message_id && String(message.message_id || message.id) === String(options.except_message_id)) continue;
            message.status = "archived";
            message.updated_at = nowIso();
        }
    }

    function createVerificationOutcomeMessage(event, status, verification = {}) {
        const primary = incidentPrimaryEvent(event);
        if (isValidationEvent(primary)) return null;
        const incident = ensureSafetyIncident(primary);
        if (!incident || !primary.family_id) return null;
        const result = verification.result || {};
        const copies = {
            confirmed: {
                title: primary.summary || "家中异常已经确认",
                subtitle: `${primary.room || primary.camera_name || "家里"} · 云端复核确认`,
                body: result.reason || "云端视觉模型支持边缘端异常判断，请尽快查看并联系老人。",
                priority: "high",
                message_type: "alert",
            },
            rejected: {
                title: "刚才的异常已经排除",
                subtitle: `${primary.room || primary.camera_name || "家里"} · 云端复核完成`,
                body: result.reason || "云端复核未发现需要告警的异常，原始记录仍会保留用于追溯。",
                priority: "normal",
                message_type: "explain",
            },
            uncertain: {
                title: "这条异常需要你确认",
                subtitle: `${primary.room || primary.camera_name || "家里"} · 云端无法明确判断`,
                body: result.reason || verification.error || "云端复核证据不足，请查看事件截图并联系老人确认。",
                priority: "high",
                message_type: "alert",
            },
        };
        const copy = copies[status];
        if (!copy) return null;
        const messageId = `incident-verification-${incident.incident_id}-${status}`;
        return upsertAppMessage({
            message_id: messageId,
            idempotency_key: messageId,
            family_id: primary.family_id,
            event_id: primary.id,
            message_type: copy.message_type,
            title: copy.title,
            subtitle: copy.subtitle,
            body: copy.body,
            facts: [primary.event_type, status, result.confidence !== undefined ? `置信度 ${Math.round(Number(result.confidence) * 100)}%` : ""].filter(Boolean),
            actions: [{ key: "open_event", label: status === "rejected" ? "查看记录" : "查看事件", event_id: primary.id }],
            source_event_ids: incident.source_event_ids || [primary.id],
            source: [{ type: "safety_incident", id: incident.incident_id }],
            priority: copy.priority,
            generated_by: "vision-verification-orchestrator",
            metadata: { verification_status: status, model: verification.model || "" },
        });
    }

    function aggregateIncidentVerification(event) {
        const incident = ensureSafetyIncident(event);
        if (!incident) return "confirmed";
        if (incidentEvents(incident.incident_id).some((item) => item.payload?.manual_feedback?.resolution === "false_positive")) {
            return "rejected";
        }
        const statuses = incidentEvents(incident.incident_id)
            .map((item) => String(item.payload?.verification?.status || ""))
            .filter(Boolean);
        if (statuses.includes("confirmed")) return "confirmed";
        if (statuses.some((status) => ["uncertain", "failed", "unavailable"].includes(status))) return "uncertain";
        if (statuses.some((status) => ["pending", "verifying", "retrying"].includes(status))) return "verifying";
        if (statuses.length && statuses.every((status) => status === "rejected")) return "rejected";
        return incident.status || "verifying";
    }

    function applyIncidentVerificationOutcome(event) {
        const primary = incidentPrimaryEvent(event);
        const primaryIncident = ensureSafetyIncident(primary);
        if (!primaryIncident) return { status: "not_applicable", message: null, deliveries: [] };
        const nextStatus = aggregateIncidentVerification(primary);
        const previousStatus = primaryIncident.status;
        for (const linked of incidentEvents(primaryIncident.incident_id)) {
            const incident = ensureSafetyIncident(linked);
            incident.status = nextStatus;
            incident.primary_event_id = primary.id;
            incident.source_event_ids = primaryIncident.source_event_ids;
            incident.source_camera_ids = primaryIncident.source_camera_ids;
            linked.updated_at = nowIso();
        }
        appendIncidentTransition(primary, nextStatus, "vision_verification", {
            event_id: event.id,
            verification_status: event.payload?.verification?.status || "",
        });
        if (nextStatus === "rejected") {
            primary.resolution = "vision_rejected";
            archiveIncidentMessages(primaryIncident.incident_id);
        }
        if (nextStatus === previousStatus || nextStatus === "verifying") {
            return { status: nextStatus, message: null, deliveries: [] };
        }
        const message = createVerificationOutcomeMessage(primary, nextStatus, event.payload?.verification || {});
        const deliveries = message ? queueNotificationDelivery(message) : [];
        return { status: nextStatus, message, deliveries };
    }

    function acknowledgeSafetyIncident(event, resolution = "handled") {
        const incident = ensureSafetyIncident(event);
        if (!incident) return [event];
        const linkedEvents = incidentEvents(incident.incident_id);
        for (const linked of linkedEvents) {
            linked.acknowledged = true;
            linked.resolution = resolution || linked.resolution || "handled";
            const linkedIncident = ensureSafetyIncident(linked);
            linkedIncident.status = "acknowledged";
            linkedIncident.acknowledged_at = nowIso();
            linked.updated_at = nowIso();
        }
        appendIncidentTransition(incidentPrimaryEvent(event), "acknowledged", "app_user", { resolution });
        archiveIncidentMessages(incident.incident_id);
        return linkedEvents;
    }

    function rejectSafetyIncidentAsFalsePositive(event) {
        const incident = ensureSafetyIncident(event);
        const linkedEvents = incident ? incidentEvents(incident.incident_id) : [event];
        const timestamp = nowIso();
        for (const linked of linkedEvents) {
            linked.payload = linked.payload && typeof linked.payload === "object" ? linked.payload : {};
            linked.payload.manual_feedback = {
                resolution: "false_positive",
                source: "edge_admin",
                updated_at: timestamp,
            };
            linked.resolution = "false_positive";
            linked.acknowledged = false;
            const linkedIncident = ensureSafetyIncident(linked);
            if (linkedIncident) {
                linkedIncident.status = "rejected";
                linkedIncident.resolved_at = timestamp;
            }
            linked.updated_at = timestamp;
        }
        if (incident) {
            appendIncidentTransition(incidentPrimaryEvent(event), "rejected", "edge_admin", { resolution: "false_positive" });
            archiveIncidentMessages(incident.incident_id);
        }
        return linkedEvents;
    }

    function incidentMinuteBucket(date = new Date()) {
        return date.toISOString().slice(0, 16);
    }

    function createIncidentReminderMessage(event, bucket = incidentMinuteBucket()) {
        if (isValidationEvent(event)) return null;
        const incident = ensureSafetyIncident(event);
        if (!incident || event.acknowledged || !INCIDENT_REMINDER_STATUSES.has(incident.status)) return null;
        if (incident.last_reminder_bucket === bucket) return null;
        const incidentAgeMs = Date.now() - Date.parse(incident.started_at || event.occurred_at || "");
        if (!Number.isFinite(incidentAgeMs) || incidentAgeMs < 60000) return null;
        const message = upsertAppMessage({
            message_id: `incident-reminder-${event.id}-${bucket}`,
            idempotency_key: `incident-reminder:${event.id}:${bucket}`,
            family_id: event.family_id,
            event_id: event.id,
            message_type: "alert",
            title: event.summary || "家里有紧急提醒待确认",
            subtitle: `${event.room || event.camera_name || "家里"} · 尚未确认收到`,
            body: event.event_type === "long_absence"
                ? "所有守护摄像头持续未检测到老人，请尽快联系家里确认情况。"
                : "这条安全提醒尚未确认收到，请尽快查看事件并联系老人。",
            facts: [event.event_type, `提醒 ${incident.reminder_count + 1} 次`],
            actions: [{ key: "open_event", label: "立即确认", event_id: event.id }],
            source_event_ids: [event.id],
            source: [{ type: "safety_incident", id: incident.incident_id }],
            priority: "high",
            generated_by: "incident-reminder",
        });
        incident.last_reminder_bucket = bucket;
        incident.reminder_count += 1;
        return message;
    }

    function familyPresenceThresholdSeconds() {
        return Math.max(60, normalizeNumber(process.env.GOHOME_LONG_ABSENCE_SECONDS, 12 * 60 * 60));
    }

    function petActivityRecentSeconds() {
        return Math.max(300, normalizeNumber(process.env.GOHOME_PET_ACTIVITY_RECENT_SECONDS, 6 * 60 * 60));
    }

    function cameraPresenceObservationState(camera, now = Date.now(), options = {}) {
        const minCoverage = options.min_coverage ?? Math.max(0.1, Math.min(1, normalizeNumber(process.env.GOHOME_PRESENCE_MIN_COVERAGE, 0.5)));
        const maxReportAgeMs = options.max_report_age_ms ?? Math.max(30000, normalizeNumber(process.env.GOHOME_PRESENCE_REPORT_MAX_AGE_SECONDS, 120) * 1000);
        const reportedAt = camera.presence?.reported_at || camera.edge_reported_at || "";
        const reportAgeMs = now - Date.parse(reportedAt);
        const online = camera.status === "online";
        const synced = camera.sync_status === "synced";
        const fresh = Number.isFinite(reportAgeMs) && reportAgeMs <= maxReportAgeMs;
        const coverage = Number(camera.presence?.observation_coverage || 0);
        const coverageValid = coverage >= minCoverage;
        const valid = online && synced && fresh && coverageValid;
        let reason = "valid";
        if (!online) reason = "camera_offline";
        else if (!synced) reason = "config_not_synced";
        else if (!fresh) reason = "report_stale";
        else if (!coverageValid) reason = "coverage_insufficient";
        return {
            valid,
            reason,
            report_age_seconds: Number.isFinite(reportAgeMs) ? Math.max(0, Math.floor(reportAgeMs / 1000)) : null,
            observation_coverage: coverage,
        };
    }

    function familyPresenceState(family) {
        const now = Date.now();
        const monitoring = normalizePresenceMonitoring(carePreferences(family.id).metadata?.presence_monitoring || {});
        const pauseMode = String(monitoring.mode || "active");
        const pausedUntil = Date.parse(monitoring.paused_until || "");
        const paused = monitoring.enabled === false
            || ["away", "travel", "hospital", "paused"].includes(pauseMode)
            || (Number.isFinite(pausedUntil) && pausedUntil > now);
        const cameras = Object.values(store.db.cameras).filter((camera) => (
            Number(camera.family_id) === Number(family.id) && camera.enabled !== false
        ));
        const cameraObservationStates = cameras.map((camera) => cameraPresenceObservationState(camera, now));
        const validCameraCount = cameraObservationStates.filter((item) => item.valid).length;
        const valid = !paused && cameras.length > 0 && validCameraCount === cameras.length;
        const previous = family.presence_state && typeof family.presence_state === "object" ? family.presence_state : {};
        const seenTimes = cameras
            .map((camera) => Date.parse(camera.presence?.last_person_seen_at || ""))
            .filter(Number.isFinite);
        const lastPersonSeenMs = seenTimes.length ? Math.max(...seenTimes) : null;
        const petSeenTimes = cameras
            .map((camera) => Date.parse(camera.presence?.last_pet_seen_at || ""))
            .filter(Number.isFinite);
        const lastPetSeenMs = petSeenTimes.length ? Math.max(...petSeenTimes) : null;
        const petTypes = [...new Set(cameras.flatMap((camera) => (
            Array.isArray(camera.presence?.pet_types) ? camera.presence.pet_types : []
        )).map(String).filter(Boolean))];
        const eligibleSince = valid ? (previous.eligible_since || nowIso()) : "";
        const absenceStartedMs = lastPersonSeenMs ?? Date.parse(eligibleSince || "");
        const absenceSeconds = valid && Number.isFinite(absenceStartedMs) ? Math.max(0, Math.floor((now - absenceStartedMs) / 1000)) : null;
        const state = {
            family_id: family.id,
            status: paused ? "paused" : (valid ? (absenceSeconds >= familyPresenceThresholdSeconds() ? "long_absence" : "observing") : "suspended"),
            camera_count: cameras.length,
            valid_camera_count: validCameraCount,
            last_person_seen_at: lastPersonSeenMs ? new Date(lastPersonSeenMs).toISOString() : null,
            last_pet_seen_at: lastPetSeenMs ? new Date(lastPetSeenMs).toISOString() : null,
            pet_types: petTypes,
            pet_activity_recent: Number.isFinite(lastPetSeenMs) && (now - lastPetSeenMs) <= petActivityRecentSeconds() * 1000,
            absence_started_at: Number.isFinite(absenceStartedMs) ? new Date(absenceStartedMs).toISOString() : null,
            absence_seconds: absenceSeconds,
            threshold_seconds: familyPresenceThresholdSeconds(),
            eligible_since: eligibleSince,
            reason: paused
                ? `presence_monitoring_${pauseMode}`
                : (valid ? "coverage_valid" : (cameraObservationStates.find((item) => !item.valid)?.reason || "camera_unavailable")),
            monitoring: {
                enabled: monitoring.enabled,
                mode: pauseMode,
                paused_until: monitoring.paused_until || "",
                reason: String(monitoring.reason || ""),
            },
            updated_at: nowIso(),
        };
        family.presence_state = state;
        return state;
    }

    function reconcileLongAbsenceEvent(family, state) {
        const active = store.db.events.find((event) => (
            Number(event.family_id) === Number(family.id)
            && event.event_type === "long_absence"
            && !event.acknowledged
        ));
        if (state.status !== "long_absence") {
            if (active && state.last_person_seen_at) {
                active.acknowledged = true;
                active.resolution = "person_seen_again";
                const incident = ensureSafetyIncident(active);
                incident.status = "resolved";
                incident.resolved_at = nowIso();
                active.updated_at = nowIso();
            }
            return null;
        }
        if (active) return active;
        const event = {
            id: store.nextId("event"),
            family_id: family.id,
            idempotency_key: `long-absence:${family.id}:${String(state.absence_started_at || state.eligible_since || nowIso()).slice(0, 13)}`,
            edge_event_id: null,
            event_type: "long_absence",
            summary: "长时间没有在家中看到老人",
            level: "critical",
            room: "全屋守护",
            camera_id: null,
            camera_name: "全屋摄像头",
            snapshot_path: "",
            media_asset_id: null,
            occurred_at: nowIso(),
            acknowledged: false,
            resolution: "",
            payload: {
                rule: {
                    id: "long_absence",
                    label: "长时间未见老人",
                    reason: "所有参与守护的摄像头在线且观察覆盖达标，但连续超过设定时长没有可信人体数据。",
                    observed: state,
                    threshold: { absence_seconds: state.threshold_seconds },
                },
                family_presence_state: state,
            },
            created_at: nowIso(),
            updated_at: nowIso(),
        };
        ensureSafetyIncident(event);
        store.db.events.push(event);
        return event;
    }

    async function runNotificationScheduler(options = {}) {
        if (schedulerRunning && !options.allow_concurrent) {
            const result = {
                families_checked: 0,
                care_cards_generated: 0,
                app_messages_created: 0,
                notification_deliveries_created: 0,
                event_alerts_created: 0,
                incident_reminders_created: 0,
                long_absence_events_created: 0,
                skipped: [{ reason: "scheduler_already_running" }],
            };
            return {
                ok: true,
                run: {
                    id: null,
                    family_id: normalizeNumber(options.family_id, null) || null,
                    job_type: String(options.job_type || "care_notification"),
                    status: "skipped",
                    scope: {
                        force: Boolean(options.force),
                        family_id: normalizeNumber(options.family_id, null) || null,
                    },
                    result,
                    error_message: "",
                    started_at: nowIso(),
                    finished_at: nowIso(),
                    created_at: nowIso(),
                    updated_at: nowIso(),
                },
                result,
            };
        }
        schedulerRunning = true;
        const timestamp = nowIso();
        const scopeFamilyId = normalizeNumber(options.family_id, null);
        const run = {
            id: store.nextId("scheduler_run"),
            family_id: scopeFamilyId || null,
            job_type: String(options.job_type || "care_notification"),
            status: "running",
            scope: {
                force: Boolean(options.force),
                family_id: scopeFamilyId || null,
            },
            result: {},
            error_message: "",
            started_at: timestamp,
            finished_at: "",
            created_at: timestamp,
            updated_at: timestamp,
        };
        store.db.scheduler_runs.push(run);
        const result = {
            families_checked: 0,
            care_cards_generated: 0,
            app_messages_created: 0,
            notification_deliveries_created: 0,
            event_alerts_created: 0,
            incident_reminders_created: 0,
            long_absence_events_created: 0,
            skipped: [],
        };
        try {
            const families = store.db.families.filter((family) => (
                (!scopeFamilyId || Number(family.id) === Number(scopeFamilyId))
                && String(family.status || "active") !== "disabled"
            ));
            for (const family of families) {
                result.families_checked += 1;
                const preferences = carePreferences(family.id);
                const schedule = preferences.metadata?.care_card_schedule || defaultCareSchedule();
                const presenceState = familyPresenceState(family);
                const beforePresenceEvents = store.db.events.length;
                const absenceEvent = reconcileLongAbsenceEvent(family, presenceState);
                const createdAbsence = Math.max(0, store.db.events.length - beforePresenceEvents);
                result.long_absence_events_created += createdAbsence;
                if (absenceEvent && createdAbsence) {
                    queueNotificationDelivery(createEventAlertMessage(absenceEvent));
                }
                const safetyEvents = store.db.events.filter((event) => (
                    Number(event.family_id) === Number(family.id)
                    && SAFETY_INCIDENT_TYPES.has(event.event_type)
                    && !event.acknowledged
                    && INCIDENT_REMINDER_STATUSES.has(event.payload?.incident?.status)
                    && String(event.payload?.incident?.primary_event_id || event.id) === String(event.id)
                ));
                for (const event of safetyEvents) {
                    const beforeMessages = store.db.app_messages.length;
                    const reminder = createIncidentReminderMessage(event);
                    if (reminder) queueNotificationDelivery(reminder);
                    result.incident_reminders_created += Math.max(0, store.db.app_messages.length - beforeMessages);
                }
                if (!schedule.enabled) {
                    result.skipped.push({ family_id: family.id, reason: "schedule_disabled" });
                    continue;
                }
                if (dailyCareDue(family.id, schedule, options)) {
                    const beforeMessages = store.db.app_messages.length;
                    const beforeDeliveries = store.db.notification_deliveries.length;
                    const card = await generateCareCard(family.id, { force: Boolean(options.force_generate_card) });
                    const message = createCareCardMessage(card, preferences, {
                        scheduled_for: `${dateKeyShanghai()}T${schedule.delivery_time || "08:30"}:00+08:00`,
                    });
                    queueNotificationDelivery(message, { scheduled_for: message.scheduled_for });
                    result.care_cards_generated += 1;
                    result.app_messages_created += Math.max(0, store.db.app_messages.length - beforeMessages);
                    result.notification_deliveries_created += Math.max(0, store.db.notification_deliveries.length - beforeDeliveries);
                } else {
                    result.skipped.push({ family_id: family.id, reason: "daily_not_due_or_already_sent" });
                }

                const rules = schedule.delivery_rules || {};
                if (rules.home_status?.exception_push_enabled !== false) {
                    const familyIds = new Set([Number(family.id)]);
                    const openEvents = eventList(new URL("/api/app/events?acknowledged=false&limit=20", "http://local"), {
                        userVisible: true,
                        familyIds,
                    }).filter((event) => !event.acknowledged);
                    for (const event of openEvents) {
                        const beforeMessages = store.db.app_messages.length;
                        const beforeDeliveries = store.db.notification_deliveries.length;
                        const message = createEventAlertMessage(event);
                        queueNotificationDelivery(message);
                        result.event_alerts_created += Math.max(0, store.db.app_messages.length - beforeMessages);
                        result.notification_deliveries_created += Math.max(0, store.db.notification_deliveries.length - beforeDeliveries);
                    }
                }
            }
            run.status = "succeeded";
            run.result = result;
            run.finished_at = nowIso();
            run.updated_at = run.finished_at;
            return { ok: true, run, result };
        } catch (error) {
            run.status = "failed";
            run.error_message = error.message || "scheduler failed";
            run.result = result;
            run.finished_at = nowIso();
            run.updated_at = run.finished_at;
            throw error;
        } finally {
            schedulerRunning = false;
        }
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
        const family = selectedFamily(familyId) || {};
        const preferences = parts.preferences || carePreferences(familyId);
        const profile = parts.profile || defaultElderProfile(familyId, preferences.elder_id || "elder_primary");
        const cameras = Array.isArray(parts.cameras) ? parts.cameras : appConfigCameras();
        const device = parts.device || Object.values(store.db.devices)[0] || {};
        const weatherSignal = parts.weather || unavailableWeatherSignal({
            familyId,
            city: profile.city || "杭州",
            provider: weatherRuntimeConfig().provider,
            reason: "not_loaded",
        });
        const contentSignal = parts.content || unavailableContentRecommendations({
            familyId,
            city: profile.city || "杭州",
            topics: contentTopicsFromPreferences(preferences),
            provider: contentSearchRuntimeConfig().provider,
            reason: "not_loaded",
        });
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
            weather: weatherSignal.available
                ? weatherSignal
                : {
                    ...weatherSignal,
                    note: "天气数据不可用时，不要写天气现象、温度、降雨或实时预报。",
                },
            content_recommendations: contentSignal.available
                ? contentSignal.recommendations
                : [],
            content_search: contentSignal.available
                ? {
                    provider: contentSignal.provider,
                    topics: contentSignal.topics,
                    source_policy: contentSignal.source_policy,
                    updated_at: contentSignal.updated_at,
                }
                : {
                    provider: contentSignal.provider,
                    available: false,
                    reason: contentSignal.reason,
                    note: "内容搜索不可用时，只能基于老人兴趣生成通用问候话题，不要编造热点、文章或视频。",
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
        const title = String(parsed.title || "").replace(/\s+/g, " ").trim().slice(0, 24);
        const body = String(parsed.body || "").replace(/\s+/g, " ").trim().slice(0, 120);
        if (!title || !body) return null;
        const facts = Array.isArray(parsed.facts)
            ? parsed.facts.map((item) => String(item || "").replace(/\s+/g, " ").trim().slice(0, 36)).filter(Boolean).slice(0, 3)
            : [];
        const suggestedActions = Array.isArray(parsed.suggested_actions)
            ? parsed.suggested_actions.map((item) => String(item || "").replace(/\s+/g, " ").trim().slice(0, 18)).filter(Boolean).slice(0, 3)
            : [];
        const rawTone = String(parsed.tone || "warm").trim();
        const allowedTones = new Set(["warm", "calm", "alert", "seasonal", "memory"]);
        return {
            title,
            body,
            facts,
            suggested_actions: suggestedActions,
            tone: allowedTones.has(rawTone) ? rawTone : "warm",
            image_brief: String(parsed.image_brief || "").replace(/\s+/g, " ").trim().slice(0, 120),
        };
    }

    function removeUnavailableWeatherClaims(card, context) {
        if (!card) return null;
        if (context?.weather?.available) return card;
        const weatherPattern = /(多云|晴天|晴朗|晴|小雨|中雨|大雨|暴雨|阵雨|雷雨|阴天|阴|降温|升温|气温|温度|\d+\s*度|实时预报|天气预报|梅雨|台风|寒潮|闷热|湿热|凉爽|雨季|回南天|雾霾|空气质量)/;
        const stripWeatherText = (value) => String(value || "")
            .replace(/[^，。；,;]*(多云|晴天|晴朗|晴|小雨|中雨|大雨|暴雨|阵雨|雷雨|阴天|阴|降温|升温|气温|温度|\d+\s*度|实时预报|天气预报|梅雨|台风|寒潮|闷热|湿热|凉爽|雨季|回南天|雾霾|空气质量)[^，。；,;]*[，。；,;]?/g, "")
            .replace(/\s+/g, " ")
            .trim();
        const city = context?.weather?.city || context?.elder?.city || "老人所在城市";
        const next = { ...card };
        if (weatherPattern.test(next.title)) {
            next.title = "家里今天很平稳";
        }
        if (weatherPattern.test(next.body)) {
            const cleaned = stripWeatherText(next.body);
            next.body = cleaned || `设备在线，近 24 小时无高优先级告警。今天先给家里打个电话，聊聊近况和喜欢的内容。`;
        }
        next.facts = (Array.isArray(next.facts) ? next.facts : [])
            .map((item) => weatherPattern.test(item) ? "" : item)
            .filter(Boolean)
            .slice(0, 3);
        if (next.facts.length < 3) {
            next.facts.push(`${city}可作为问候话题`);
        }
        next.suggested_actions = (Array.isArray(next.suggested_actions) ? next.suggested_actions : [])
            .map((item) => weatherPattern.test(item) ? "发一句问候" : item)
            .filter(Boolean)
            .slice(0, 3);
        if (weatherPattern.test(next.image_brief)) {
            next.image_brief = "温暖家居生活场景，电话问候和家常陪伴氛围。";
        }
        return next;
    }

    function contextualCareTheme(context = {}) {
        const weather = context.weather || {};
        const schedule = context.preferences?.care_card_schedule || {};
        const topics = Array.isArray(schedule.interest_topics) && schedule.interest_topics.length
            ? schedule.interest_topics
            : (Array.isArray(context.preferences?.interests) ? context.preferences.interests : []);
        const firstTopic = String(topics[0] || "近况").trim();
        const visitDays = daysSinceDateString(schedule.visit_reminder?.last_visit_at);
        if (Number(context.critical_event_count || 0) > 0) {
            return {
                title: "有提醒待确认",
                body: "家里有一条高优先级事件待确认。先查看事件证据，确认情况后再联系家里。",
                image_brief: "自然日光下的整洁桌面，一部熄屏手机放在触手可及的位置，画面克制安静。",
            };
        }
        if (weather.available) {
            const city = weather.city || context.elder?.city || "当地";
            const condition = weather.condition || "天气";
            const temp = Number.isFinite(Number(weather.temperature_c)) ? `${weather.temperature_c}°C` : "";
            const isHot = Number(weather.temperature_c) >= 30 || /(闷热|炎热|高温|热)/.test(String(weather.advice || ""));
            const weatherTitle = isHot ? "天气有点闷，晚点问问晚饭" : `${condition}天，晚点问问今天怎么过`;
            const observation = `${city}今天${condition}${temp ? `，${temp}` : ""}`;
            return {
                title: weatherTitle.slice(0, 18),
                body: isHot
                    ? `${observation}。傍晚打电话时，问问晚饭吃了什么，话题自然就打开了。`
                    : `${observation}。晚点联系时，从今天有没有出门、晚饭吃什么聊起，会更自然。`,
                image_brief: isHot
                    ? "自然日光下的窗边桌面，一杯清水、几片新鲜柠檬和一部熄屏手机，清爽克制的生活摄影。"
                    : "天气光线映在安静餐桌一角，一只素色杯子和一部熄屏手机，真实自然的生活摄影。",
            };
        }
        if (visitDays !== null) {
            return {
                title: "这个周末，留一点时间回家",
                body: `距离上次回家已经 ${visitDays} 天。先看看周末安排，定不下来也可以今晚打个电话聊聊。`,
                image_brief: "明亮玄关里的钥匙、轻便背包和一双干净便鞋，像正准备出门回家，没有人物。",
            };
        }
        return {
            title: `${firstTopic}，刚好可以当开场`.slice(0, 18),
            body: `今天联系时，可以从${firstTopic}里挑一件具体的小事问起，不用先想一段完整的问候。`,
            image_brief: `自然日光下与${firstTopic}有关的一件日常物品和一部熄屏手机，真实、克制、无人像。`,
        };
    }

    function sanitizeContextualCareCard(card, context) {
        if (!card) return null;
        const genericPattern = /(家里.{0,6}(一切)?(很)?(平稳|安稳|安心)|一切(平稳|安稳)|聊聊家常|多陪陪家人|^今日关怀$|^今日关怀卡片$|今天问个安|打个电话聊聊近况|模型生成的今日关怀)/;
        const directivePattern = /(提醒(多)?喝水|电话里提醒|少久晒|注意身体|多喝水|及时补水|关爱健康|送上关怀)/;
        const impossibleActionPattern = /(递|端|倒|送)(一)?(杯)?(水|茶|热水|温水)|送到(手边|身边)|陪在(身边|旁边)|给.{0,4}(递|端|倒|送)/;
        const next = { ...card };
        const theme = contextualCareTheme(context);
        const weather = context?.weather || {};
        const hotWeather = weather.available && (Number(weather.temperature_c) >= 30 || /(闷热|炎热|高温|热)/.test(String(weather.advice || "")));
        if (genericPattern.test(next.title) || directivePattern.test(next.title) || impossibleActionPattern.test(next.title) || next.title.length > 18) {
            next.title = theme.title;
        }
        next.title = String(next.title || "")
            .replace(/(老人|妈妈|母亲|爸爸|父亲)/g, "家里")
            .replace(/家里家里/g, "家里")
            .trim();
        const weatherTopicMatch = next.title.match(/^[^，,]{1,12}[，,]\s*聊聊(.{2,10})(?:新动态|新消息)?$/);
        if (weatherTopicMatch) {
            const topic = weatherTopicMatch[1].replace(/新动态|新消息/g, "").trim();
            next.title = /(旅行|旅游|文旅)/.test(topic)
                ? `${topic}，问问最近想去哪`.slice(0, 18)
                : `${topic}，刚好可以聊聊`.slice(0, 18);
        }
        if (hotWeather && (directivePattern.test(next.title) || /(一切|安稳|平稳|安心)/.test(next.title))) {
            next.title = theme.title;
        }
        next.body = String(next.body || "")
            .replace(/家里一切平稳[，,、 ]*/g, "")
            .replace(/^家里设备在线(?:且)?无异常[。；，,\s]*/g, "")
            .replace(/^设备在线(?:且)?无异常[。；，,\s]*/g, "")
            .replace(/(老人|妈妈|母亲|爸爸|父亲)/g, "家里")
            .replace(/家里家里/g, "家里")
            .replace(/正好问问家里对(.+?)有没有兴趣[。.]?$/g, "晚点可以问一句：“最近有没有留意$1？”")
            .replace(/\s+/g, " ")
            .trim();
        if (!next.body || genericPattern.test(next.body) || directivePattern.test(next.body) || impossibleActionPattern.test(next.body)) {
            next.body = theme.body;
        }
        const bodyUsesGenericWeatherOpener = weather.available
            && /(不用只说[“\"]?注意身体|问一句晚饭吃了什么|问问晚饭吃了什么|话题自然就打开了|从今天有没有出门)/.test(next.body);
        const titleDescribesWeather = /(晴|阴|多云|雨|雪|闷热|高温|降温|天气|晚饭)/.test(next.title);
        if (bodyUsesGenericWeatherOpener && !titleDescribesWeather) {
            next.title = theme.title;
        }
        if (next.body.length > 90) next.body = next.body.slice(0, 87).trim() + "...";
        next.facts = (Array.isArray(next.facts) ? next.facts : [])
            .map((item) => String(item || "")
                .replace(/(老人|妈妈|母亲|爸爸|父亲)兴趣/g, "已选关注主题")
                .replace(/(老人|妈妈|母亲|爸爸|父亲)/g, "家里")
                .replace(/家里家里/g, "家里")
                .replace(/已选关注主题话题/g, "已选关注主题")
                .trim())
            .filter(Boolean)
            .slice(0, 3);
        if (!next.image_brief || genericPattern.test(next.image_brief) || directivePattern.test(next.image_brief) || impossibleActionPattern.test(next.image_brief)) {
            next.image_brief = theme.image_brief;
        }
        return next;
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
            const card = sanitizeContextualCareCard(removeUnavailableWeatherClaims(sanitizeModelCareCard(parsed), context), context);
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

    const VISION_VERIFICATION_EVENT_TYPES = new Set([
        "fall_candidate",
        "prolonged_floor_lying",
        "fire_candidate",
    ]);

    function sanitizeVisionVerification(value) {
        if (!value || typeof value !== "object" || Array.isArray(value)) return null;
        const required = ["person_count", "posture", "surface", "emergency", "confidence", "reason", "suggested_event_type"];
        const allowed = new Set(required);
        if (required.some((key) => !(key in value))) return null;
        if (Object.keys(value).some((key) => !allowed.has(key))) return null;
        const personCount = Number(value.person_count);
        const confidence = Number(value.confidence);
        const postures = new Set(["standing", "sitting", "squatting", "bending", "lying", "fallen", "unknown"]);
        const surfaces = new Set(["floor", "bed", "sofa", "chair", "unknown"]);
        const eventTypes = new Set(["fall_candidate", "prolonged_floor_lying", "fire_candidate", "none", "uncertain"]);
        const posture = String(value.posture || "").trim();
        const surface = String(value.surface || "").trim();
        const suggestedEventType = String(value.suggested_event_type || "").trim();
        const reason = String(value.reason || "").replace(/\s+/g, " ").trim();
        if (!Number.isInteger(personCount) || personCount < 0 || personCount > 20) return null;
        if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) return null;
        if (typeof value.emergency !== "boolean") return null;
        if (!postures.has(posture) || !surfaces.has(surface) || !eventTypes.has(suggestedEventType)) return null;
        if (!reason || reason.length > 240) return null;
        return {
            person_count: personCount,
            posture,
            surface,
            emergency: value.emergency,
            confidence: Number(confidence.toFixed(4)),
            reason,
            suggested_event_type: suggestedEventType,
        };
    }

    function visionVerificationContext(event) {
        const evidence = event.payload?.evidence || {};
        return {
            event: {
                event_type: event.event_type,
                summary: event.summary,
                level: event.level,
                room: event.room || event.camera_name || "",
                occurred_at: event.occurred_at,
            },
            edge_rule: event.payload?.rule || evidence.rule || {},
            metrics: evidence.metrics || {},
            flags: evidence.flags || {},
            objects: evidence.objects || {},
            pose_factor_graph: evidence.pose_factor_graph || event.payload?.pose_factor_graph || {},
            temporal_evidence_bundle: evidence.temporal_evidence_bundle || event.payload?.temporal_evidence_bundle || {},
            evidence_frames: (event.payload?.evidence_media_assets || []).map((item) => ({
                asset_id: item.asset_id || item.id || null,
                role: item.role || "evidence",
                captured_at: item.captured_at || "",
                postures: Array.isArray(item.postures) ? item.postures : [],
            })),
        };
    }

    function verificationAssetPath(asset) {
        const relativePath = String(asset?.relative_path || "").replace(/^[/\\]+/, "");
        if (!relativePath) return "";
        const target = path.resolve(mediaDir, relativePath);
        const root = `${path.resolve(mediaDir)}${path.sep}`;
        return target.startsWith(root) ? target : "";
    }

    function visionEvidenceAssets(event, primaryAsset = null) {
        const roleOrder = { before: 0, transition: 1, current: 2, evidence: 3 };
        const ids = [];
        for (const item of event.payload?.evidence_media_assets || []) {
            const assetId = normalizeNumber(item?.asset_id || item?.id, null);
            if (assetId !== null && !ids.includes(assetId)) ids.push(assetId);
        }
        if (primaryAsset?.id && !ids.includes(Number(primaryAsset.id))) ids.push(Number(primaryAsset.id));
        return ids
            .map((id) => store.db.assets.find((item) => Number(item.id) === Number(id)))
            .filter((item) => item && verificationAssetPath(item))
            .sort((a, b) => {
                const roleDifference = (roleOrder[String(a.evidence_frame_role || "evidence")] ?? 3)
                    - (roleOrder[String(b.evidence_frame_role || "evidence")] ?? 3);
                if (roleDifference) return roleDifference;
                return String(a.captured_at || a.created_at || "").localeCompare(String(b.captured_at || b.created_at || ""));
            })
            .slice(0, 3);
    }

    async function callVisionVerificationModel(event, assets) {
        const runtime = visionVerificationRuntimeConfig();
        if (!visionVerificationEnabled()) throw new Error("vision verification disabled");
        if (!runtime.base_url || !runtime.api_key || !runtime.model) throw new Error("vision verification model is not configured");
        const evidenceAssets = Array.isArray(assets) ? assets.slice(0, 3) : [assets].filter(Boolean);
        if (!evidenceAssets.length) throw new Error("event evidence image is unavailable");
        const images = evidenceAssets.map((asset) => {
            const assetPath = verificationAssetPath(asset);
            if (!assetPath || !fs.existsSync(assetPath)) throw new Error("event evidence image is unavailable");
            const imageBytes = fs.readFileSync(assetPath);
            if (!imageBytes.length) throw new Error("event evidence image is empty");
            if (imageBytes.length > 8 * 1024 * 1024) throw new Error("event evidence image exceeds 8MB");
            return {
                bytes: imageBytes,
                content_type: String(asset.content_type || "image/jpeg").split(";")[0].trim() || "image/jpeg",
            };
        });
        if (images.reduce((total, item) => total + item.bytes.length, 0) > 18 * 1024 * 1024) {
            throw new Error("event evidence sequence exceeds 18MB");
        }
        const context = visionVerificationContext(event);
        const requestPayload = {
            model: runtime.model,
            messages: [
                { role: "system", content: runtime.prompt },
                {
                    role: "user",
                    content: [
                        {
                            type: "text",
                            text: [
                                `请按时间顺序复核这条家庭守护事件的 ${images.length} 张证据图。严格按系统约定只输出 JSON。`,
                                JSON.stringify(context),
                            ].join("\n\n"),
                        },
                        ...images.map((image) => ({
                            type: "image_url",
                            image_url: { url: `data:${image.content_type};base64,${image.bytes.toString("base64")}` },
                        })),
                    ],
                },
            ],
            temperature: 0.1,
            max_tokens: 900,
            response_format: { type: "json_object" },
            enable_thinking: false,
            thinking_budget: 64,
        };
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), visionVerificationTimeoutMs());
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
            const responsePayload = safeJsonParse(responseText, null);
            if (!response.ok) {
                const detail = responsePayload?.error?.message || responsePayload?.message || responseText.slice(0, 200);
                throw new Error(`vision verification failed: ${response.status} ${detail}`);
            }
            const content = responsePayload?.choices?.[0]?.message?.content
                || responsePayload?.output_text
                || responsePayload?.text
                || "";
            const verification = sanitizeVisionVerification(extractJsonObject(content));
            if (!verification) {
                const error = new Error("vision verification response violates strict JSON contract");
                error.response_payload = {
                    id: responsePayload?.id || "",
                    model: responsePayload?.model || runtime.model,
                    content_preview: String(content || responseText || "").slice(0, 1200),
                };
                throw error;
            }
            return {
                verification,
                response_payload: {
                    id: responsePayload?.id || "",
                    model: responsePayload?.model || runtime.model,
                    usage: responsePayload?.usage || {},
                    parsed: verification,
                },
            };
        } finally {
            clearTimeout(timeout);
        }
    }

    function verificationDecision(result) {
        if (result.emergency) return { status: "confirmed", decision: "confirm" };
        if (result.confidence >= 0.75 && result.suggested_event_type === "none") {
            return { status: "rejected", decision: "downgrade" };
        }
        return { status: "uncertain", decision: "manual_review" };
    }

    function verificationJobForEvent(eventId) {
        return store.db.model_generation_jobs.find((job) => (
            job.purpose === "vision_event_verification"
            && String(job.metadata?.event_id || "") === String(eventId)
        ));
    }

    function queueVisionVerification(event, asset) {
        const validationProbe = Boolean(event.payload?.validation?.vision_verification_probe);
        if (!VISION_VERIFICATION_EVENT_TYPES.has(event.event_type) || (isValidationEvent(event) && !validationProbe)) return null;
        event.payload = event.payload && typeof event.payload === "object" ? event.payload : {};
        const assets = visionEvidenceAssets(event, asset);
        if (!assets.length) {
            event.payload.verification = {
                status: "unavailable",
                reason: "missing_event_evidence",
                updated_at: nowIso(),
            };
            return null;
        }
        const primaryAsset = asset || assets[assets.length - 1];
        const runtime = visionVerificationRuntimeConfig();
        if (!visionVerificationEnabled() || !runtime.base_url || !runtime.api_key || !runtime.model) {
            event.payload.verification = {
                status: "unavailable",
                reason: "model_not_configured",
                updated_at: nowIso(),
            };
            return null;
        }
        const existing = verificationJobForEvent(event.id);
        if (existing) return existing;
        const context = visionVerificationContext(event);
        const job = modelJob({
            family_id: event.family_id,
            purpose: "vision_event_verification",
            model: runtime.model,
            prompt_version: `vision-verification:${runtime.prompt_source}:v1`,
            input_hash: sha256(JSON.stringify({ context, asset_ids: assets.map((item) => item.id) })),
            output_status: "pending",
            request_payload: {
                capability_id: runtime.capability_id,
                event_id: event.id,
                asset_id: primaryAsset.id,
                asset_ids: assets.map((item) => item.id),
                context,
            },
            metadata: {
                event_id: String(event.id),
                asset_id: String(primaryAsset.id),
                asset_ids: assets.map((item) => String(item.id)),
                evidence_frame_count: assets.length,
                attempt_count: 0,
                max_attempts: visionVerificationMaxAttempts(),
                next_attempt_at: nowIso(),
            },
        });
        store.db.model_generation_jobs.push(job);
        event.payload.verification = {
            status: "pending",
            job_id: job.id,
            attempt_count: 0,
            model: runtime.model,
            updated_at: nowIso(),
        };
        return job;
    }

    async function processVisionVerificationJobs(options = {}) {
        if (visionVerificationRunning) return { ok: true, skipped: "already_running", processed: 0 };
        visionVerificationRunning = true;
        const limit = Math.max(1, Math.min(10, normalizeNumber(options.limit, 3)));
        const force = normalizeBool(options.force);
        const result = { ok: true, processed: 0, succeeded: 0, retrying: 0, failed: 0, skipped: 0 };
        try {
            const now = Date.now();
            const jobs = store.db.model_generation_jobs
                .filter((job) => job.purpose === "vision_event_verification")
                .filter((job) => ["pending", "retrying", "verifying"].includes(job.output_status))
                .filter((job) => force || !job.metadata?.next_attempt_at || Date.parse(job.metadata.next_attempt_at) <= now)
                .sort((a, b) => String(a.created_at || "").localeCompare(String(b.created_at || "")))
                .slice(0, limit);
            for (const job of jobs) {
                const event = store.db.events.find((item) => String(item.id) === String(job.metadata?.event_id || job.request_payload?.event_id));
                const assetIds = Array.isArray(job.metadata?.asset_ids)
                    ? job.metadata.asset_ids
                    : (Array.isArray(job.request_payload?.asset_ids) ? job.request_payload.asset_ids : [job.metadata?.asset_id || job.request_payload?.asset_id]);
                const assets = assetIds
                    .map((id) => store.db.assets.find((item) => String(item.id) === String(id)))
                    .filter(Boolean);
                if (!event || !assets.length) {
                    updateModelJob(job, { output_status: "failed", error_message: "event or evidence asset not found" });
                    result.failed += 1;
                    result.processed += 1;
                    continue;
                }
                const attempts = Number(job.metadata?.attempt_count || 0) + 1;
                job.metadata = { ...job.metadata, attempt_count: attempts, started_at: nowIso() };
                updateModelJob(job, { output_status: "verifying", error_message: "" });
                event.payload.verification = {
                    ...(event.payload.verification || {}),
                    status: "verifying",
                    job_id: job.id,
                    attempt_count: attempts,
                    updated_at: nowIso(),
                };
                await store.save();
                try {
                    const response = await callVisionVerificationModel(event, assets);
                    const decision = verificationDecision(response.verification);
                    updateModelJob(job, {
                        output_status: "succeeded",
                        response_payload: response.response_payload,
                        error_message: "",
                    });
                    job.metadata = { ...job.metadata, completed_at: nowIso(), next_attempt_at: "" };
                    event.payload.verification = {
                        status: decision.status,
                        decision: decision.decision,
                        job_id: job.id,
                        attempt_count: attempts,
                        model: job.model,
                        result: response.verification,
                        verified_at: nowIso(),
                        updated_at: nowIso(),
                    };
                    event.updated_at = nowIso();
                    const orchestration = applyIncidentVerificationOutcome(event);
                    job.metadata = {
                        ...job.metadata,
                        orchestration_status: orchestration.status,
                        orchestration_message_id: orchestration.message?.message_id || "",
                    };
                    result.succeeded += 1;
                } catch (error) {
                    const maxAttempts = Number(job.metadata?.max_attempts || visionVerificationMaxAttempts());
                    const exhausted = attempts >= maxAttempts;
                    const delaySeconds = [5, 30, 120, 300][Math.min(attempts - 1, 3)];
                    updateModelJob(job, {
                        output_status: exhausted ? "failed" : "retrying",
                        response_payload: error.response_payload || {},
                        error_message: String(error.message || error).slice(0, 500),
                    });
                    job.metadata = {
                        ...job.metadata,
                        next_attempt_at: exhausted ? "" : new Date(Date.now() + delaySeconds * 1000).toISOString(),
                        completed_at: exhausted ? nowIso() : "",
                    };
                    event.payload.verification = {
                        ...(event.payload.verification || {}),
                        status: exhausted ? "failed" : "retrying",
                        job_id: job.id,
                        attempt_count: attempts,
                        next_attempt_at: job.metadata.next_attempt_at,
                        error: String(error.message || error).slice(0, 240),
                        updated_at: nowIso(),
                    };
                    if (exhausted) applyIncidentVerificationOutcome(event);
                    if (exhausted) result.failed += 1;
                    else result.retrying += 1;
                }
                result.processed += 1;
                await store.save();
            }
            return result;
        } finally {
            visionVerificationRunning = false;
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
        const recommendations = Array.isArray(card.content_recommendations) ? card.content_recommendations : [];
        const recommendation = recommendations.find((item) => item?.type === "image_brief")
            || recommendations.find((item) => item?.summary);
        return String(recommendation?.summary || recommendation?.title || "").trim();
    }

    function careImageScene(card) {
        const text = [card?.title, card?.body].map((item) => String(item || "")).join(" ");
        if (/(旅行|旅游|文旅|戏曲|演出|展览|周末活动)/.test(text)) {
            return "雨后明亮玄关，收好的素色折叠伞、黑色轻便背包、钥匙和一小块姜黄色手帕，自然侧光，无人物。";
        }
        if (/(闷热|炎热|高温|偏热|喝水|清凉)/.test(text)) {
            return "窗边浅色木桌，一杯清水、切开的青柠、熄屏手机和一块姜黄色杯垫，清爽自然日光，无人物。";
        }
        if (/(雨|雷|阴天|多云|天气)/.test(text)) {
            return "雨后窗边，一把收拢的素色雨伞、熄屏手机和一只姜黄色小碟，柔和阴天自然光，无人物。";
        }
        if (/(回家|离家|探望)/.test(text)) {
            return "明亮玄关里的钥匙、黑色轻便背包、干净便鞋和一小块姜黄色织物，像正准备出门，无人物。";
        }
        if (/(生日|纪念日|节日)/.test(text)) {
            return "白色餐桌上的一束当季鲜花、无标识礼物盒和姜黄色丝带，自然日光，无人物。";
        }
        if (/(健康|养生|饮食|晚饭|水果)/.test(text)) {
            return "浅色餐桌一角，当季水果、素色杯子、熄屏手机和姜黄色餐巾，真实自然日光，无人物。";
        }
        const brief = careImageBrief(card);
        if (brief && !/(横幅|海报|招牌|文字|标题|标语|屏幕|界面|人物|老人|卡片)/.test(brief)) {
            return compactPromptText(brief, 90);
        }
        return "自然日光下的浅色桌面，一部熄屏手机、素色杯子、小束绿植和姜黄色杯垫，安静真实，无人物。";
    }

    function buildCareImagePrompt(card, context, runtime = imageRuntimeConfig()) {
        return [
            runtime.prompt,
            "",
            `本次具体场景：${careImageScene(card)}`,
            "最终只生成一张铺满画幅的照片，不增加其他内容。",
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
        const timeout = setTimeout(() => controller.abort(), imageGenerationTimeoutMs());
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

    function cachedProviderValue(cacheKey, ttlMs) {
        const entry = providerCache.get(cacheKey);
        if (!entry) return null;
        if (Date.now() - entry.cached_at > ttlMs) {
            providerCache.delete(cacheKey);
            return null;
        }
        return entry.value;
    }

    function setCachedProviderValue(cacheKey, value) {
        providerCache.set(cacheKey, { value, cached_at: Date.now() });
        return value;
    }

    function knownContentImageUrl(targetUrl) {
        const target = String(targetUrl || "").trim();
        if (!target) return false;
        const cached = [...providerCache.values()].some((entry) => (
            Array.isArray(entry?.value?.recommendations)
            && entry.value.recommendations.some((item) => String(item?.image_url || "").trim() === target)
        ));
        if (cached) return true;
        return store.db.care_cards.some((card) => (
            Array.isArray(card?.content_recommendations)
            && card.content_recommendations.some((item) => String(item?.image_url || "").trim() === target)
        ));
    }

    async function proxyContentImage(targetUrl) {
        const target = String(targetUrl || "").trim();
        let parsed;
        try {
            parsed = new URL(target);
        } catch (_error) {
            throw new Error("invalid content image URL");
        }
        if (parsed.protocol !== "https:" || !knownContentImageUrl(parsed.toString())) {
            throw new Error("content image is not an approved recommendation asset");
        }
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 8000);
        try {
            const response = await fetch(parsed, {
                headers: {
                    Accept: "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8",
                    "User-Agent": "Mozilla/5.0 GoHomeContent/1.0",
                },
                redirect: "follow",
                signal: controller.signal,
            });
            if (!response.ok) throw new Error(`content image request failed: ${response.status}`);
            const contentType = String(response.headers.get("content-type") || "").split(";")[0].trim().toLowerCase();
            if (!/^image\/(?:avif|webp|png|jpe?g|gif)$/.test(contentType)) {
                throw new Error("content image response has an unsupported type");
            }
            const buffer = Buffer.from(await response.arrayBuffer());
            if (!buffer.length || buffer.length > 5 * 1024 * 1024) throw new Error("content image size is invalid");
            return { buffer, contentType };
        } finally {
            clearTimeout(timeout);
        }
    }

    function providerUrl(baseUrl, pathname, params = {}) {
        const url = new URL(baseUrl);
        const basePath = url.pathname.replace(/\/+$/, "");
        const nextPath = String(pathname || "").startsWith("/") ? String(pathname) : `/${pathname}`;
        url.pathname = `${basePath}${nextPath}`;
        Object.entries(params).forEach(([key, value]) => {
            if (value !== null && value !== undefined && value !== "") {
                url.searchParams.set(key, String(value));
            }
        });
        return url;
    }

    async function fetchProviderJson(url, options = {}, errorPrefix = "provider request failed") {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), providerRequestTimeoutMs());
        try {
            const response = await fetch(url, {
                ...options,
                signal: controller.signal,
            });
            const responseText = await response.text();
            const payload = safeJsonParse(responseText, { raw_text: responseText.slice(0, 1200) });
            if (!response.ok) {
                const detail = payload?.message || payload?.error?.message || payload?.code || responseText.slice(0, 200);
                throw new Error(`${errorPrefix}: ${response.status} ${detail}`);
            }
            return payload;
        } finally {
            clearTimeout(timeout);
        }
    }

    function unavailableWeatherSignal({ familyId, city, provider, reason, detail = "" }) {
        return {
            family_id: Number(familyId || 0),
            city: city || "杭州",
            available: false,
            provider,
            reason,
            detail: detail ? String(detail).slice(0, 160) : "",
            condition: "",
            temperature_c: null,
            humidity: null,
            precipitation_mm: null,
            precipitation_probability: null,
            advice: "天气数据源未接入或暂时不可用，关怀卡片不会编造温度、降雨或实时天气。",
            updated_at: nowIso(),
        };
    }

    function qweatherAuthMode(runtime) {
        const configured = String(runtime.auth_mode || "auto").toLowerCase();
        if (configured === "bearer" || configured === "query") return configured;
        const key = String(runtime.api_key || "");
        return key.includes(".") || key.length > 80 ? "bearer" : "query";
    }

    async function qweatherJson(runtime, pathname, params = {}, baseUrl = runtime.base_url) {
        const url = providerUrl(baseUrl || "https://devapi.qweather.com", pathname, params);
        const headers = { Accept: "application/json" };
        if (qweatherAuthMode(runtime) === "bearer") {
            headers.Authorization = `Bearer ${runtime.api_key}`;
        } else {
            url.searchParams.set("key", runtime.api_key);
        }
        const payload = await fetchProviderJson(url, { headers }, "qweather request failed");
        const code = String(payload?.code || "");
        if (code && code !== "200") {
            throw new Error(`qweather returned code ${code}`);
        }
        return payload;
    }

    function weatherAdvice({ condition, temperature, humidity, precipitation }) {
        const parts = [];
        if (condition) parts.push(condition);
        if (Number.isFinite(temperature)) {
            if (temperature >= 33) parts.push("天热，电话里可以提醒多喝水、少久晒");
            else if (temperature <= 8) parts.push("气温偏低，适合提醒添衣保暖");
            else parts.push("天气适中，适合一句轻松问候");
        }
        if (Number.isFinite(precipitation) && precipitation > 0) parts.push("有降水，出门记得带伞");
        if (Number.isFinite(humidity) && humidity >= 80) parts.push("湿度偏高，注意通风");
        return parts.length ? parts.join("；") : "可作为今天电话问候的自然开场。";
    }

    async function fetchQWeatherSignal({ familyId, city }) {
        const runtime = weatherRuntimeConfig();
        if (!runtime.api_key) {
            return unavailableWeatherSignal({ familyId, city, provider: "qweather", reason: "not_configured" });
        }
        const targetCity = String(city || "杭州").trim() || "杭州";
        const cacheKey = `weather:qweather:${targetCity}`;
        const cached = cachedProviderValue(cacheKey, 20 * 60 * 1000);
        if (cached) return { ...cached, family_id: Number(familyId || cached.family_id || 0) };
        try {
            const geo = await qweatherJson(runtime, "/v2/city/lookup", {
                location: targetCity,
                number: 1,
                lang: "zh",
            }, runtime.geo_base_url || "https://geoapi.qweather.com");
            const location = Array.isArray(geo.location) ? geo.location[0] : null;
            if (!location?.id) throw new Error("qweather city lookup returned no location");
            const weather = await qweatherJson(runtime, "/v7/weather/now", {
                location: location.id,
                lang: "zh",
                unit: "m",
            });
            const now = weather.now || {};
            const temperature = Number(now.temp);
            const humidity = Number(now.humidity);
            const precipitation = Number(now.precip);
            const signal = {
                family_id: Number(familyId || 0),
                city: location.name || targetCity,
                available: true,
                provider: "qweather",
                location_id: location.id,
                location_name: [location.adm2, location.adm1].filter(Boolean).join(" · "),
                condition: String(now.text || ""),
                temperature_c: Number.isFinite(temperature) ? temperature : null,
                humidity: Number.isFinite(humidity) ? humidity : null,
                precipitation_mm: Number.isFinite(precipitation) ? precipitation : null,
                precipitation_probability: null,
                wind: [now.windDir, now.windScale ? `${now.windScale}级` : ""].filter(Boolean).join(" "),
                advice: weatherAdvice({ condition: now.text, temperature, humidity, precipitation }),
                source: "QWeather",
                observed_at: now.obsTime || weather.updateTime || "",
                updated_at: nowIso(),
            };
            return setCachedProviderValue(cacheKey, signal);
        } catch (error) {
            return unavailableWeatherSignal({
                familyId,
                city: targetCity,
                provider: "qweather",
                reason: "provider_error",
                detail: error.message,
            });
        }
    }

    function weatherCodeText(code) {
        const table = {
            0: "晴朗",
            1: "多云",
            2: "多云",
            3: "阴天",
            45: "有雾",
            48: "有雾",
            51: "小雨",
            53: "小雨",
            55: "小雨",
            61: "小雨",
            63: "中雨",
            65: "大雨",
            80: "阵雨",
            81: "阵雨",
            82: "强阵雨",
            95: "雷雨",
        };
        return table[Number(code)] || "天气已更新";
    }

    async function fetchOpenMeteoSignal({ familyId, city }) {
        const targetCity = String(city || "杭州").trim() || "杭州";
        const cacheKey = `weather:open-meteo:${targetCity}`;
        const cached = cachedProviderValue(cacheKey, 20 * 60 * 1000);
        if (cached) return { ...cached, family_id: Number(familyId || cached.family_id || 0) };
        try {
            const geoUrl = providerUrl("https://geocoding-api.open-meteo.com", "/v1/search", {
                name: targetCity,
                count: 1,
                language: "zh",
                format: "json",
            });
            const geo = await fetchProviderJson(geoUrl, { headers: { Accept: "application/json" } }, "open-meteo geocoding failed");
            const location = Array.isArray(geo.results) ? geo.results[0] : null;
            if (!location?.latitude || !location?.longitude) throw new Error("open-meteo city lookup returned no location");
            const forecastUrl = providerUrl("https://api.open-meteo.com", "/v1/forecast", {
                latitude: location.latitude,
                longitude: location.longitude,
                current: "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
                timezone: "Asia/Shanghai",
                forecast_days: 1,
            });
            const forecast = await fetchProviderJson(forecastUrl, { headers: { Accept: "application/json" } }, "open-meteo forecast failed");
            const current = forecast.current || {};
            const temperature = Number(current.temperature_2m);
            const humidity = Number(current.relative_humidity_2m);
            const precipitation = Number(current.precipitation);
            const condition = weatherCodeText(current.weather_code);
            const signal = {
                family_id: Number(familyId || 0),
                city: location.name || targetCity,
                available: true,
                provider: "open-meteo",
                location_id: "",
                location_name: [location.admin1, location.country].filter(Boolean).join(" · "),
                condition,
                temperature_c: Number.isFinite(temperature) ? temperature : null,
                humidity: Number.isFinite(humidity) ? humidity : null,
                precipitation_mm: Number.isFinite(precipitation) ? precipitation : null,
                precipitation_probability: null,
                wind: Number.isFinite(Number(current.wind_speed_10m)) ? `${current.wind_speed_10m} km/h` : "",
                advice: weatherAdvice({ condition, temperature, humidity, precipitation }),
                source: "Open-Meteo",
                observed_at: current.time || "",
                updated_at: nowIso(),
            };
            return setCachedProviderValue(cacheKey, signal);
        } catch (error) {
            return unavailableWeatherSignal({
                familyId,
                city: targetCity,
                provider: "open-meteo",
                reason: "provider_error",
                detail: error.message,
            });
        }
    }

    async function fetchWeatherSignal({ familyId, city }) {
        const runtime = weatherRuntimeConfig();
        if (["none", "off", "disabled"].includes(runtime.provider)) {
            return unavailableWeatherSignal({ familyId, city, provider: runtime.provider, reason: "disabled" });
        }
        if (runtime.provider === "qweather") return fetchQWeatherSignal({ familyId, city });
        return fetchOpenMeteoSignal({ familyId, city });
    }

    function unavailableContentRecommendations({ familyId, city, topics = [], provider, reason, detail = "" }) {
        return {
            family_id: Number(familyId || 0),
            city: city || "杭州",
            topics,
            available: false,
            provider,
            reason,
            detail: detail ? String(detail).slice(0, 160) : "",
            recommendations: [],
            source_policy: "candidate_only",
            updated_at: nowIso(),
        };
    }

    function contentTopicsFromPreferences(preferences = {}) {
        const schedule = preferences.metadata?.care_card_schedule || {};
        const contentTypes = schedule.content_types || {};
        return [...new Set([
            ...(Array.isArray(schedule.interest_topics) ? schedule.interest_topics : []),
            ...(Array.isArray(preferences.interests) ? preferences.interests : []),
            ...(contentTypes.local_hotspots ? ["本地生活", "社区活动"] : []),
            ...(contentTypes.health_tips ? ["健康养生", "节气饮食"] : []),
            ...(contentTypes.anti_fraud ? ["防诈骗"] : []),
            ...(contentTypes.culture_entertainment ? ["戏曲", "电视节目"] : []),
            "家常",
        ].map((item) => String(item || "").trim()).filter(Boolean))].slice(0, 8);
    }

    function contentRegionText(preferences = {}, fallbackCity = "杭州", fallbackDistrict = "") {
        const schedule = preferences.metadata?.care_card_schedule || {};
        const region = schedule.content_region || {};
        const city = String(region.city || fallbackCity || "杭州").trim() || "杭州";
        const district = String(region.district || fallbackDistrict || "").trim();
        return {
            city,
            district,
            label: `${city}${district ? ` ${district}` : ""}`.trim(),
        };
    }

    function shanghaiDateParts(date = new Date()) {
        return new Intl.DateTimeFormat("zh-CN", {
            timeZone: "Asia/Shanghai",
            year: "numeric",
            month: "numeric",
            day: "numeric",
            weekday: "short",
        }).formatToParts(date).reduce((acc, part) => {
            if (part.type !== "literal") acc[part.type] = part.value;
            return acc;
        }, {});
    }

    function contentSearchDateContext(date = new Date()) {
        const parts = shanghaiDateParts(date);
        const year = Number(parts.year || date.getFullYear());
        const month = Number(parts.month || date.getMonth() + 1);
        const day = Number(parts.day || date.getDate());
        return {
            year,
            today: `${year}年${month}月${day}日`,
            month: `${year}年${month}月`,
            weekday: parts.weekday || "",
        };
    }

    function contentSearchTasksFromPreferences(preferences = {}, fallbackCity = "杭州", fallbackDistrict = "") {
        const schedule = preferences.metadata?.care_card_schedule || {};
        const contentTypes = schedule.content_types || {};
        const topics = contentTopicsFromPreferences(preferences);
        const region = contentRegionText(preferences, fallbackCity, fallbackDistrict);
        const dateContext = contentSearchDateContext();
        const commonOfficialDomains = ["people.com.cn", "xinhuanet.com", "cctv.com", "gmw.cn"];
        const shanghaiPublicDomains = [
            "shanghai.gov.cn",
            "shyp.gov.cn",
            "shhk.gov.cn",
            "shqp.gov.cn",
            "shpt.gov.cn",
            "fgj.sh.gov.cn",
        ];
        const taskList = [];
        if (contentTypes.local_hotspots) {
            taskList.push({
                type: "local_hotspots",
                topic: "本地热点",
                query: `${dateContext.today} ${region.label} 本周 民生 社区活动 便民服务 本地生活 适合老人聊天`,
                domains: ["shobserver.com", "wsjkw.sh.gov.cn", ...shanghaiPublicDomains, ...commonOfficialDomains],
                search_topic: "news",
                time_range: "week",
                max_age_days: 21,
            });
        }
        if (contentTypes.health_tips) {
            taskList.push({
                type: "health_tips",
                topic: "健康养生",
                query: `${dateContext.month} 老年人 健康生活 养生 节气 饮食 作息 官方 科普`,
                domains: ["wsjkw.sh.gov.cn", "nhc.gov.cn", "gov.cn", "ihchina.cn", "shobserver.com", ...commonOfficialDomains],
                search_topic: "general",
                time_range: "month",
                max_age_days: 180,
            });
        }
        if (contentTypes.anti_fraud) {
            taskList.push({
                type: "anti_fraud",
                topic: "防诈骗提醒",
                query: `${dateContext.month} ${region.city} 老年人 防诈骗 反诈 社区 安全提醒 官方`,
                domains: ["mps.gov.cn", "gaj.sh.gov.cn", "shanghai.gov.cn", ...commonOfficialDomains],
                search_topic: "news",
                time_range: "month",
                max_age_days: 120,
            });
        }
        if (contentTypes.culture_entertainment) {
            taskList.push({
                type: "culture_entertainment",
                topic: "文娱兴趣",
                query: `${dateContext.month} ${region.label} 老年人 戏曲 电视节目 社区文化 活动`,
                domains: ["shobserver.com", ...shanghaiPublicDomains, ...commonOfficialDomains],
                search_topic: "news",
                time_range: "month",
                max_age_days: 90,
            });
        }
        if (contentTypes.elder_interest_topics) {
            taskList.push({
                type: "elder_interest_topics",
                topic: "问候话题",
                query: `${dateContext.today} ${region.label} 适合老人 聊天话题 ${topics.slice(0, 5).join(" ")}`,
                domains: ["shobserver.com", "wsjkw.sh.gov.cn", ...commonOfficialDomains],
                search_topic: "general",
                time_range: "month",
                max_age_days: 90,
            });
        }
        if (!taskList.length) {
            taskList.push({
                type: "elder_interest_topics",
                topic: topics[0] || "关怀话题",
                query: `${dateContext.today} ${region.label} 老年人 健康生活 适合聊天 ${topics.slice(0, 5).join(" ")}`,
                domains: ["shobserver.com", "wsjkw.sh.gov.cn", ...commonOfficialDomains],
                search_topic: "general",
                time_range: "month",
                max_age_days: 90,
            });
        }
        return taskList.slice(0, 5);
    }

    function publicTavilyImageUrl(value) {
        const raw = typeof value === "string"
            ? value
            : String(value?.url || value?.image_url || value?.src || "").trim();
        if (!raw) return "";
        try {
            const parsed = new URL(raw);
            return parsed.protocol === "https:" ? parsed.toString() : "";
        } catch (_error) {
            return "";
        }
    }

    function tavilyResultImage(result, images = [], index = 0) {
        const direct = publicTavilyImageUrl(result?.image_url || result?.image || result?.thumbnail);
        if (direct) return direct;
        return publicTavilyImageUrl(images[index] || images[0]);
    }

    function publicRecommendationFromTavily(result, topic, imageUrl = "") {
        const url = String(result?.url || "").trim();
        let source = "";
        try {
            source = new URL(url).hostname.replace(/^www\./, "");
        } catch (_error) {
            source = "内容源";
        }
        const title = String(result?.title || "今日可聊内容")
            .replace(/^\s*[\[【][^\]】]{1,18}[\]】]\s*/g, "")
            .replace(/[_｜|].*$/g, "")
            .replace(/新闻频道|央视网|中国网|老年频道|公众号|视频号/g, "")
            .replace(/\s+/g, " ")
            .trim()
            .slice(0, 80);
        return {
            type: "search_result",
            topic,
            title,
            url,
            source,
            summary: String(result?.content || result?.raw_content || "").replace(/\s+/g, " ").trim().slice(0, 160),
            image_url: publicTavilyImageUrl(imageUrl),
            published_at: String(result?.published_date || result?.publishedAt || result?.date || "").trim(),
            score: Number.isFinite(Number(result?.score)) ? Number(result.score) : null,
        };
    }

    function parseContentPublishedAt(value) {
        const raw = String(value || "").trim();
        if (!raw) return null;
        const timestamp = Date.parse(raw);
        return Number.isFinite(timestamp) ? timestamp : null;
    }

    function contentAgeDays(item) {
        const timestamp = parseContentPublishedAt(item?.published_at);
        if (!timestamp) return null;
        return Math.floor((Date.now() - timestamp) / (24 * 60 * 60 * 1000));
    }

    function containsStaleYear(text, maxYearAge = 1) {
        const currentYear = contentSearchDateContext().year;
        const years = String(text || "").match(/\b20\d{2}\b/g) || [];
        return years.some((year) => currentYear - Number(year) > maxYearAge);
    }

    function seasonalTermMismatched(text) {
        const month = contentSearchDateContext().month;
        const value = String(text || "");
        const seasonalWindows = [
            { pattern: /春节|元宵/, months: [1, 2] },
            { pattern: /清明/, months: [3, 4] },
            { pattern: /端午/, months: [5, 6] },
            { pattern: /中秋/, months: [9, 10] },
            { pattern: /国庆/, months: [9, 10] },
            { pattern: /重阳/, months: [10, 11] },
        ];
        return seasonalWindows.some((item) => item.pattern.test(value) && !item.months.includes(month));
    }

    function matchesModuleIntent(text, taskType = "") {
        const value = String(text || "");
        if (taskType === "anti_fraud") {
            return /(诈骗|反诈|防骗|防诈|养老诈骗|电信网络|陌生电话|陌生链接|转账|刷单|冒充|保健品骗局)/.test(value);
        }
        if (taskType === "local_hotspots") {
            return /(社区|便民|民生|服务|活动|出行|公交|地铁|菜场|文旅|公园|街道|本地|上海|杭州)/.test(value);
        }
        if (taskType === "health_tips") {
            return /(健康|养生|饮食|作息|喝水|睡眠|运动|防暑|降温|节气|科普|老人|老年)/.test(value);
        }
        if (taskType === "culture_entertainment") {
            return /(戏曲|电视|节目|演出|文化|文旅|活动|社区|展览|电影|广播)/.test(value);
        }
        return true;
    }

    function safeCareContentRecommendation(item, taskType = "", task = {}) {
        const text = `${item?.title || ""} ${item?.summary || ""}`;
        const sourceText = `${item?.source || ""} ${item?.url || ""}`.toLowerCase();
        if (!String(item?.title || "").trim() || !String(item?.url || "").trim()) return false;
        if (!/[\u4e00-\u9fff]{4,}/.test(text)) return false;
        if (/(字体放大|字体缩小|默认大小|来源\s*[:：]|作者\s*[:：]|日期\s*[:：]|###|\{\{|font-size|copyright|版权所有|网站地图|登录\s*注册)/i.test(text)) return false;
        if (/(dangjian|cpc\.people|qstheory|theory\.people)/.test(sourceText)) return false;
        if (!matchesModuleIntent(text, taskType)) return false;
        const blocked = taskType === "anti_fraud"
            ? /(痴迷|割韭菜|谣言|投诉|死亡|猝死|癌|肿瘤|医院花钱|收割|曝光|乱象|焦虑|保健品骗局|坑老|习近平|金正恩|朝鲜|党代会|慢性病|疾病风险|医疗诊断)/
            : /(痴迷|骗局|诈骗|防骗|割韭菜|谣言|投诉|死亡|猝死|癌|肿瘤|医院花钱|收割|警惕|曝光|乱象|焦虑|保健品骗局|坑老|习近平|金正恩|朝鲜|党代会|慢性病|疾病风险|医疗诊断)/;
        if (blocked.test(text)) return false;
        if (containsStaleYear(text, taskType === "health_tips" ? 2 : 1)) return false;
        if (seasonalTermMismatched(text)) return false;
        const ageDays = contentAgeDays(item);
        const maxAgeDays = Number(task?.max_age_days || 0);
        if (ageDays !== null && maxAgeDays > 0 && ageDays > maxAgeDays) return false;
        return true;
    }

    async function fetchTavilyContent({ familyId, city, district = "", topics = [], preferences = null }) {
        const runtime = contentSearchRuntimeConfig();
        if (runtime.provider !== "tavily") {
            return unavailableContentRecommendations({ familyId, city, topics, provider: runtime.provider, reason: "disabled" });
        }
        if (!runtime.api_key) {
            return unavailableContentRecommendations({ familyId, city, topics, provider: "tavily", reason: "not_configured" });
        }
        const targetCity = String(city || "杭州").trim() || "杭州";
        const normalizedTopics = normalizeStringList(topics, ["健康养生", "家常"], 8);
        const tasks = contentSearchTasksFromPreferences(preferences || {}, targetCity, district);
        const cacheKey = `content:tavily:v3:${targetCity}:${tasks.map((item) => `${item.type}:${item.query}`).join("|")}`;
        const cached = cachedProviderValue(cacheKey, 30 * 60 * 1000);
        if (cached) return { ...cached, family_id: Number(familyId || cached.family_id || 0) };
        try {
            const taskPayloads = await Promise.all(tasks.map(async (task) => {
                const requestPayload = {
                    query: task.query,
                    auto_parameters: false,
                    topic: task.search_topic || "general",
                    search_depth: "basic",
                    max_results: runtime.max_results,
                    time_range: task.time_range || null,
                    include_answer: false,
                    include_raw_content: false,
                    include_images: true,
                    include_image_descriptions: false,
                    include_favicon: false,
                    include_domains: task.domains,
                };
                try {
                    return {
                        task,
                        payload: await fetchProviderJson(runtime.base_url, {
                            method: "POST",
                            headers: {
                                Accept: "application/json",
                                "Content-Type": "application/json",
                                Authorization: `Bearer ${runtime.api_key}`,
                            },
                            body: JSON.stringify(requestPayload),
                        }, "tavily request failed"),
                    };
                } catch (error) {
                    if (!/(401|403|Unauthorized|invalid API key)/i.test(error.message || "")) return { task, error };
                    return {
                        task,
                        payload: await fetchProviderJson(runtime.base_url, {
                            method: "POST",
                            headers: {
                                Accept: "application/json",
                                "Content-Type": "application/json",
                            },
                            body: JSON.stringify({ ...requestPayload, api_key: runtime.api_key }),
                        }, "tavily request failed"),
                    };
                }
            }));
            const recommendations = taskPayloads
                .flatMap(({ task, payload }) => (Array.isArray(payload?.results) ? payload.results : [])
                    .map((item, index) => ({
                        ...publicRecommendationFromTavily(item, task.topic, tavilyResultImage(item, payload?.images, index)),
                        module: task.type,
                        search_topic: task.search_topic || "general",
                        time_range: task.time_range || "",
                    }))
                    .filter((item) => safeCareContentRecommendation(item, task.type, task))
                    .slice(0, 3))
                .filter((item, index, source) => source.findIndex((candidate) => candidate.url === item.url) === index)
                .slice(0, 10);
            return setCachedProviderValue(cacheKey, {
                family_id: Number(familyId || 0),
                city: targetCity,
                topics: normalizedTopics,
                tasks: tasks.map(({ type, topic, query, search_topic, time_range }) => ({ type, topic, query, search_topic, time_range })),
                available: recommendations.length > 0,
                provider: "tavily",
                query: tasks.map((item) => item.query).join(" | "),
                recommendations,
                source_policy: "candidate_only",
                updated_at: nowIso(),
            });
        } catch (error) {
            return unavailableContentRecommendations({
                familyId,
                city: targetCity,
                topics: normalizedTopics,
                provider: "tavily",
                reason: "provider_error",
                detail: error.message,
            });
        }
    }

    async function fetchContentRecommendations({ familyId, city, district = "", preferences }) {
        const resolvedPreferences = preferences || carePreferences(familyId);
        const topics = contentTopicsFromPreferences(resolvedPreferences);
        const contentTypes = resolvedPreferences.metadata?.care_card_schedule?.content_types || {};
        const hasSelectedContent = [
            "elder_interest_topics",
            "local_hotspots",
            "health_tips",
            "anti_fraud",
            "culture_entertainment",
        ].some((key) => contentTypes[key] === true);
        if (resolvedPreferences.content_recommendations_enabled === false && !hasSelectedContent) {
            return unavailableContentRecommendations({
                familyId,
                city,
                topics,
                provider: contentSearchRuntimeConfig().provider,
                reason: "disabled_by_preferences",
            });
        }
        return fetchTavilyContent({ familyId, city, district, topics, preferences: resolvedPreferences });
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
        const timeout = setTimeout(() => controller.abort(), imageGenerationTimeoutMs());
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

    function transcodeCareCardImage(imageBuffer, contentType) {
        if (!Buffer.isBuffer(imageBuffer) || imageBuffer.length < 320 * 1024) {
            return { buffer: imageBuffer, content_type: contentType || "image/png" };
        }
        const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "gohome-care-image-"));
        const inputPath = path.join(tempDir, `input${imageExtension(contentType)}`);
        const outputPath = path.join(tempDir, "output.webp");
        try {
            fs.writeFileSync(inputPath, imageBuffer);
            const result = spawnSync("ffmpeg", [
                "-y",
                "-loglevel", "error",
                "-i", inputPath,
                "-vf", "scale=1024:1024:force_original_aspect_ratio=decrease",
                "-c:v", "libwebp",
                "-quality", "82",
                "-compression_level", "4",
                outputPath,
            ], { timeout: 20_000, maxBuffer: 1024 * 1024 });
            if (result.status !== 0 || !fs.existsSync(outputPath)) {
                return { buffer: imageBuffer, content_type: contentType || "image/png" };
            }
            const optimized = fs.readFileSync(outputPath);
            if (!optimized.length || optimized.length >= imageBuffer.length) {
                return { buffer: imageBuffer, content_type: contentType || "image/png" };
            }
            return { buffer: optimized, content_type: "image/webp" };
        } catch (_error) {
            return { buffer: imageBuffer, content_type: contentType || "image/png" };
        } finally {
            fs.rmSync(tempDir, { recursive: true, force: true });
        }
    }

    function optimizedCareCardFile(asset, filePath) {
        if (asset?.metadata?.purpose !== "care_card_image") return null;
        const stat = fs.statSync(filePath);
        if (stat.size < 320 * 1024) return null;
        const outputPath = `${filePath}.mobile.webp`;
        try {
            const outputStat = fs.existsSync(outputPath) ? fs.statSync(outputPath) : null;
            if (!outputStat || outputStat.mtimeMs < stat.mtimeMs) {
                const result = spawnSync("ffmpeg", [
                    "-y",
                    "-loglevel", "error",
                    "-i", filePath,
                    "-vf", "scale=1024:1024:force_original_aspect_ratio=decrease",
                    "-c:v", "libwebp",
                    "-quality", "82",
                    "-compression_level", "4",
                    outputPath,
                ], { timeout: 20_000, maxBuffer: 1024 * 1024 });
                if (result.status !== 0) return null;
            }
            const optimizedStat = fs.statSync(outputPath);
            return optimizedStat.size > 0 && optimizedStat.size < stat.size ? outputPath : null;
        } catch (_error) {
            return null;
        }
    }

    function storeCareCardImageAsset(card, familyId, imageBuffer, contentType, sourceUrl = "") {
        const optimized = transcodeCareCardImage(imageBuffer, contentType);
        imageBuffer = optimized.buffer;
        contentType = optimized.content_type;
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

    function latestSuccessfulCareImagePath(familyId, runtime) {
        const promptVersion = `care-image:${runtime.prompt_source}:${runtime.prompt_fingerprint}`;
        const job = [...store.db.model_generation_jobs].reverse().find((item) => (
            Number(item.family_id) === Number(familyId)
            && item.purpose === "care_card_image_generation"
            && item.output_status === "succeeded"
            && item.prompt_version === promptVersion
            && String(item.response_payload?.snapshot_path || "").trim()
        ));
        const snapshotPath = String(job?.response_payload?.snapshot_path || "").trim();
        if (!snapshotPath) return "";
        const asset = store.db.assets.find((item) => (
            Number(item.family_id) === Number(familyId)
            && String(item.snapshot_path || "") === snapshotPath
        ));
        return asset ? snapshotPath : "";
    }

    async function ensureCareCardImage(card, familyId, parts = {}) {
        const preferences = parts.preferences || carePreferences(familyId);
        if (!careImageRequested(preferences)) {
            if (!card.image_url) card.image_mode = "none";
            return false;
        }
        if (card.image_url && card.image_mode === "generated" && !parts.forceImage) return true;
        if (card.image_mode === "failed_provider" && !parts.forceImage) return false;
        const runtime = imageRuntimeConfig();
        if (!careImageCallsEnabled() || !imageRuntimeConfigured(runtime)) {
            if (!card.image_url) card.image_mode = "pending_provider";
            return false;
        }
        const retainedImagePath = latestSuccessfulCareImagePath(familyId, runtime);
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
            prompt_fingerprint: runtime.prompt_fingerprint,
        }));
        const job = modelJob({
            family_id: familyId,
            purpose: "care_card_image_generation",
            model: runtime.model,
            prompt_version: `care-image:${runtime.prompt_source}:${runtime.prompt_fingerprint}`,
            input_hash: inputHash,
            output_status: "pending",
            request_payload: {
                capability_id: runtime.capability_id,
                card_id: card.card_id,
            },
            metadata: {
                capability_id: runtime.capability_id,
                provider: "dashscope-wan",
                aspect_ratio: "4:3",
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
            if (retainedImagePath) {
                card.image_mode = "generated";
                card.image_url = retainedImagePath;
            } else if (!card.image_url) {
                card.image_mode = "failed_provider";
            }
            card.updated_at = nowIso();
            card.source_summary = [...new Set([
                ...(Array.isArray(card.source_summary) ? card.source_summary : []),
                retainedImagePath ? "生图失败，已保留最近图片" : "生图失败，已保留文字卡片",
            ])];
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

    function shanghaiDayStart(dayString) {
        const timestamp = Date.parse(`${dayString}T00:00:00+08:00`);
        return Number.isFinite(timestamp) ? timestamp : null;
    }

    function daysUntilDay(dayString, nowMs = Date.now()) {
        const timestamp = shanghaiDayStart(dayString);
        if (timestamp === null) return null;
        return Math.ceil((timestamp - nowMs) / (24 * 60 * 60 * 1000));
    }

    function monthDayFromDate(value) {
        const match = String(value || "").match(/^\d{4}-(\d{2})-(\d{2})$/);
        return match ? { month: match[1], day: match[2] } : null;
    }

    function nextAnnualOccurrence(value, now = new Date()) {
        const parts = monthDayFromDate(value);
        if (!parts) return null;
        const year = Number(new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric" }).format(now));
        const current = `${year}-${parts.month}-${parts.day}`;
        const next = `${year + 1}-${parts.month}-${parts.day}`;
        const currentDays = daysUntilDay(current, now.getTime());
        return currentDays !== null && currentDays >= 0
            ? { date: current, days: currentDays }
            : { date: next, days: daysUntilDay(next, now.getTime()) };
    }

    function holidayCandidates(now = new Date()) {
        const year = Number(new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric" }).format(now));
        const fixed = (targetYear) => [
            { title: "元旦", date: `${targetYear}-01-01` },
            { title: "劳动节", date: `${targetYear}-05-01` },
            { title: "国庆节", date: `${targetYear}-10-01` },
        ];
        const festivalTable = {
            2026: [
                { title: "春节", date: "2026-02-17" },
                { title: "清明节", date: "2026-04-05" },
                { title: "端午节", date: "2026-06-19" },
                { title: "中秋节", date: "2026-09-25" },
            ],
            2027: [
                { title: "春节", date: "2027-02-06" },
                { title: "清明节", date: "2027-04-05" },
                { title: "端午节", date: "2027-06-09" },
                { title: "中秋节", date: "2027-09-15" },
            ],
        };
        return [
            ...fixed(year),
            ...fixed(year + 1),
            ...(festivalTable[year] || []),
            ...(festivalTable[year + 1] || []),
        ];
    }

    function upcomingScheduleFacts(schedule) {
        const facts = [];
        const now = new Date();
        if (schedule.content_types?.anniversaries && schedule.anniversaries?.length) {
            const upcoming = schedule.anniversaries
                .map((item) => {
                    const next = nextAnnualOccurrence(item.date, now);
                    if (!next || next.days === null) return null;
                    return { label: item.label, ...next };
                })
                .filter(Boolean)
                .filter((item) => item.days <= 14)
                .sort((a, b) => a.days - b.days)
                .slice(0, 3);
            if (upcoming.length) {
                facts.push(...upcoming.map((item) => (
                    item.days === 0
                        ? `今天是${item.label}，适合推送纪念日问候。`
                        : `${item.label}还有 ${item.days} 天，按每年 ${item.date.slice(5)} 提醒。`
                )));
            } else {
                facts.push(`已配置 ${schedule.anniversaries.length} 个按月日每年重复的纪念日提醒。`);
            }
        }
        if (schedule.content_types?.holidays) {
            const upcoming = holidayCandidates(now)
                .map((item) => ({ ...item, days: daysUntilDay(item.date, now.getTime()) }))
                .filter((item) => item.days !== null && item.days >= 0 && item.days <= 14)
                .sort((a, b) => a.days - b.days)
                .slice(0, 2);
            if (upcoming.length) {
                facts.push(...upcoming.map((item) => (
                    item.days === 0
                        ? `今天是${item.title}，适合生成节日问候卡片。`
                        : `${item.title}还有 ${item.days} 天，可以提前准备节日问候。`
                )));
            } else {
                facts.push("已开启节日问候，会在常见节日前进入关怀卡片。");
            }
        }
        return facts;
    }

    async function careCardFacts(familyId, preferences = carePreferences(familyId)) {
        const familyIds = new Set([Number(familyId)]);
        const cameras = appConfigCameras(familyIds);
        const onlineCameras = cameras.filter((camera) => String(camera.status || "").toLowerCase() === "online");
        const activeCameraIds = new Set(cameras.filter((camera) => camera.enabled !== false).map((camera) => Number(camera.id)));
        const recentCutoff = Date.now() - 24 * 60 * 60 * 1000;
        const recentEvents = store.db.events.filter((event) => {
            if (isValidationEvent(event)) return false;
            const timestamp = Date.parse(event.occurred_at || event.created_at || "");
            if (!Number.isFinite(timestamp) || timestamp < recentCutoff) return false;
            const eventCamera = store.db.cameras[String(event.camera_id)] || {};
            const eventFamilyId = Number(event.family_id || eventCamera.family_id || 0);
            if (!eventFamilyId || !familyIds.has(eventFamilyId)) return false;
            if (!activeCameraIds.has(Number(event.camera_id))) return false;
            if (event.event_type !== "camera_offline" || event.acknowledged) return true;
            const camera = store.db.cameras[String(event.camera_id)] || {};
            if (String(camera.status || "").toLowerCase() !== "online") return true;
            const seenTime = Date.parse(camera.last_seen_at || camera.edge_reported_at || camera.updated_at || "");
            return !(Number.isFinite(seenTime) && seenTime >= timestamp);
        });
        const openEvents = recentEvents.filter((event) => !event.acknowledged);
        const criticalEvents = openEvents.filter((event) => event.level === "critical");
        const binding = store.db.device_bindings.find((item) => Number(item.family_id) === Number(familyId) && item.status !== "revoked");
        const device = binding ? (store.db.devices[String(binding.device_id)] || {}) : {};
        const family = selectedFamily(familyId) || {};
        const profile = store.db.elder_profiles[elderProfileKey(family.id || familyId, "elder_primary")]
            || defaultElderProfile(family.id || familyId, "elder_primary");
        const schedule = preferences.metadata?.care_card_schedule || defaultCareSchedule();
        const region = contentRegionText(preferences, profile.city || "杭州", profile.district || "");
        const city = String(region.city || profile.city || "杭州").trim() || "杭州";
        const district = String(region.district || profile.district || "").trim();
        const [weather, content] = await Promise.all([
            schedule.content_types?.weather && schedule.delivery_rules?.weather?.enabled !== false
                ? fetchWeatherSignal({ familyId: family.id || familyId, city })
                : unavailableWeatherSignal({ familyId: family.id || familyId, city, provider: weatherRuntimeConfig().provider, reason: "disabled_by_schedule" }),
            (schedule.content_types?.elder_interest_topics
                || schedule.content_types?.local_hotspots
                || schedule.content_types?.health_tips
                || schedule.content_types?.anti_fraud
                || schedule.content_types?.culture_entertainment)
                ? fetchContentRecommendations({ familyId: family.id || familyId, city, district, preferences })
                : unavailableContentRecommendations({
                    familyId: family.id || familyId,
                    city,
                    topics: contentTopicsFromPreferences(preferences),
                    provider: contentSearchRuntimeConfig().provider,
                    reason: "disabled_by_schedule",
                }),
        ]);
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
            const daysUntilVisit = daysUntilDay(schedule.visit_reminder.next_visit_at);
            if (daysUntilVisit !== null && daysUntilVisit >= 0) {
                facts.push(`计划 ${schedule.visit_reminder.next_visit_at} 回家，还有 ${daysUntilVisit} 天。`);
            }
            if (daysSinceVisit !== null) {
                facts.push(`距离上次回家已经 ${daysSinceVisit} 天，提醒阈值是 ${schedule.visit_reminder.threshold_days} 天。`);
            } else {
                facts.push(`已开启回家间隔提醒，阈值是 ${schedule.visit_reminder.threshold_days} 天。`);
            }
        }
        if (schedule.content_types?.elder_interest_topics && schedule.interest_topics?.length) {
            facts.push(`老人关心的话题包括：${schedule.interest_topics.slice(0, 6).join("、")}。`);
        }
        if (schedule.content_types?.weather) {
            if (weather.available) {
                const temp = Number.isFinite(Number(weather.temperature_c)) ? `${weather.temperature_c}°C` : "";
                facts.push(`${weather.city || city} ${weather.condition || "天气已更新"}${temp ? `，${temp}` : ""}，可作为今天问候开场。`);
            } else {
                facts.push("天气数据源暂不可用，本次不会生成实时天气或温度文案。");
            }
        }
        if ((schedule.content_types?.elder_interest_topics
            || schedule.content_types?.local_hotspots
            || schedule.content_types?.health_tips
            || schedule.content_types?.anti_fraud
            || schedule.content_types?.culture_entertainment) && content.available) {
            const first = content.recommendations?.[0];
            if (first?.title) facts.push(`今日内容候选：${first.title}`);
        } else if (schedule.content_types?.elder_interest_topics
            || schedule.content_types?.local_hotspots
            || schedule.content_types?.health_tips
            || schedule.content_types?.anti_fraud
            || schedule.content_types?.culture_entertainment) {
            facts.push("热点内容源暂未接通，先按老人兴趣生成通用聊天话题。");
        }
        facts.push(...upcomingScheduleFacts(schedule));
        if (schedule.message_focus) {
            facts.push(`本次关怀重点：${schedule.message_focus}`);
        }
        return { facts, cameras, onlineCameras, openEvents, criticalEvents, device, profile, weather, content };
    }

    async function generateCareCard(familyId, options = {}) {
        const targetFamilyId = Number(familyId || 0);
        if (!targetFamilyId) {
            throw new Error("family_id required for care card generation");
        }
        const cardDate = dateKeyShanghai();
        const preferences = carePreferences(targetFamilyId);
        const existing = store.db.care_cards.find((card) => (
            Number(card.family_id) === targetFamilyId && card.card_date === cardDate && card.card_type === "daily"
        ));
        if (existing && !options.force) {
            if (careImageRequested(preferences) && !existing.image_url && existing.image_mode !== "failed_provider") {
                const existingParts = await careCardFacts(targetFamilyId, preferences);
                await ensureCareCardImage(existing, targetFamilyId, { ...existingParts, preferences });
            }
            return existing;
        }
        const factParts = await careCardFacts(targetFamilyId, preferences);
        const { facts, openEvents, criticalEvents, profile, weather, content } = factParts;
        const templateContext = careCardModelContext(targetFamilyId, { ...factParts, preferences });
        const templateTheme = contextualCareTheme(templateContext);
        const title = templateTheme.title;
        const body = templateTheme.body;
        const sourceSummary = [
            "设备在线状态",
            "摄像头同步状态",
            "未处理事件",
            "老人资料",
            ...(weather?.available ? ["天气数据源"] : []),
            ...(content?.available ? ["内容搜索候选"] : []),
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
                { key: "message", label: "发一句问候" },
                { key: openEvents.length ? "open_events" : "prepare_greeting", label: openEvents.length ? "查看提醒" : "准备关怀卡" },
            ],
            status: "open",
            generated_by: "care-template-v2",
            source_summary: sourceSummary,
            content_recommendations: content?.available ? content.recommendations : [],
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
                    { key: "message", label: generated.suggested_actions[1] || "发一句问候" },
                    { key: openEvents.length ? "open_events" : "prepare_greeting", label: generated.suggested_actions[2] || (openEvents.length ? "查看提醒" : "准备关怀卡") },
                ];
                card.generated_by = `model:${runtime.model}`;
                card.source_summary = [
                    ...sourceSummary,
                    "多模态语言模型",
                ];
                card.content_recommendations = [
                    ...(content?.available ? content.recommendations : []),
                    ...(generated.image_brief
                        ? [{ type: "image_brief", title: "关怀卡片配图建议", summary: generated.image_brief }]
                        : []),
                ];
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
        const latestExisting = store.db.care_cards.find((item) => (
            item !== card
            && (
                item.card_id === card.card_id
                || (
                    Number(item.family_id) === targetFamilyId
                    && String(item.elder_id || "elder_primary") === String(card.elder_id || "elder_primary")
                    && item.card_date === cardDate
                    && String(item.card_type || "daily") === "daily"
                )
            )
        ));
        if (existing || latestExisting) {
            const target = existing || latestExisting;
            Object.assign(target, card, {
                id: target.id || card.id,
                created_at: target.created_at || card.created_at,
            });
            store.db.care_cards = compactCareCards(store.db.care_cards);
            return target;
        }
        store.db.care_cards.push(card);
        store.db.care_cards = compactCareCards(store.db.care_cards);
        return card;
    }

    function queueCareCardGeneration(familyId) {
        const key = String(familyId);
        if (careCardGenerationJobs.has(key)) return careCardGenerationJobs.get(key);
        const job = Promise.resolve()
            .then(() => generateCareCard(familyId))
            .then((card) => store.save().then(() => card))
            .catch(() => null)
            .finally(() => careCardGenerationJobs.delete(key));
        careCardGenerationJobs.set(key, job);
        return job;
    }

    function immediateCareCard(familyId, cardDate) {
        const latest = store.db.care_cards
            .filter((card) => Number(card.family_id) === Number(familyId) && card.card_type === "daily")
            .sort((a, b) => String(b.card_date || b.created_at || "").localeCompare(String(a.card_date || a.created_at || "")))[0];
        if (latest) return { ...publicCareCard(latest), pending_refresh: true };
        const profile = existingElderProfile(familyId, "elder_primary") || {};
        const displayName = profile.display_name || "家人";
        return {
            id: null,
            card_id: `care-${familyId}-${cardDate}`,
            family_id: Number(familyId),
            elder_id: "elder_primary",
            card_date: cardDate,
            card_type: "daily",
            title: "今天问个安",
            body: `可以先给${displayName}打一通电话，今天的天气、日历和家里状态会在后台整理好。`,
            facts: [],
            source_message_ids: [],
            image_mode: "pending_provider",
            image_url: "",
            actions: [
                { key: "call", label: "打电话问候" },
                { key: "message", label: "发一句问候" },
            ],
            status: "open",
            generated_by: "care-fast-fallback-v1",
            source_summary: [],
            content_recommendations: [],
            created_at: nowIso(),
            updated_at: nowIso(),
            pending_refresh: true,
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

    function ensureDeviceBindings() {
        const candidates = [];
        const explicitlyBoundDeviceIds = new Set(store.db.device_bindings
            .filter((item) => item.status !== "revoked" && item.device_id)
            .map((item) => String(item.device_id)));
        for (const token of store.db.device_tokens) {
            if (token.status !== "active" || !token.family_id || !token.device_id) continue;
            explicitlyBoundDeviceIds.add(String(token.device_id));
            candidates.push({
                family_id: token.family_id,
                device_id: token.device_id,
                device_name: "回家盒子",
                note: token.note || "device token",
            });
        }
        for (const camera of Object.values(store.db.cameras)) {
            if (!camera.family_id || !camera.device_id) continue;
            if (explicitlyBoundDeviceIds.has(String(camera.device_id))) continue;
            candidates.push({
                family_id: camera.family_id,
                device_id: camera.device_id,
                device_name: store.db.devices[String(camera.device_id)]?.name || "回家盒子",
                note: "camera config",
            });
        }
        for (const device of Object.values(store.db.devices)) {
            if (!device.family_id || !(device.device_id || device.id)) continue;
            candidates.push({
                family_id: device.family_id,
                device_id: device.device_id || device.id,
                device_name: device.name || "回家盒子",
                note: "device report",
            });
        }

        let changed = false;
        for (const candidate of candidates) {
            const familyId = normalizeNumber(candidate.family_id, null);
            const deviceId = String(candidate.device_id || "").trim();
            if (!familyId || !deviceId || !selectedFamily(familyId)) continue;
            const beforeCount = store.db.device_bindings.length;
            const binding = bindDeviceToFamily({
                familyId,
                deviceId,
                deviceName: candidate.device_name || "回家盒子",
                note: candidate.note || "auto recovered from local device state",
            });
            if (!binding) continue;
            if (store.db.device_bindings.length > beforeCount) {
                changed = true;
            }
        }
        return changed;
    }

    function eventTimestamp(event = {}) {
        const timestamp = Date.parse(event.occurred_at || event.created_at || "");
        return Number.isFinite(timestamp) ? timestamp : null;
    }

    function isStaleCameraOfflineEvent(event = {}) {
        if (String(event.event_type || event.type || "") !== "camera_offline" || event.acknowledged) return false;
        const camera = store.db.cameras[String(event.camera_id)] || {};
        if (String(camera.status || "").toLowerCase() !== "online") return false;
        const eventTime = eventTimestamp(event);
        const seenTime = Date.parse(camera.last_seen_at || camera.edge_reported_at || camera.updated_at || "");
        return Number.isFinite(eventTime) && Number.isFinite(seenTime) && seenTime >= eventTime;
    }

    function isValidationEvent(event = {}) {
        const validation = event.payload?.validation;
        return Boolean(validation && typeof validation === "object" && validation.test_event);
    }

    function isUserVisibleEvent(event = {}, familyIds = null) {
        if (isValidationEvent(event)) return false;
        const activeCameraIds = new Set(appConfigCameras(familyIds).filter((camera) => camera.enabled !== false).map((camera) => Number(camera.id)));
        if (activeCameraIds.size && !activeCameraIds.has(Number(event.camera_id))) return false;
        if (isStaleCameraOfflineEvent(event)) return false;
        return true;
    }

    function eventList(url, options = {}) {
        const limit = Math.min(100, Math.max(1, normalizeNumber(url.searchParams.get("limit"), 30)));
        const cameraId = normalizeNumber(url.searchParams.get("camera_id"), null);
        const acknowledged = url.searchParams.get("acknowledged");
        let events = [...store.db.events];
        if (options.familyIds instanceof Set) {
            events = events.filter((event) => {
                const camera = store.db.cameras[String(event.camera_id)] || {};
                const familyId = Number(event.family_id || camera.family_id || 0);
                return options.familyIds.has(familyId);
            });
        }
        if (cameraId !== null) {
            events = events.filter((event) => Number(event.camera_id) === cameraId);
        }
        if (options.userVisible) {
            events = events.filter((event) => isUserVisibleEvent(event, options.familyIds));
            if (cameraId === null) {
                events = events.filter((event) => (
                    !event.payload?.incident
                    || String(event.payload.incident.primary_event_id || event.id) === String(event.id)
                ));
            }
        }
        if (acknowledged !== null) {
            const expected = normalizeBool(acknowledged);
            events = events.filter((event) => Boolean(event.acknowledged) === expected);
        }
        const project = url.searchParams.get("view") === "summary" ? publicEventSummary : publicEvent;
        return events
            .sort((a, b) => String(b.occurred_at || b.created_at).localeCompare(String(a.occurred_at || a.created_at)))
            .slice(0, limit)
            .map(project);
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
            family_id: existing.family_id || store.db.devices[deviceId]?.family_id || null,
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

    function isValidationAsset(asset) {
        const purpose = String(asset?.purpose || "").toLowerCase();
        if (purpose.startsWith("validation") || purpose.startsWith("test")) return true;
        return store.db.events.some((event) => Number(event.media_asset_id) === Number(asset?.id) && isValidationEvent(event));
    }

    function latestCameraAsset(cameraId = null, options = {}) {
        const targetCameraId = cameraId === null ? null : Number(cameraId);
        const purposes = new Set((options.purposes || []).map((item) => String(item).toLowerCase()));
        return [...store.db.assets]
            .filter((asset) => asset.relative_path && (targetCameraId === null || Number(asset.camera_id) === targetCameraId))
            .filter((asset) => !isValidationAsset(asset))
            .filter((asset) => !purposes.size || purposes.has(String(asset.purpose || "").toLowerCase()))
            .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")))[0] || null;
    }

    function familyIdForCamera(cameraId) {
        const camera = store.db.cameras[String(cameraId)] || null;
        if (camera) return camera.family_id || null;
        const event = latestMediaEvent(cameraId);
        if (event) {
            const eventCamera = store.db.cameras[String(event.camera_id)] || {};
            return event.family_id || eventCamera.family_id || null;
        }
        return null;
    }

    function requireCameraAccess(req, res, cameraId) {
        const familyId = familyIdForCamera(cameraId);
        if (!familyId) {
            writeError(res, 404, "camera not found");
            return false;
        }
        return requireFamilyAccess(req, res, familyId);
    }

    function eventAsset(event) {
        if (!event?.media_asset_id) return null;
        return store.db.assets.find((asset) => Number(asset.id) === Number(event.media_asset_id)) || null;
    }

    function familyIdForAsset(asset) {
        if (!asset) return null;
        if (asset.family_id) return asset.family_id;
        if (asset.camera_id) {
            const cameraFamilyId = familyIdForCamera(asset.camera_id);
            if (cameraFamilyId) return cameraFamilyId;
        }
        const event = store.db.events.find((item) => Number(item.media_asset_id) === Number(asset.id));
        if (event) {
            const camera = store.db.cameras[String(event.camera_id)] || {};
            return event.family_id || camera.family_id || null;
        }
        return null;
    }

    function requireAssetAccess(req, res, asset) {
        const familyId = familyIdForAsset(asset);
        if (!familyId) {
            writeError(res, 404, "media asset not found");
            return false;
        }
        return requireFamilyAccess(req, res, familyId);
    }

    function latestCameraSnapshotPayload(cameraId) {
        const asset = latestCameraAsset(cameraId, { purposes: ["live_preview"] });
        if (!asset) return { available: false };
        return {
            available: true,
            id: null,
            asset_id: asset.id,
            camera_id: asset.camera_id || Number(cameraId),
            image_url: asset.snapshot_path,
            snapshot_path: asset.snapshot_path,
            captured_at: asset.captured_at || asset.created_at,
            width: asset.width || null,
            height: asset.height || null,
            brightness: asset.brightness ?? null,
            motion_score: asset.motion_score ?? null,
            person_count: asset.person_count ?? null,
            tags: [],
            analysis: {
                event_type: "latest_frame",
                summary: "家庭盒子最新实时预览",
            },
        };
    }

    function latestCameraEvaluationPayload(cameraId) {
        const targetCameraId = Number(cameraId);
        const camera = store.db.cameras[String(targetCameraId)] || {};
        const event = [...store.db.events]
            .filter((item) => Number(item.camera_id) === targetCameraId)
            .filter((item) => !isValidationEvent(item))
            .filter((item) => !isStaleCameraOfflineEvent(item))
            .sort((a, b) => String(b.occurred_at || b.created_at).localeCompare(String(a.occurred_at || a.created_at)))[0];
        if (!event) {
            const status = String(camera.status || "").toLowerCase();
            const enabled = camera.enabled !== false;
            const cameraState = !enabled
                ? "disabled"
                : status === "online"
                    ? "online"
                    : status || "unknown";
            const evaluatedAt = camera.last_seen_at || camera.edge_reported_at || camera.updated_at || nowIso();
            const explanation = !enabled
                ? "这路摄像头已停用，不参与守护检测。"
                : status === "online"
                    ? "摄像头在线，最近没有命中需要家属确认的规则。"
                    : "等待家庭盒子回传这路摄像头的检测结果。";
            return {
                camera_id: targetCameraId,
                snapshot_id: null,
                evaluated_at: evaluatedAt,
                matched_rules: [],
                score: null,
                state: {
                    camera_state: cameraState,
                    camera_status: camera.status || "",
                    sync_status: camera.sync_status || "",
                    enabled,
                    last_seen_at: camera.last_seen_at || null,
                    edge_reported_at: camera.edge_reported_at || null,
                },
                candidates: [],
                explanation,
                analysis: {
                    camera_status: camera.status || "",
                    sync_status: camera.sync_status || "",
                    tags: [],
                },
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

    function latestCameraEvaluationSummaryPayload(cameraId) {
        const evaluation = latestCameraEvaluationPayload(cameraId);
        const posture = evaluation.analysis?.posture
            || evaluation.analysis?.pose_factor_graph?.posture
            || evaluation.candidates?.[0]?.payload?.verification?.result?.posture
            || evaluation.candidates?.[0]?.payload?.evidence?.posture
            || evaluation.candidates?.[0]?.payload?.evidence?.pose_factor_graph?.posture
            || "";
        return {
            camera_id: evaluation.camera_id,
            evaluated_at: evaluation.evaluated_at,
            score: evaluation.score,
            state: evaluation.state || {},
            explanation: evaluation.explanation || "",
            analysis: posture ? { posture, pose_factor_graph: { posture } } : {},
            candidates: posture ? [{ payload: {
                verification: { result: { posture } },
                evidence: { posture },
            } }] : [],
        };
    }

    function serveLatestCameraSnapshot(req, res, cameraId) {
        if (!requireApp(req, res)) return;
        if (!requireCameraAccess(req, res, cameraId)) return;
        write(res, 200, latestCameraSnapshotPayload(cameraId));
    }

    function serveLatestCameraEvaluation(req, res, cameraId, url) {
        if (!requireApp(req, res)) return;
        if (!requireCameraAccess(req, res, cameraId)) return;
        const summary = url?.searchParams?.get("view") === "summary";
        write(res, 200, summary ? latestCameraEvaluationSummaryPayload(cameraId) : latestCameraEvaluationPayload(cameraId));
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

    function writeLatestFrameImage(res, cameraId) {
        const asset = latestCameraAsset(cameraId, { purposes: ["live_preview"] });
        const filePath = assetAbsolutePath(asset);
        if (!asset || !filePath || !fs.existsSync(filePath)) return false;

        const stat = fs.statSync(filePath);
        if (!stat.isFile() || stat.size <= 0) return false;

        const headers = {
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-store, no-transform",
            "Connection": "close",
            "Content-Length": String(stat.size),
            "Content-Type": asset.content_type || "image/jpeg",
            "X-GoHome-Stream-State": "latest_snapshot",
        };
        if (asset.id) headers["X-GoHome-Asset-Id"] = String(asset.id);
        res.writeHead(200, headers);
        fs.createReadStream(filePath).pipe(res);
        return true;
    }

    function latestLiveFrame(cameraId) {
        const item = liveFrameCache.get(String(cameraId));
        if (!item?.frame || Date.now() - Number(item.received_at_ms || 0) > LIVE_FRAME_TTL_MS) return null;
        return item;
    }

    function latestRelayFrame(cameraId) {
        const live = latestLiveFrame(cameraId);
        if (live) {
            return {
                key: `live:${live.frame_id}`,
                frame: live.frame,
                contentType: live.content_type || "image/jpeg",
                capturedAt: live.captured_at || live.received_at,
                source: "live",
                assetId: "",
            };
        }

        const asset = latestCameraAsset(cameraId, { purposes: ["live_preview"] });
        const filePath = assetAbsolutePath(asset);
        if (!asset || !filePath || !fs.existsSync(filePath)) return null;
        let stat;
        try {
            stat = fs.statSync(filePath);
        } catch (_error) {
            return null;
        }
        if (!stat.isFile() || stat.size <= 0) return null;
        let frame;
        try {
            frame = fs.readFileSync(filePath);
        } catch (_error) {
            return null;
        }
        if (!frame.length) return null;
        return {
            key: `asset:${asset.id || ""}:${asset.relative_path || ""}:${stat.mtimeMs}:${stat.size}`,
            frame,
            contentType: asset.content_type || "image/jpeg",
            capturedAt: asset.captured_at || asset.created_at,
            source: "asset",
            assetId: asset.id ? String(asset.id) : "",
        };
    }

    function writeLatestFrameMjpegStream(req, res, cameraId) {
        const boundary = `gohome-${crypto.randomBytes(4).toString("hex")}`;
        let lastAssetKey = "";
        let closed = false;

        if (typeof req.setTimeout === "function") req.setTimeout(0);
        if (req.socket && typeof req.socket.setTimeout === "function") req.socket.setTimeout(0);

        res.writeHead(200, {
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-store, no-transform",
            "Connection": "keep-alive",
            "Content-Type": `multipart/x-mixed-replace; boundary=${boundary}`,
            "X-Accel-Buffering": "no",
            "X-GoHome-Stream-State": "cloud_relay",
        });
        if (typeof res.flushHeaders === "function") res.flushHeaders();

        function writeNextFrame({ force = false } = {}) {
            if (closed || res.destroyed || res.writableEnded) return;
            const relayFrame = latestRelayFrame(cameraId);
            if (!relayFrame) return;
            if (!force && relayFrame.key === lastAssetKey) return;
            lastAssetKey = relayFrame.key;
            res.write(`--${boundary}\r\n`);
            res.write(`Content-Type: ${relayFrame.contentType}\r\n`);
            res.write(`Content-Length: ${relayFrame.frame.length}\r\n`);
            res.write(`X-GoHome-Frame-Source: ${relayFrame.source}\r\n`);
            if (relayFrame.assetId) res.write(`X-GoHome-Asset-Id: ${relayFrame.assetId}\r\n`);
            if (relayFrame.capturedAt) {
                res.write(`X-GoHome-Captured-At: ${relayFrame.capturedAt}\r\n`);
            }
            res.write("\r\n");
            res.write(relayFrame.frame);
            res.write("\r\n");
        }

        writeNextFrame({ force: true });
        const timer = setInterval(writeNextFrame, 120);
        req.on("close", () => {
            closed = true;
            clearInterval(timer);
        });
        res.on("close", () => {
            closed = true;
            clearInterval(timer);
        });
        return true;
    }

    async function handleDeviceLiveFrameUpload(req, res, url) {
        if (!requireDevice(req, res)) return;
        const issuedToken = issuedDeviceTokenFromRequest(req);
        const content = await readBody(req, 4 * 1024 * 1024);
        if (!content.length) {
            writeError(res, 400, "live frame body is empty");
            return;
        }
        const rawCameraId = url.searchParams.get("camera_id");
        const localCameraId = url.searchParams.get("local_camera_id") || rawCameraId;
        const mappedCamera = resolveAppCameraForDeviceCameraId(rawCameraId, {
            local_camera_id: localCameraId,
            edge_camera_id: localCameraId,
        }, issuedToken?.device_id || "");
        const cameraId = normalizeNumber(mappedCamera?.id || rawCameraId, null);
        if (!cameraId) {
            writeError(res, 400, "camera_id is required");
            return;
        }
        const sequence = Number(liveFrameSequence.get(String(cameraId)) || 0) + 1;
        liveFrameSequence.set(String(cameraId), sequence);
        const receivedAt = nowIso();
        liveFrameCache.set(String(cameraId), {
            frame_id: `${cameraId}-${Date.now()}-${sequence}`,
            frame: content,
            camera_id: cameraId,
            local_camera_id: normalizeNumber(localCameraId, null),
            device_id: issuedToken?.device_id || "",
            content_type: url.searchParams.get("content_type") || req.headers["content-type"] || "image/jpeg",
            captured_at: url.searchParams.get("captured_at") || receivedAt,
            received_at: receivedAt,
            received_at_ms: Date.now(),
            size: content.length,
        });
        write(res, 200, {
            ok: true,
            camera_id: cameraId,
            live_frame_id: liveFrameCache.get(String(cameraId)).frame_id,
            received_at: receivedAt,
        });
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

        for (const localCameraId of target.localCameraIds) {
            const deviceUrl = applyStreamParams(new URL(`/api/v1/device/cameras/${localCameraId}/stream.mjpg`, target.base), req);
            const deviceProxied = await proxyMjpegRequest(req, res, deviceUrl, {
                Authorization: `Bearer ${target.token}`,
                "X-GoHome-Device-Token": target.token,
            }, {
                "X-GoHome-Device-Base": target.base,
                "X-GoHome-Local-Camera-Id": String(localCameraId),
                "X-GoHome-Proxy-Mode": "device-token",
            });
            if (deviceProxied || res.headersSent) return deviceProxied;
        }

        const adminCookie = await requestBoxAdminCookie(target.base);
        if (!adminCookie) return false;
        for (const localCameraId of target.localCameraIds) {
            const adminUrl = applyStreamParams(new URL(`/api/cameras/${localCameraId}/stream.mjpg`, target.base), req);
            const adminProxied = await proxyMjpegRequest(req, res, adminUrl, { Cookie: adminCookie }, {
                "X-GoHome-Device-Base": target.base,
                "X-GoHome-Local-Camera-Id": String(localCameraId),
                "X-GoHome-Proxy-Mode": "admin-cookie",
            });
            if (adminProxied || res.headersSent) return adminProxied;
        }
        return false;
    }

    async function serveCameraMjpeg(req, res, cameraId) {
        if (!requireApp(req, res)) return;
        if (!requireCameraAccess(req, res, cameraId)) return;
        if (isLocalBrowserRequest(req) && await proxyCameraMjpeg(req, res, cameraId)) return;
        if (writeLatestFrameMjpegStream(req, res, cameraId)) return;
        if (await proxyCameraMjpeg(req, res, cameraId)) return;
        if (writeLatestFrameImage(res, cameraId)) return;
        writeEmptyMjpeg(res);
    }

    async function handleDeviceMediaUpload(req, res, url) {
        if (!requireDevice(req, res)) return;
        const issuedToken = issuedDeviceTokenFromRequest(req);
        const content = await readBody(req);
        const assetId = store.nextId("asset");
        const fileName = path.basename(url.searchParams.get("file_name") || `asset-${assetId}.jpg`).replace(/[^\w.\-]+/g, "_");
        const dateDir = new Date().toISOString().slice(0, 10);
        const relativePath = path.join(dateDir, `${assetId}-${fileName}`);
        const target = path.join(mediaDir, relativePath);
        ensureDir(path.dirname(target));
        fs.writeFileSync(target, content);
        const snapshotPath = String(url.searchParams.get("snapshot_path") || relativePath).replace(/^\/+/, "");
        const rawCameraId = url.searchParams.get("camera_id");
        const localCameraId = url.searchParams.get("local_camera_id") || rawCameraId;
        const mappedCamera = resolveAppCameraForDeviceCameraId(rawCameraId, {
            local_camera_id: localCameraId,
            edge_camera_id: localCameraId,
        }, issuedToken?.device_id || "");
        const cameraId = normalizeNumber(mappedCamera?.id || rawCameraId, null);
        const asset = {
            id: assetId,
            family_id: issuedToken?.family_id || mappedCamera?.family_id || null,
            device_id: issuedToken?.device_id || mappedCamera?.device_id || "",
            camera_id: cameraId,
            file_name: fileName,
            content_type: url.searchParams.get("content_type") || req.headers["content-type"] || "image/jpeg",
            snapshot_path: snapshotPath,
            relative_path: relativePath,
            edge_event_id: url.searchParams.get("edge_event_id") || "",
            purpose: url.searchParams.get("purpose") || "",
            evidence_frame_role: url.searchParams.get("evidence_frame_role") || "",
            local_camera_id: normalizeNumber(localCameraId, null),
            captured_at: url.searchParams.get("captured_at") || nowIso(),
            size: content.length,
            created_at: nowIso(),
            updated_at: nowIso(),
            url: `/api/v1/video/media/snapshots/${encodeURIComponent(snapshotPath)}`,
        };
        store.db.assets.push(asset);
        await store.save();
        write(res, 200, { ok: true, asset });
    }

    async function handleDeviceEvent(req, res) {
        if (!requireDevice(req, res)) return;
        const issuedToken = issuedDeviceTokenFromRequest(req);
        const payload = await parseJsonBody(req);
        const camera = upsertCamera(payload);
        const edgeEventId = payload.payload?.edge_upload?.edge_event_id || payload.edge_event_id || "";
        const mediaFromPayload = payload.media_upload_result?.asset || payload.payload?.media_upload_result?.asset || null;
        const deviceAsset = (item) => Boolean(
            item
            && (!issuedToken?.device_id || String(item.device_id || "") === String(issuedToken.device_id))
            && (!edgeEventId || String(item.edge_event_id || "") === String(edgeEventId))
        );
        const asset = mediaFromPayload?.id
            ? store.db.assets.find((item) => Number(item.id) === Number(mediaFromPayload.id) && deviceAsset(item))
            : [...store.db.assets].reverse().find((item) => deviceAsset(item));
        const requestedEvidenceAssets = Array.isArray(payload.payload?.evidence_media_assets)
            ? payload.payload.evidence_media_assets
            : [];
        const evidenceMediaAssets = requestedEvidenceAssets
            .map((entry) => {
                const requestedAssetId = normalizeNumber(entry?.asset?.id || entry?.asset_id || entry?.id, null);
                const matched = requestedAssetId === null
                    ? null
                    : store.db.assets.find((item) => Number(item.id) === requestedAssetId && deviceAsset(item));
                if (!matched) return null;
                return {
                    asset_id: matched.id,
                    role: String(entry.role || matched.evidence_frame_role || "evidence"),
                    captured_at: String(entry.captured_at || matched.captured_at || ""),
                    snapshot_id: normalizeNumber(entry.snapshot_id, null),
                    postures: Array.isArray(entry.postures) ? entry.postures.map(String).slice(0, 8) : [],
                };
            })
            .filter(Boolean)
            .filter((entry, index, items) => items.findIndex((item) => Number(item.asset_id) === Number(entry.asset_id)) === index)
            .slice(0, 3);
        const event = {
            id: store.nextId("event"),
            family_id: camera?.family_id || store.db.devices[String(camera?.device_id || "")]?.family_id || null,
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
                evidence_media_assets: evidenceMediaAssets,
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
        const correlatedPrimary = correlateSafetyIncident(event);
        ensureSafetyIncident(event);
        store.db.events.push(event);
        let message = null;
        let deliveries = [];
        if (event.family_id && !isValidationEvent(event) && !correlatedPrimary) {
            message = upsertAppMessage({
                message_id: `edge-event-${event.idempotency_key}`,
                family_id: event.family_id,
                message_type: event.level === "critical" ? "alert" : "explain",
                title: event.summary,
                subtitle: `${event.room || event.camera_name || "家中"} · 守护提醒`,
                body: String(event.payload?.rule?.reason || event.summary || "家庭盒子检测到一条需要查看的情况。"),
                facts: [event.event_type, event.level],
                actions: [{ key: "open_event", label: "查看事件", event_id: event.id }],
                source_event_ids: [event.id],
                generated_by: "edge-event",
                status: "open",
                priority: event.level === "critical" ? "high" : "normal",
                metadata: {
                    incident_id: event.payload?.incident?.incident_id || "",
                    incident_status: event.payload?.incident?.status || "",
                },
                created_at: event.occurred_at,
            });
            if (currentRules(event.family_id).notification_enabled) {
                deliveries = queueNotificationDelivery(message);
            }
        }
        const verificationJob = queueVisionVerification(event, asset);
        if (!verificationJob && event.payload?.verification) {
            applyIncidentVerificationOutcome(event);
        }
        await store.save();
        if (verificationJob) {
            setImmediate(() => {
                processVisionVerificationJobs({ limit: 1 })
                    .catch((error) => console.error(`vision verification failed: ${error.message || error}`));
            });
        }
        write(res, 200, {
            ok: true,
            event: publicEvent(event),
            media_asset: asset || null,
            message: message ? publicAppMessage(message) : null,
            deliveries: deliveries.map(publicNotificationDelivery),
            verification: event.payload?.verification || null,
        });
    }

    function deviceVisionVerificationStatus(req, res, url) {
        if (!requireDevice(req, res)) return;
        const issuedToken = issuedDeviceTokenFromRequest(req);
        const deviceId = String(issuedToken?.device_id || currentEdgeDeviceId() || "");
        const familyId = normalizeNumber(issuedToken?.family_id, null);
        const limit = Math.max(1, Math.min(50, normalizeNumber(url.searchParams.get("limit"), 12)));
        const deviceEvents = store.db.events
            .filter((event) => {
                const camera = store.db.cameras[String(event.camera_id || "")] || {};
                const edgeDeviceId = String(event.payload?.edge_upload?.edge_device_id || camera.device_id || "");
                if (deviceId && edgeDeviceId) return edgeDeviceId === deviceId;
                if (familyId) return Number(event.family_id || camera.family_id) === Number(familyId);
                return false;
            })
            .filter((event) => event.payload?.verification)
            .sort((a, b) => String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || "")))
            .slice(0, limit);
        const records = deviceEvents.map((event) => {
            const verification = event.payload?.verification || {};
            const job = verification.job_id
                ? store.db.model_generation_jobs.find((item) => String(item.id) === String(verification.job_id))
                : verificationJobForEvent(event.id);
            return {
                event_id: event.id,
                edge_event_id: event.edge_event_id || event.payload?.edge_upload?.edge_event_id || "",
                event_type: event.event_type,
                summary: event.summary,
                level: event.level,
                room: event.room || event.camera_name || "",
                occurred_at: event.occurred_at,
                updated_at: event.updated_at,
                incident: event.payload?.incident || null,
                verification,
                job: job ? {
                    id: job.id,
                    output_status: job.output_status,
                    model: job.model,
                    attempt_count: Number(job.metadata?.attempt_count || 0),
                    orchestration_status: job.metadata?.orchestration_status || "",
                    orchestration_message_id: job.metadata?.orchestration_message_id || "",
                    error_message: job.error_message || "",
                    response_payload: job.response_payload || {},
                    created_at: job.created_at,
                    updated_at: job.updated_at,
                } : null,
            };
        });
        write(res, 200, {
            ok: true,
            device_id: deviceId,
            enabled: visionVerificationEnabled(),
            configured: Boolean(
                visionVerificationRuntimeConfig().base_url
                && visionVerificationRuntimeConfig().api_key
                && visionVerificationRuntimeConfig().model
            ),
            running: visionVerificationRunning,
            records,
            generated_at: nowIso(),
        });
    }

    function deviceEventLog(req, res, url) {
        if (!requireDevice(req, res)) return;
        const issuedToken = issuedDeviceTokenFromRequest(req);
        const deviceId = String(issuedToken?.device_id || currentEdgeDeviceId() || "");
        const familyId = normalizeNumber(issuedToken?.family_id, null);
        const limit = Math.max(1, Math.min(200, normalizeNumber(url.searchParams.get("limit"), 80)));
        const records = store.db.events
            .filter((event) => {
                const camera = store.db.cameras[String(event.camera_id || "")] || {};
                const edgeDeviceId = String(event.payload?.edge_upload?.edge_device_id || camera.device_id || "");
                if (deviceId && edgeDeviceId) return edgeDeviceId === deviceId;
                if (familyId) return Number(event.family_id || camera.family_id) === Number(familyId);
                return false;
            })
            .sort((a, b) => String(b.occurred_at || b.created_at || "").localeCompare(String(a.occurred_at || a.created_at || "")))
            .slice(0, limit)
            .map((event) => ({
                event_id: event.id,
                edge_event_id: event.edge_event_id || event.payload?.edge_upload?.edge_event_id || "",
                event_type: event.event_type,
                summary: event.summary,
                level: event.level,
                room: event.room || event.camera_name || "",
                camera_id: event.camera_id,
                occurred_at: event.occurred_at,
                updated_at: event.updated_at,
                acknowledged: Boolean(event.acknowledged),
                resolution: event.resolution || "",
                incident: event.payload?.incident || null,
                verification: event.payload?.verification || null,
                media_asset_id: event.media_asset_id || null,
            }));
        write(res, 200, { ok: true, device_id: deviceId, records });
    }

    async function handleDeviceEventFeedback(req, res, edgeEventId) {
        if (!requireDevice(req, res)) return;
        const issuedToken = issuedDeviceTokenFromRequest(req);
        const deviceId = String(issuedToken?.device_id || currentEdgeDeviceId() || "");
        const familyId = normalizeNumber(issuedToken?.family_id, null);
        const payload = await parseJsonBody(req);
        if (String(payload.resolution || "") !== "false_positive") {
            writeError(res, 400, "only false_positive feedback is supported");
            return;
        }
        const event = store.db.events.find((item) => {
            if (String(item.edge_event_id || item.payload?.edge_upload?.edge_event_id || "") !== String(edgeEventId || "")) return false;
            const camera = store.db.cameras[String(item.camera_id || "")] || {};
            const edgeDeviceId = String(item.payload?.edge_upload?.edge_device_id || camera.device_id || "");
            if (deviceId && edgeDeviceId) return edgeDeviceId === deviceId;
            if (familyId) return Number(item.family_id || camera.family_id) === Number(familyId);
            return false;
        });
        if (!event) {
            writeError(res, 404, "event not found");
            return;
        }
        rejectSafetyIncidentAsFalsePositive(event);
        await store.save();
        write(res, 200, { ok: true, event: publicEvent(event) });
    }

    async function handleDeviceEventState(req, res, edgeEventId) {
        if (!requireDevice(req, res)) return;
        const issuedToken = issuedDeviceTokenFromRequest(req);
        const deviceId = String(issuedToken?.device_id || currentEdgeDeviceId() || "");
        const familyId = normalizeNumber(issuedToken?.family_id, null);
        const payload = await parseJsonBody(req);
        const state = String(payload.state || "");
        const resolution = String(payload.resolution || "");
        const evidence = payload.evidence && typeof payload.evidence === "object" ? payload.evidence : {};
        if (state !== "resolved" || resolution !== "person_upright_again") {
            writeError(res, 400, "unsupported event state transition");
            return;
        }
        const posture = String(evidence.posture || "");
        const confidence = Number(evidence.confidence || 0);
        if (!["standing", "sitting", "squatting"].includes(posture) || !Number.isFinite(confidence) || confidence < 0.45) {
            writeError(res, 400, "credible upright recovery evidence is required");
            return;
        }
        const event = store.db.events.find((item) => {
            if (String(item.edge_event_id || item.payload?.edge_upload?.edge_event_id || "") !== String(edgeEventId || "")) return false;
            const camera = store.db.cameras[String(item.camera_id || "")] || {};
            const edgeDeviceId = String(item.payload?.edge_upload?.edge_device_id || camera.device_id || "");
            if (deviceId && edgeDeviceId) return edgeDeviceId === deviceId;
            if (familyId) return Number(item.family_id || camera.family_id) === Number(familyId);
            return false;
        });
        if (!event) {
            writeError(res, 404, "event not found");
            return;
        }
        if (!["fall_candidate", "prolonged_floor_lying"].includes(event.event_type)) {
            writeError(res, 400, "event type does not support posture recovery");
            return;
        }
        const incident = ensureSafetyIncident(event);
        const linkedEvents = incident ? incidentEvents(incident.incident_id) : [event];
        const resolvedAt = String(payload.observed_at || nowIso());
        for (const linked of linkedEvents) {
            linked.acknowledged = true;
            linked.resolution = resolution;
            linked.payload = linked.payload && typeof linked.payload === "object" ? linked.payload : {};
            linked.payload.edge_recovery = {
                observed_at: resolvedAt,
                evidence: {
                    posture,
                    confidence: Number(confidence.toFixed(4)),
                    track_id: String(evidence.track_id || ""),
                    bbox: Array.isArray(evidence.bbox) ? evidence.bbox.slice(0, 4) : [],
                },
            };
            const linkedIncident = ensureSafetyIncident(linked);
            linkedIncident.status = "resolved";
            linkedIncident.resolved_at = resolvedAt;
            linked.updated_at = nowIso();
        }
        if (incident) {
            appendIncidentTransition(incidentPrimaryEvent(event), "resolved", "edge_recovery", {
                resolution,
                observed_at: resolvedAt,
                posture,
                confidence: Number(confidence.toFixed(4)),
            });
            archiveIncidentMessages(incident.incident_id);
        }
        await store.save();
        write(res, 200, { ok: true, event: publicEvent(event) });
    }

    async function handleHeartbeat(req, res) {
        if (!requireDevice(req, res)) return;
        const payload = await parseJsonBody(req);
        const deviceId = String(payload.device_id || payload.id || "edge-local");
        const issuedToken = issuedDeviceTokenFromRequest(req);
        if (issuedToken) {
            issuedToken.device_id = deviceId;
            issuedToken.last_heartbeat_at = nowIso();
        }
        store.db.devices[deviceId] = {
            ...store.db.devices[deviceId],
            ...payload,
            id: deviceId,
            device_id: deviceId,
            family_id: store.db.devices[deviceId]?.family_id || issuedToken?.family_id || null,
            last_seen_at: nowIso(),
        };
        store.db.heartbeats.push({
            id: store.nextId("heartbeat"),
            device_id: deviceId,
            payload,
            created_at: nowIso(),
        });
        ensureDeviceBindings();
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
        const issuedToken = issuedDeviceTokenFromRequest(req);
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
            family_id: existingDevice.family_id || issuedToken?.family_id || null,
            name: payload.device_name || existingDevice.name || "回家盒子",
            status: String(reportedStatus.status || payload.device_status || "online"),
            worker_running: payload.worker_running ?? existingDevice.worker_running ?? null,
            lan_url: deviceLanUrl || existingDevice.lan_url || "",
            service_url: deviceServiceUrl || existingDevice.service_url || "",
            last_seen_at: receivedAt,
            last_sync_at: receivedAt,
            reported_config_version: String(payload.config_version || payload.applied_config_version || ""),
            applied_rule_version: String(payload.applied_rule_version || existingDevice.applied_rule_version || ""),
            app_version: String(payload.app_version || existingDevice.app_version || ""),
            model_version: String(payload.model_version || existingDevice.model_version || ""),
            detector_backend: detectorBackend || existingDevice.detector_backend || "",
            yolo_model: yoloModel || existingDevice.yolo_model || "",
            yolo_imgsz: yoloImgsz ?? existingDevice.yolo_imgsz ?? null,
            runtime,
            maintenance: payload.maintenance || existingDevice.maintenance || {},
            metadata: {
                ...objectValue(existingDevice.metadata),
                serial_number: objectValue(existingDevice.metadata).serial_number || deviceSerial({ ...existingDevice, device_id: deviceId }),
            },
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
            const resolvedFamilyId = existing.family_id || issuedToken?.family_id || store.db.devices[deviceId]?.family_id || null;
            if (!resolvedFamilyId && !isAppConfiguredCamera(existing)) continue;
            const reportLocalCameraId = report.local_camera_id ?? existing.local_camera_id ?? (!isAppConfiguredCamera(existing) ? rawCameraId : null);
            const presence = report.presence && typeof report.presence === "object" ? report.presence : (existing.presence || {});
            const camera = {
                ...existing,
                id: existing.id || rawCameraId,
                family_id: resolvedFamilyId,
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
                presence: {
                    last_observed_at: presence.last_observed_at || null,
                    last_person_seen_at: presence.last_person_seen_at || null,
                    observation_window_minutes: normalizeNumber(presence.observation_window_minutes, 60),
                    observed_samples: normalizeNumber(presence.observed_samples, 0),
                    person_samples: normalizeNumber(presence.person_samples, 0),
                    last_pet_seen_at: presence.last_pet_seen_at || null,
                    last_pet_count: Math.max(0, normalizeNumber(presence.last_pet_count, 0)),
                    pet_types: Array.isArray(presence.pet_types) ? presence.pet_types.map(String).filter(Boolean) : [],
                    expected_samples: normalizeNumber(presence.expected_samples, 0),
                    observation_coverage: Math.max(0, Math.min(1, normalizeNumber(presence.observation_coverage, 0))),
                    reported_at: receivedAt,
                },
                created_at: existing.created_at || receivedAt,
                updated_at: existing.updated_at || receivedAt,
            };
            store.db.cameras[targetKey] = camera;
            updatedCameras.push(publicCamera(camera));
        }

        ensureDeviceBindings();
        await store.save();
        const deviceFamilyId = store.db.devices[deviceId]?.family_id || issuedToken?.family_id || null;
        write(res, 200, {
            ok: true,
            device_id: deviceId,
            received_at: receivedAt,
            reported_config_version: store.db.devices[deviceId].reported_config_version,
            current_config_version: deviceConfigVersion(deviceFamilyId),
            rules_version: rulesVersion(deviceFamilyId),
            updated_cameras: updatedCameras,
            config: deviceConfigPayload({
                device_id: deviceId,
                family_id: deviceFamilyId,
            }),
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
        if (!requireAssetAccess(req, res, asset)) return;
        const optimizedPath = optimizedCareCardFile(asset, filePath);
        write(res, 200, fs.readFileSync(optimizedPath || filePath), {
            "Content-Type": optimizedPath ? "image/webp" : (asset.content_type || "image/jpeg"),
            "Cache-Control": "private, max-age=300",
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
        if (!requireAssetAccess(req, res, asset)) return;
        const optimizedPath = optimizedCareCardFile(asset, filePath);
        write(res, 200, fs.readFileSync(optimizedPath || filePath), {
            "Content-Type": optimizedPath ? "image/webp" : (asset.content_type || "image/jpeg"),
            "Cache-Control": "private, max-age=300",
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
        const stat = fs.statSync(filePath);
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
            ".woff2": "font/woff2",
            ".woff": "font/woff",
            ".ttf": "font/ttf",
        };
        const etag = `W/\"${stat.size.toString(16)}-${Math.floor(stat.mtimeMs).toString(16)}\"`;
        const serviceWorkerScript = pathname === "/service-worker.js";
        const versionedAsset = [".css", ".js"].includes(ext) && url.searchParams.has("v");
        const cacheControl = serviceWorkerScript
            ? "no-cache"
            : [".html", ".json", ".webmanifest"].includes(ext)
                ? "no-cache"
                : versionedAsset || [".woff2", ".woff", ".ttf"].includes(ext)
                    ? "public, max-age=31536000, immutable"
                    : [".png", ".jpg", ".jpeg", ".svg", ".ico"].includes(ext)
                        ? "public, max-age=604800, stale-while-revalidate=86400"
                        : "public, max-age=300, stale-while-revalidate=60";
        const headers = {
            "Content-Type": types[ext] || "application/octet-stream",
            "Cache-Control": cacheControl,
            "ETag": etag,
            "Last-Modified": stat.mtime.toUTCString(),
            ...(serviceWorkerScript ? { "Service-Worker-Allowed": "/" } : {}),
        };
        if (String(req.headers["if-none-match"] || "") === etag) {
            res.writeHead(304, {
                "Access-Control-Allow-Origin": "*",
                ...headers,
            });
            res.end();
            return;
        }
        write(res, 200, fs.readFileSync(filePath), headers);
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
                const payload = {
                    ok: true,
                    service: "gohome-local-app-server",
                    store: store.kind || "json",
                    app_server_base_url: process.env.GOHOME_APP_SERVER_BASE_URL || `http://localhost:${DEFAULT_PORT}`,
                    events: store.db.events.length,
                    assets: store.db.assets.length,
                    updated_at: store.db.updated_at,
                };
                if (isLocalRequest(req) && process.env.NODE_ENV !== "production") {
                    payload.local_app_demo_token = appToken;
                }
                write(res, 200, payload);
                return;
            }

            if (req.method === "POST" && (pathname === "/api/auth/request-code" || pathname === "/api/v1/identity/request-code")) {
                const payload = await parseJsonBody(req);
                const result = await authService.requestCode(payload.phone || payload.mobile || payload.mobile_phone);
                write(res, 200, result);
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/content/image") {
                try {
                    const image = await proxyContentImage(url.searchParams.get("url"));
                    write(res, 200, image.buffer, {
                        "Content-Type": image.contentType,
                        "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
                    });
                } catch (error) {
                    writeError(res, 404, error.message || "content image unavailable");
                }
                return;
            }

            if (req.method === "POST" && (pathname === "/api/auth/login" || pathname === "/api/v1/identity/login")) {
                const payload = await parseJsonBody(req);
                const identity = authIdentityFromPayload(payload);
                const email = identity.email;
                const password = String(payload.password || payload.code || "");
                const user = store.db.users.find((item) => String(item.email || "").toLowerCase() === email);
                if (!user) {
                    writeError(res, 401, identity.isPhone ? "手机号未注册" : "账号不存在");
                    return;
                }
                const isPhoneAccount = identity.isPhone || /@phone\.gohome\.local$/i.test(email);
                if (isPhoneAccount) authService.verifyCode(identity.phone, password, payload.challenge_id || payload.challengeId);
                const phoneOtpLogin = isPhoneAccount;
                const passwordMatches = user.password ? String(user.password) === password : Boolean(password);
                if (!phoneOtpLogin && !passwordMatches) {
                    writeError(res, 401, isPhoneAccount ? "验证码不正确" : "密码不正确");
                    return;
                }
                store.db.active_user_id = user.id;
                const session = issueAppSession(user);
                await store.save();
                write(res, 200, { token: session.token, user: publicUser(user) }, {
                    "Set-Cookie": appSessionCookieHeader(session.token),
                });
                return;
            }

            if (req.method === "POST" && (pathname === "/api/auth/register" || pathname === "/api/v1/identity/register")) {
                const payload = await parseJsonBody(req);
                const identity = authIdentityFromPayload(payload, `user-${Date.now()}@gohome.local`);
                const email = identity.email;
                if (identity.isPhone) authService.verifyCode(identity.phone, payload.code || payload.password, payload.challenge_id || payload.challengeId);
                let user = store.db.users.find((item) => item.email === email);
                if (user) {
                    writeError(res, 409, identity.isPhone ? "手机号已注册，请直接登录。" : "账号已存在，请直接登录。");
                    return;
                }
                user = {
                    id: store.nextId("user"),
                    email,
                    phone: identity.phone || "",
                    display_name: String(payload.display_name || payload.name || "回家用户"),
                    password: identity.isPhone ? "" : String(payload.password || payload.code || ""),
                    created_at: nowIso(),
                    updated_at: nowIso(),
                };
                store.db.users.push(user);
                store.db.active_user_id = user.id;
                const session = issueAppSession(user);
                await store.save();
                write(res, 200, { token: session.token, user: publicUser(user) }, {
                    "Set-Cookie": appSessionCookieHeader(session.token),
                });
                return;
            }

            if (req.method === "POST" && (pathname === "/api/auth/logout" || pathname === "/api/v1/identity/logout")) {
                const token = tokenFrom(req);
                if (token) {
                    const session = sessionForToken(token);
                    if (session) {
                        session.status = "revoked";
                        session.revoked_at = nowIso();
                        session.updated_at = nowIso();
                        await store.save();
                    }
                }
                write(res, 200, { ok: true }, {
                    "Set-Cookie": clearAppSessionCookieHeader(),
                });
                return;
            }

            if (req.method === "GET" && (pathname === "/api/users/me" || pathname === "/api/v1/identity/me")) {
                if (!requireApp(req, res)) return;
                const user = activeAppUser(req);
                write(res, 200, publicUser(user));
                return;
            }

            if (req.method === "GET" && (pathname === "/api/families/mine" || pathname === "/api/v1/households/mine")) {
                if (!requireApp(req, res)) return;
                const user = activeAppUser(req);
                write(res, 200, familiesForUser(user.id).map(publicFamily));
                return;
            }

            if (req.method === "POST" && (pathname === "/api/families" || pathname === "/api/v1/households")) {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req);
                const user = activeAppUser(req);
                const name = String(payload.name || payload.household_name || "我的家庭").trim();
                const myFamilyIds = familyIdsForUser(user.id);
                let family = store.db.families.find((item) => myFamilyIds.has(Number(item.id)) && item.name === name);
                if (!family) {
                    family = {
                        id: store.nextId("family"),
                        name,
                        member_count: 1,
                        created_by_user_id: user.id,
                        created_at: nowIso(),
                        updated_at: nowIso(),
                    };
                    store.db.families.push(family);
                    store.db.family_rules[String(family.id)] = defaultRules(family.created_at);
                }
                ensureFamilyMember(family.id, user.id, "owner");
                await store.save();
                write(res, 200, publicFamily(family));
                return;
            }

            if (req.method === "POST" && (pathname === "/api/families/join" || pathname === "/api/v1/households/join")) {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req);
                const family = familyForJoinCode(payload.code || payload.join_code || payload.invite_code);
                if (!family) {
                    writeError(res, 404, "邀请码无效或已失效。");
                    return;
                }
                const user = activeAppUser(req);
                ensureFamilyMember(family.id, user.id, "member");
                await store.save();
                write(res, 200, publicFamily(family));
                return;
            }

            if (req.method === "GET" && pathname === "/api/device-bindings") {
                if (!requireApp(req, res)) return;
                if (ensureDeviceBindings()) await store.save();
                const userFamilies = familiesForUser(activeAppUser(req).id);
                const familyId = normalizeNumber(url.searchParams.get("family_id"), userFamilies[0]?.id || null);
                if (!familyId) {
                    write(res, 200, []);
                    return;
                }
                if (!familyId || !requireFamilyAccess(req, res, familyId)) return;
                const bindings = store.db.device_bindings.filter((item) => Number(item.family_id) === Number(familyId));
                write(res, 200, bindings.map(publicBinding));
                return;
            }

            const deviceBindingMatch = pathname.match(/^\/api\/device-bindings\/([^/]+)$/);
            if (deviceBindingMatch && req.method === "DELETE") {
                if (!requireApp(req, res)) return;
                const bindingId = decodeURIComponent(deviceBindingMatch[1]);
                const binding = store.db.device_bindings.find((item) => (
                    String(item.id) === bindingId
                    && String(item.status || "active") !== "revoked"
                ));
                if (!binding) {
                    writeError(res, 404, "没有找到可解除的盒子绑定。");
                    return;
                }
                if (!requireFamilyOwner(req, res, binding.family_id)) return;
                const result = unbindDeviceFromFamily({
                    familyId: binding.family_id,
                    bindingId,
                });
                if (!result) {
                    writeError(res, 404, "盒子绑定已经解除。");
                    return;
                }
                await deletePersistedRows(result.removed_camera_ids.map((id) => ({ table: "cameras", id })));
                await store.save();
                write(res, 200, {
                    ok: true,
                    binding: publicBinding(result.binding),
                    device: publicClaimableDevice(result.device),
                    removed_camera_count: result.removed_camera_count,
                    next: "device_claim",
                });
                return;
            }

            if (req.method === "GET" && pathname === "/api/device-claims/available") {
                if (!requireApp(req, res)) return;
                if (!cloudDeviceClaimsEnabled()) {
                    write(res, 200, []);
                    return;
                }
                const devices = Object.values(store.db.devices)
                    .filter((device) => {
                        const deviceId = String(device.device_id || device.id || "");
                        if (!deviceId) return false;
                        if (device.family_id || deviceHasActiveBinding(deviceId)) return false;
                        return true;
                    })
                    .sort((a, b) => String(b.last_seen_at || b.updated_at || "").localeCompare(String(a.last_seen_at || a.updated_at || "")))
                    .map(publicClaimableDevice);
                write(res, 200, devices);
                return;
            }

            if (req.method === "POST" && pathname === "/api/device-claims/claim") {
                if (!requireApp(req, res)) return;
                if (!cloudDeviceClaimsEnabled()) {
                    writeError(res, 403, "请让手机和盒子连接同一 Wi-Fi，再通过局域网搜索完成绑定。");
                    return;
                }
                const payload = await parseJsonBody(req);
                const user = activeAppUser(req);
                const userFamilies = familiesForUser(user.id);
                const familyId = normalizeNumber(payload.family_id, userFamilies[0]?.id || null);
                if (!familyId || !requireFamilyAccess(req, res, familyId)) return;
                const claimCode = payload.claim_code || payload.code || payload.serial_number || payload.serial || "";
                const requestedSerial = normalizeClaimCode(payload.serial_number || payload.serial || "");
                const requestedDeviceId = normalizeClaimCode(payload.device_id || "");
                const candidates = Object.values(store.db.devices).filter((device) => {
                    const deviceId = String(device.device_id || device.id || "");
                    if (!deviceId) return false;
                    const serial = normalizeClaimCode(deviceSerial(device));
                    if (requestedSerial && requestedSerial !== serial) return false;
                    if (requestedDeviceId && requestedDeviceId !== normalizeClaimCode(deviceId)) return false;
                    return claimCodeMatchesDevice(device, claimCode);
                });
                const boundToOtherFamily = candidates.find((device) => {
                    const deviceId = String(device.device_id || device.id || "");
                    return deviceBoundToOtherFamily(deviceId, familyId);
                });
                if (boundToOtherFamily) {
                    writeError(res, 409, "这台盒子已经绑定到其他家庭。请先在原家庭解绑，或联系服务方重置后再绑定。");
                    return;
                }
                const device = candidates[0] || null;
                if (!device) {
                    writeError(res, 404, "盒子绑定码无效，或这台盒子还没有连接到云端。");
                    return;
                }
                const deviceId = String(device.device_id || device.id);
                const binding = bindDeviceToFamily({
                    familyId,
                    deviceId,
                    deviceName: payload.device_name || device.name || "回家盒子",
                    note: payload.note || "app device claim",
                    userId: user.id,
                });
                await store.save();
                write(res, 200, {
                    ok: true,
                    binding: publicBinding(binding),
                    device: publicClaimableDevice(store.db.devices[deviceId]),
                    next: "camera_setup",
                });
                return;
            }

            if (req.method === "POST" && pathname === "/api/device-bindings") {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req);
                if (payload.claim_code || payload.code || payload.serial_number || payload.serial) {
                    if (!cloudDeviceClaimsEnabled()) {
                        writeError(res, 403, "请通过局域网搜索盒子完成绑定。");
                        return;
                    }
                    const user = activeAppUser(req);
                    const userFamilies = familiesForUser(user.id);
                    const familyId = normalizeNumber(payload.family_id, userFamilies[0]?.id || null);
                    if (!familyId || !requireFamilyAccess(req, res, familyId)) return;
                    const claimCode = payload.claim_code || payload.code || payload.serial_number || payload.serial || "";
                    const device = Object.values(store.db.devices).find((item) => claimCodeMatchesDevice(item, claimCode));
                    if (!device) {
                        writeError(res, 404, "盒子绑定码无效，或这台盒子还没有连接到云端。");
                        return;
                    }
                    if (deviceBoundToOtherFamily(device.device_id || device.id, familyId)) {
                        writeError(res, 409, "这台盒子已经绑定到其他家庭。请先在原家庭解绑，或联系服务方重置后再绑定。");
                        return;
                    }
                    const binding = bindDeviceToFamily({
                        familyId,
                        deviceId: device.device_id || device.id,
                        deviceName: payload.device_name || device.name || "回家盒子",
                        note: payload.note || "app device claim",
                        userId: user.id,
                    });
                    await store.save();
                    write(res, 200, publicBinding(binding));
                    return;
                }
                writeError(res, 400, "请通过盒身二维码、序列号或临时绑定码认领设备。");
                return;
            }

            const elderProfileMatch = pathname.match(/^\/api\/v1\/families\/([^/]+)\/elders\/([^/]+)\/profile$/);
            if (elderProfileMatch && req.method === "GET") {
                if (!requireApp(req, res)) return;
                const familyId = Number(elderProfileMatch[1]);
                const elderId = decodeURIComponent(elderProfileMatch[2]);
                if (!requireFamilyAccess(req, res, familyId)) return;
                const profile = existingElderProfile(familyId, elderId);
                if (!profile) {
                    writeError(res, 404, "老人资料尚未填写。");
                    return;
                }
                write(res, 200, profile);
                return;
            }

            if (elderProfileMatch && req.method === "PUT") {
                if (!requireApp(req, res)) return;
                const familyId = Number(elderProfileMatch[1]);
                const elderId = decodeURIComponent(elderProfileMatch[2]);
                if (!requireFamilyAccess(req, res, familyId)) return;
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
                if (!requireFamilyAccess(req, res, familyId)) return;
                const elderId = url.searchParams.get("elder_id") || "";
                write(res, 200, store.db.calendar_events.filter((item) => (
                    Number(item.family_id) === familyId && (!elderId || item.elder_id === elderId)
                )));
                return;
            }

            if (calendarMatch && req.method === "POST") {
                if (!requireApp(req, res)) return;
                const familyId = Number(calendarMatch[1]);
                if (!requireFamilyAccess(req, res, familyId)) return;
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
                const familyId = Number(weatherMatch[1]);
                if (!requireFamilyAccess(req, res, familyId)) return;
                const elderId = url.searchParams.get("elder_id") || "elder_primary";
                const profile = existingElderProfile(familyId, elderId) || {};
                const city = url.searchParams.get("city") || profile.city || "杭州";
                write(res, 200, await fetchWeatherSignal({ familyId, city }));
                return;
            }

            const contentRecommendationMatch = pathname.match(/^\/api\/v1\/families\/([^/]+)\/content-recommendations$/);
            if (contentRecommendationMatch && req.method === "GET") {
                if (!requireApp(req, res)) return;
                const familyId = Number(contentRecommendationMatch[1]);
                if (!requireFamilyAccess(req, res, familyId)) return;
                const elderId = url.searchParams.get("elder_id") || "elder_primary";
                const profile = existingElderProfile(familyId, elderId) || {};
                const preferences = carePreferences(familyId);
                const region = contentRegionText(
                    preferences,
                    url.searchParams.get("city") || profile.city || "杭州",
                    url.searchParams.get("district") || profile.district || "",
                );
                write(res, 200, await fetchContentRecommendations({
                    familyId,
                    city: region.city,
                    district: region.district,
                    preferences,
                }));
                return;
            }

            if (req.method === "GET" && (pathname === "/api/v1/devices" || pathname === "/api/v1/devices/current")) {
                if (!requireApp(req, res)) return;
                if (ensureDeviceBindings()) await store.save();
                const userFamilyIds = familyIdsForUser(activeAppUser(req).id);
                const bindings = store.db.device_bindings
                    .filter((item) => userFamilyIds.has(Number(item.family_id)))
                    .map(publicBinding);
                const primaryBinding = bindings[0] || null;
                const primaryDevice = primaryBinding ? (store.db.devices[String(primaryBinding.device_id)] || {}) : {};
                const device = {
                    device_id: primaryBinding ? String(primaryBinding.device_id) : "",
                    name: primaryBinding ? (primaryDevice.name || primaryBinding.device_name || "回家盒子") : "未绑定家庭盒子",
                    status: primaryBinding ? (primaryDevice.status || "active") : "unbound",
                    last_seen_at: primaryBinding ? (primaryDevice.last_seen_at || primaryBinding.last_seen_at || null) : null,
                    bindings,
                };
                write(res, 200, pathname.endsWith("/current") ? device : (primaryBinding ? [device] : []));
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/devices/current/sync-state") {
                if (!requireApp(req, res)) return;
                if (ensureDeviceBindings()) await store.save();
                const userFamilyIds = familyIdsForUser(activeAppUser(req).id);
                const primaryBinding = store.db.device_bindings.find((item) => userFamilyIds.has(Number(item.family_id)) && item.status !== "revoked");
                const device = primaryBinding ? (store.db.devices[String(primaryBinding.device_id)] || {}) : {};
                const familyId = normalizeNumber(primaryBinding?.family_id || [...userFamilyIds][0], null);
                write(res, 200, {
                    device_id: primaryBinding ? String(primaryBinding.device_id) : "",
                    server_time: nowIso(),
                    config_version: deviceConfigVersion(familyId),
                    cameras: appConfigCameras(userFamilyIds).map(publicCamera),
                    rules_version: rulesVersion(familyId),
                    applied_rule_version: device.applied_rule_version || "",
                    pending_commands: [],
                });
                return;
            }

            if (req.method === "GET" && (pathname === "/api/rules" || pathname === "/api/v1/rules")) {
                if (!requireApp(req, res)) return;
                const user = activeAppUser(req);
                const userFamilies = familiesForUser(user.id);
                const familyId = normalizeNumber(url.searchParams.get("family_id"), normalizeNumber(userFamilies[0]?.id, null));
                if (!familyId || !requireFamilyAccess(req, res, familyId)) return;
                write(res, 200, {
                    ...currentRules(familyId),
                    family_id: familyId,
                    can_edit: userCanManageFamily(user.id, familyId),
                });
                return;
            }

            if (req.method === "GET" && pathname === "/api/rules/runtime") {
                if (!requireApp(req, res)) return;
                const user = activeAppUser(req);
                const userFamilies = familiesForUser(user.id);
                const familyId = normalizeNumber(url.searchParams.get("family_id"), normalizeNumber(userFamilies[0]?.id, null));
                if (!familyId || !requireFamilyAccess(req, res, familyId)) return;
                const binding = store.db.device_bindings.find((item) => (
                    Number(item.family_id) === Number(familyId)
                    && String(item.status || "active") !== "revoked"
                ));
                const device = binding ? (store.db.devices[String(binding.device_id)] || {}) : {};
                write(res, 200, {
                    worker_running: Boolean(device.worker_running),
                    last_rules_loaded_at: device.last_sync_at || device.last_seen_at || "",
                    desired_rule_version: rulesVersion(familyId),
                    applied_rule_version: device.applied_rule_version || "",
                    family_id: familyId,
                    can_edit: userCanManageFamily(user.id, familyId),
                });
                return;
            }

            if (req.method === "PUT" && (pathname === "/api/rules" || pathname === "/api/v1/rules")) {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req);
                const user = activeAppUser(req);
                const userFamilies = familiesForUser(user.id);
                const familyId = normalizeNumber(
                    payload.family_id || url.searchParams.get("family_id"),
                    normalizeNumber(userFamilies[0]?.id, null),
                );
                if (!familyId || !requireFamilyOwner(req, res, familyId)) return;
                const baseRules = currentRules(familyId);
                store.db.family_rules[String(familyId)] = normalizeRules({
                    ...baseRules,
                    ...payload,
                    updated_at: nowIso(),
                }, baseRules);
                await store.save();
                write(res, 200, {
                    ...currentRules(familyId),
                    family_id: familyId,
                    can_edit: userCanManageFamily(user.id, familyId),
                });
                return;
            }

            if (req.method === "GET" && pathname === "/api/device/binding-codes") {
                if (!requireApp(req, res)) return;
                const userFamilies = familiesForUser(activeAppUser(req).id);
                const familyId = normalizeNumber(url.searchParams.get("family_id"), userFamilies[0]?.id || null);
                if (!familyId) {
                    write(res, 200, []);
                    return;
                }
                if (!requireFamilyAccess(req, res, familyId)) return;
                write(res, 200, store.db.binding_codes
                    .filter((item) => Number(item.family_id) === Number(familyId))
                    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
                    .map(publicBindingCode));
                return;
            }

            if (req.method === "POST" && pathname === "/api/device/binding-codes") {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req);
                const userFamilies = familiesForUser(activeAppUser(req).id);
                const familyId = normalizeNumber(payload.family_id, userFamilies[0]?.id || null);
                if (!familyId) {
                    writeError(res, 400, "请先创建家庭。");
                    return;
                }
                if (!requireFamilyOwner(req, res, familyId)) return;
                const code = {
                    id: store.nextId("binding_code"),
                    family_id: Number(familyId),
                    code: crypto.randomBytes(8).toString("hex"),
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
                if (deviceBoundToOtherFamily(deviceId, code.family_id)) {
                    writeError(res, 409, "这台盒子已经绑定到其他家庭，请先由原家庭创建者解绑。");
                    return;
                }
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
                const binding = bindDeviceToFamily({
                    familyId: code.family_id,
                    deviceId,
                    deviceName: payload.device_name || "回家盒子",
                    note: payload.note || "",
                });
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
                const userFamilyIds = familyIdsForUser(activeAppUser(req).id);
                const binding = store.db.device_bindings.find((item) => userFamilyIds.has(Number(item.family_id)) && item.status !== "revoked");
                const device = binding ? (store.db.devices[String(binding.device_id)] || {}) : {};
                const cameras = appConfigCameras(userFamilyIds);
                const familyId = normalizeNumber(binding?.family_id, null);
                write(res, 200, {
                    device_id: binding ? String(binding.device_id) : "",
                    name: binding ? (device.name || binding.device_name || "回家盒子") : "未连接家庭盒子",
                    worker_running: binding ? Boolean(device.worker_running) : false,
                    detector_backend: device.detector_backend || "basic",
                    yolo_model: device.yolo_model || "",
                    yolo_imgsz: device.yolo_imgsz || null,
                    vision_capabilities: deviceVisionCapabilities(device, cameras),
                    upload_agent: { configured: Boolean(binding), app_server_base_url: Boolean(binding) },
                    family_id: familyId,
                    can_manage: familyId ? userCanManageFamily(activeAppUser(req).id, familyId) : false,
                    storage: objectValue(objectValue(device.runtime).storage),
                    maintenance: objectValue(device.maintenance),
                });
                return;
            }

            if (req.method === "POST" && pathname === "/api/v1/devices/current/cleanup") {
                if (!requireApp(req, res)) return;
                const user = activeAppUser(req);
                const userFamilyIds = familyIdsForUser(user.id);
                const binding = store.db.device_bindings.find((item) => (
                    userFamilyIds.has(Number(item.family_id)) && item.status !== "revoked"
                ));
                const familyId = normalizeNumber(binding?.family_id, null);
                if (!binding || !familyId || !requireFamilyOwner(req, res, familyId)) return;
                const deviceId = String(binding.device_id || "");
                const device = store.db.devices[deviceId] || {};
                const command = {
                    command_id: stableId("cleanup-"),
                    type: "cleanup_runtime_history",
                    retention_hours: 24,
                    requested_at: nowIso(),
                    requested_by_user_id: user.id,
                };
                store.db.devices[deviceId] = {
                    ...device,
                    metadata: {
                        ...objectValue(device.metadata),
                        maintenance_command: command,
                    },
                    updated_at: nowIso(),
                };
                await store.save();
                write(res, 202, { ok: true, command });
                return;
            }

            if (req.method === "GET" && (pathname === "/api/app/cameras" || pathname === "/api/cameras")) {
                if (!requireApp(req, res)) return;
                const userFamilyIds = familyIdsForUser(activeAppUser(req).id);
                write(res, 200, appConfigCameras(userFamilyIds).map(publicCamera));
                return;
            }

            if (req.method === "POST" && pathname === "/api/cameras") {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req);
                const userFamilies = familiesForUser(activeAppUser(req).id);
                const familyId = normalizeNumber(payload.family_id, userFamilies[0]?.id || null);
                if (!familyId || !requireFamilyAccess(req, res, familyId)) return;
                const camera = normalizeCameraPayload({ ...payload, family_id: familyId });
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
                if (!existing.family_id || !requireFamilyAccess(req, res, existing.family_id)) return;
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
                if (!store.db.cameras[cameraId].family_id || !requireFamilyAccess(req, res, store.db.cameras[cameraId].family_id)) return;
                detachCameraReferences([cameraId]);
                delete store.db.cameras[cameraId];
                await deletePersistedRows([{ table: "cameras", id: cameraId }]);
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
                if (!camera.family_id || !requireFamilyAccess(req, res, camera.family_id)) return;
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
                serveLatestCameraEvaluation(req, res, latestEvaluationMatch[1], url);
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
                playbackTickets.set(ticket, { payload, user_id: activeAppUser(req).id, expires_at: Date.now() + 120000 });
                write(res, 200, { ticket, expires_at: new Date(Date.now() + 120000).toISOString() });
                return;
            }

            const streamMatch = pathname.match(/^\/api\/v1\/video\/cameras\/([^/]+)\/stream\.mjpg$/)
                || pathname.match(/^\/api\/app\/cameras\/([^/]+)\/stream\.mjpg$/);
            if (req.method === "GET" && streamMatch) {
                await serveCameraMjpeg(req, res, streamMatch[1]);
                return;
            }

            const mediaSnapshotPrefix = pathname.startsWith("/api/app/media/snapshots/")
                ? "/api/app/media/snapshots/"
                : (pathname.startsWith("/api/v1/video/media/snapshots/") ? "/api/v1/video/media/snapshots/" : "");
            if (req.method === "GET" && mediaSnapshotPrefix) {
                serveMedia(req, res, pathname.slice(mediaSnapshotPrefix.length));
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
                const issuedToken = issuedDeviceTokenFromRequest(req);
                const deviceId = String(issuedToken?.device_id || currentEdgeDeviceId());
                const device = store.db.devices[deviceId] || {};
                write(res, 200, deviceConfigPayload({
                    device_id: deviceId,
                    family_id: issuedToken?.family_id || device.family_id || null,
                }));
                return;
            }

            if (req.method === "POST" && pathname === "/api/v1/device/sync") {
                await handleDeviceSync(req, res);
                return;
            }

            if (req.method === "POST" && pathname === "/api/v1/device/live-frames/upload") {
                await handleDeviceLiveFrameUpload(req, res, url);
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

            if (req.method === "GET" && pathname === "/api/v1/device/vision-verifications") {
                deviceVisionVerificationStatus(req, res, url);
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/device/event-log") {
                deviceEventLog(req, res, url);
                return;
            }

            const deviceEventFeedbackMatch = pathname.match(/^\/api\/v1\/device\/events\/([^/]+)\/feedback$/);
            if (deviceEventFeedbackMatch && req.method === "POST") {
                await handleDeviceEventFeedback(req, res, decodeURIComponent(deviceEventFeedbackMatch[1]));
                return;
            }

            const deviceEventStateMatch = pathname.match(/^\/api\/v1\/device\/events\/([^/]+)\/state$/);
            if (deviceEventStateMatch && req.method === "POST") {
                await handleDeviceEventState(req, res, decodeURIComponent(deviceEventStateMatch[1]));
                return;
            }

            if (req.method === "GET" && (
                pathname === "/api/app/events" ||
                pathname === "/api/events" ||
                pathname === "/api/v1/events"
            )) {
                if (!requireApp(req, res)) return;
                const userFamilyIds = familyIdsForUser(activeAppUser(req).id);
                write(res, 200, eventList(url, { userVisible: true, familyIds: userFamilyIds }));
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
                const camera = store.db.cameras[String(event.camera_id)] || {};
                if (!(event.family_id || camera.family_id) || !requireFamilyAccess(req, res, event.family_id || camera.family_id)) return;
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
                const camera = store.db.cameras[String(event.camera_id)] || {};
                if (!(event.family_id || camera.family_id) || !requireFamilyAccess(req, res, event.family_id || camera.family_id)) return;
                const patch = await parseJsonBody(req);
                if ("acknowledged" in patch) event.acknowledged = normalizeBool(patch.acknowledged);
                if ("resolution" in patch) event.resolution = String(patch.resolution || "");
                const incident = ensureSafetyIncident(event);
                if (incident && event.acknowledged) {
                    acknowledgeSafetyIncident(event, event.resolution || "handled");
                }
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
                const userFamilyIds = familyIdsForUser(activeAppUser(req).id);
                const events = store.db.events
                    .filter((event) => {
                        const camera = store.db.cameras[String(event.camera_id)] || {};
                        return userFamilyIds.has(Number(event.family_id || camera.family_id || 0));
                    })
                    .filter((event) => isUserVisibleEvent(event, userFamilyIds));
                const open = events.filter((event) => !event.acknowledged).length;
                const critical = events.filter((event) => !event.acknowledged && event.level === "critical").length;
                write(res, 200, { events: events.length, open_events: open, critical_events: critical });
                return;
            }

            const carePreferenceMatch = pathname.match(/^\/api\/v1\/families\/([^/]+)\/care-preferences$/);
            if (carePreferenceMatch && req.method === "GET") {
                if (!requireApp(req, res)) return;
                if (!requireFamilyAccess(req, res, Number(carePreferenceMatch[1]))) return;
                write(res, 200, publicCarePreferences(carePreferences(carePreferenceMatch[1])));
                return;
            }

            if (carePreferenceMatch && req.method === "PUT") {
                if (!requireApp(req, res)) return;
                const familyId = Number(carePreferenceMatch[1]);
                if (!requireFamilyAccess(req, res, familyId)) return;
                const payload = await parseJsonBody(req);
                const existing = carePreferences(familyId);
                if (payload.metadata?.presence_monitoring && !userCanManageFamily(activeAppUser(req).id, familyId)) {
                    writeError(res, 403, "只有家庭创建者可以修改外出与暂停守护设置。");
                    return;
                }
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

            const presenceStateMatch = pathname.match(/^\/api\/v1\/families\/([^/]+)\/presence-state$/);
            if (presenceStateMatch && req.method === "GET") {
                if (!requireApp(req, res)) return;
                const familyId = Number(presenceStateMatch[1]);
                if (!requireFamilyAccess(req, res, familyId)) return;
                const family = selectedFamily(familyId);
                const state = familyPresenceState(family);
                const user = activeAppUser(req);
                const cameras = Object.values(store.db.cameras)
                    .filter((camera) => Number(camera.family_id) === familyId && camera.enabled !== false)
                    .map((camera) => {
                        const observation = cameraPresenceObservationState(camera);
                        return {
                            id: camera.id,
                            name: camera.name || "",
                            room: camera.room || "",
                            status: camera.status || "",
                            sync_status: camera.sync_status || "",
                            edge_reported_at: camera.edge_reported_at || null,
                            presence: camera.presence || null,
                            observation_valid: observation.valid,
                            observation_reason: observation.reason,
                            report_age_seconds: observation.report_age_seconds,
                        };
                    });
                write(res, 200, {
                    ...state,
                    can_edit: userCanManageFamily(user.id, familyId),
                    cameras,
                });
                return;
            }

            const presenceMonitoringMatch = pathname.match(/^\/api\/v1\/families\/([^/]+)\/presence-monitoring$/);
            if (presenceMonitoringMatch && req.method === "PUT") {
                if (!requireApp(req, res)) return;
                const familyId = Number(presenceMonitoringMatch[1]);
                if (!requireFamilyOwner(req, res, familyId)) return;
                const payload = await parseJsonBody(req);
                const existing = carePreferences(familyId);
                const monitoring = normalizePresenceMonitoring({
                    ...(existing.metadata?.presence_monitoring || {}),
                    ...payload,
                    updated_at: nowIso(),
                });
                if (monitoring.mode === "active") monitoring.paused_until = "";
                store.db.care_preferences[String(familyId)] = publicCarePreferences({
                    ...existing,
                    metadata: normalizeCareMetadata({
                        ...(existing.metadata || {}),
                        presence_monitoring: monitoring,
                    }),
                    updated_at: nowIso(),
                });
                const family = selectedFamily(familyId);
                const state = familyPresenceState(family);
                await store.save();
                write(res, 200, {
                    ...state,
                    can_edit: true,
                    monitoring,
                });
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/app/care-cards/today") {
                if (!requireApp(req, res)) return;
                const userFamilies = familiesForUser(activeAppUser(req).id);
                const familyId = normalizeNumber(url.searchParams.get("family_id"), userFamilies[0]?.id || null);
                if (!familyId || !requireFamilyAccess(req, res, familyId)) return;
                const cardDate = dateKeyShanghai();
                const existing = store.db.care_cards.find((card) => (
                    Number(card.family_id) === Number(familyId)
                    && card.card_date === cardDate
                    && card.card_type === "daily"
                ));
                if (existing) {
                    write(res, 200, publicCareCard(existing));
                    const preferences = carePreferences(familyId);
                    if (careImageRequested(preferences) && !existing.image_url && existing.image_mode !== "failed_provider") {
                        setImmediate(() => queueCareCardGeneration(familyId));
                    }
                    return;
                }
                write(res, 200, immediateCareCard(familyId, cardDate), { "Retry-After": "5" });
                setImmediate(() => queueCareCardGeneration(familyId));
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/app/care-cards") {
                if (!requireApp(req, res)) return;
                const userFamilies = familiesForUser(activeAppUser(req).id);
                const familyId = normalizeNumber(url.searchParams.get("family_id"), userFamilies[0]?.id || null);
                if (!familyId || !requireFamilyAccess(req, res, familyId)) return;
                const limit = Math.max(1, Math.min(60, normalizeNumber(url.searchParams.get("limit"), 20)));
                const cards = store.db.care_cards
                    .filter((card) => Number(card.family_id) === Number(familyId))
                    .sort((a, b) => String(b.card_date || b.created_at || "").localeCompare(String(a.card_date || a.created_at || "")))
                    .slice(0, limit)
                    .map(publicCareCard);
                write(res, 200, cards);
                return;
            }

            if (req.method === "POST" && pathname === "/api/v1/internal/care-cards/generate") {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req);
                const userFamilies = familiesForUser(activeAppUser(req).id);
                const familyId = normalizeNumber(payload.family_id, userFamilies[0]?.id || null);
                if (!familyId || !requireFamilyAccess(req, res, familyId)) return;
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

            if (req.method === "POST" && pathname === "/api/v1/internal/verify-data/cleanup") {
                if (!requireOps(req, res)) return;
                const payload = await parseJsonBody(req).catch(() => ({}));
                const dryRun = "dry_run" in payload
                    ? normalizeBool(payload.dry_run)
                    : normalizeBool(url.searchParams.get("dry_run"));
                const result = cleanupVerifyData({ dry_run: dryRun });
                const persistenceDeletes = result.persistence_deletes || [];
                delete result.persistence_deletes;
                if (!dryRun) {
                    await deletePersistedRows(persistenceDeletes);
                    await store.save();
                }
                write(res, 200, result);
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/internal/scheduler/status") {
                if (!requireOps(req, res)) return;
                const limit = Math.max(1, Math.min(50, normalizeNumber(url.searchParams.get("limit"), 10)));
                write(res, 200, {
                    ok: true,
                    enabled: normalizeBool(process.env.GOHOME_SCHEDULER_ENABLED),
                    latest_runs: store.db.scheduler_runs
                        .slice()
                        .sort((a, b) => String(b.started_at || b.created_at || "").localeCompare(String(a.started_at || a.created_at || "")))
                        .slice(0, limit),
                    generated_at: nowIso(),
                });
                return;
            }

            if (req.method === "POST" && pathname === "/api/v1/internal/scheduler/run") {
                if (!requireOps(req, res)) return;
                const payload = await parseJsonBody(req).catch(() => ({}));
                const result = await runNotificationScheduler({
                    family_id: payload.family_id || url.searchParams.get("family_id"),
                    force: "force" in payload ? normalizeBool(payload.force) : normalizeBool(url.searchParams.get("force")),
                    force_generate_card: "force_generate_card" in payload
                        ? normalizeBool(payload.force_generate_card)
                        : normalizeBool(url.searchParams.get("force_generate_card")),
                    job_type: payload.job_type || "manual_scheduler_run",
                });
                await store.save();
                write(res, 200, {
                    ok: true,
                    run: result.run,
                    result: result.result,
                });
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/internal/vision-verifications/status") {
                if (!requireOps(req, res)) return;
                const jobs = store.db.model_generation_jobs
                    .filter((job) => job.purpose === "vision_event_verification")
                    .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
                write(res, 200, {
                    ok: true,
                    enabled: visionVerificationEnabled(),
                    configured: Boolean(visionVerificationRuntimeConfig().base_url && visionVerificationRuntimeConfig().api_key && visionVerificationRuntimeConfig().model),
                    running: visionVerificationRunning,
                    counts: jobs.reduce((counts, job) => {
                        counts[job.output_status] = Number(counts[job.output_status] || 0) + 1;
                        return counts;
                    }, {}),
                    latest_jobs: jobs.slice(0, 20).map((job) => ({
                        id: job.id,
                        event_id: job.metadata?.event_id || "",
                        output_status: job.output_status,
                        model: job.model,
                        attempt_count: Number(job.metadata?.attempt_count || 0),
                        error_message: job.error_message || "",
                        created_at: job.created_at,
                        updated_at: job.updated_at,
                    })),
                });
                return;
            }

            if (req.method === "POST" && pathname === "/api/v1/internal/vision-verifications/run") {
                if (!requireOps(req, res)) return;
                const payload = await parseJsonBody(req).catch(() => ({}));
                const result = await processVisionVerificationJobs({
                    limit: payload.limit || url.searchParams.get("limit") || 3,
                    force: "force" in payload ? payload.force : url.searchParams.get("force"),
                });
                write(res, 200, result);
                return;
            }

            if (req.method === "POST" && pathname === "/api/v1/internal/messages/generate") {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req).catch(() => ({}));
                const userFamilies = familiesForUser(activeAppUser(req).id);
                const familyId = normalizeNumber(payload.family_id, userFamilies[0]?.id || null);
                if (!familyId || !requireFamilyAccess(req, res, familyId)) return;
                const result = await runNotificationScheduler({
                    family_id: familyId,
                    force: "force" in payload ? normalizeBool(payload.force) : true,
                    force_generate_card: normalizeBool(payload.force_generate_card),
                    job_type: "app_message_generate",
                });
                await store.save();
                write(res, 200, {
                    ok: true,
                    run: result.run,
                    result: result.result,
                });
                return;
            }

            const appMessageMatch = pathname.match(/^\/api\/v1\/app\/messages\/([^/]+)$/);
            if (appMessageMatch && req.method === "GET") {
                if (!requireApp(req, res)) return;
                const userFamilyIds = familyIdsForUser(activeAppUser(req).id);
                const messageId = decodeURIComponent(appMessageMatch[1]);
                const message = store.db.app_messages.find((item) => (
                    (String(item.message_id || item.id) === messageId || String(item.id) === messageId)
                    && userFamilyIds.has(Number(item.family_id))
                ));
                if (!message) {
                    writeError(res, 404, "message not found");
                    return;
                }
                write(res, 200, publicAppMessage(message));
                return;
            }

            if (appMessageMatch && req.method === "PATCH") {
                if (!requireApp(req, res)) return;
                const userFamilyIds = familyIdsForUser(activeAppUser(req).id);
                const messageId = decodeURIComponent(appMessageMatch[1]);
                const message = store.db.app_messages.find((item) => (
                    (String(item.message_id || item.id) === messageId || String(item.id) === messageId)
                    && userFamilyIds.has(Number(item.family_id))
                ));
                if (!message) {
                    writeError(res, 404, "message not found");
                    return;
                }
                const patch = await parseJsonBody(req).catch(() => ({}));
                if ("status" in patch) {
                    const status = String(patch.status || "open");
                    message.status = ["open", "read", "archived"].includes(status) ? status : message.status;
                    if (message.status === "read" && !message.read_at) message.read_at = nowIso();
                }
                if ("read" in patch && normalizeBool(patch.read)) {
                    message.status = "read";
                    message.read_at = message.read_at || nowIso();
                }
                message.updated_at = nowIso();
                await store.save();
                write(res, 200, publicAppMessage(message));
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/app/messages") {
                if (!requireApp(req, res)) return;
                const userFamilyIds = familyIdsForUser(activeAppUser(req).id);
                const familyId = normalizeNumber(url.searchParams.get("family_id"), null);
                if (familyId && !requireFamilyAccess(req, res, familyId)) return;
                const statusFilter = String(url.searchParams.get("status") || "open").trim();
                const limit = Math.max(1, Math.min(60, normalizeNumber(url.searchParams.get("limit"), 20)));
                const messageFamilyIds = familyId ? new Set([Number(familyId)]) : userFamilyIds;
                const persisted = store.db.app_messages
                    .filter((message) => messageFamilyIds.has(Number(message.family_id)))
                    .filter((message) => !statusFilter || statusFilter === "all" || String(message.status || "open") === statusFilter)
                    .map(publicAppMessage);
                const persistedEventIds = new Set(persisted.flatMap((message) => (
                    Array.isArray(message.source_event_ids) ? message.source_event_ids.map(String) : []
                )));
                const events = eventList(url, { userVisible: true, familyIds: messageFamilyIds })
                    .filter((event) => !event.acknowledged)
                    .filter((event) => !persistedEventIds.has(String(event.id)))
                    .slice(0, 5);
                const eventMessages = events.map((event) => ({
                    id: `event-${event.id}`,
                    message_id: `event-${event.id}`,
                    family_id: event.family_id || store.db.cameras[String(event.camera_id)]?.family_id || null,
                    message_type: event.level === "critical" ? "alert" : "explain",
                    title: event.type === "camera_offline"
                        ? `${event.camera_name || event.room || "摄像头"} 暂时没有返回画面`
                        : event.summary,
                    subtitle: `${event.room || event.camera_name || "摄像头"} · ${event.event_type}`,
                    body: event.type === "camera_offline"
                        ? "家庭盒子暂时没有拿到这路画面，会继续重试。"
                        : (event.payload?.rule?.reason || event.summary),
                    facts: [event.event_type, event.level],
                    actions: [{ key: "open_event", label: "查看事件" }],
                    source_event_ids: [event.id],
                    generated_by: "local-app-server",
                    status: "open",
                    priority: event.level === "critical" ? "high" : "normal",
                    created_at: event.created_at,
                    updated_at: event.updated_at || event.created_at,
                }));
                const messages = [...persisted, ...eventMessages]
                    .sort((a, b) => {
                        const priorityScore = (item) => item.priority === "high" ? 1 : 0;
                        const priorityDelta = priorityScore(b) - priorityScore(a);
                        if (priorityDelta) return priorityDelta;
                        return String(b.created_at || "").localeCompare(String(a.created_at || ""));
                    })
                    .slice(0, limit);
                write(res, 200, messages);
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/notifications/deliveries") {
                if (!requireApp(req, res)) return;
                const userFamilyIds = familyIdsForUser(activeAppUser(req).id);
                const familyId = normalizeNumber(url.searchParams.get("family_id"), null);
                if (familyId && !requireFamilyAccess(req, res, familyId)) return;
                const limit = Math.max(1, Math.min(100, normalizeNumber(url.searchParams.get("limit"), 50)));
                const deliveries = store.db.notification_deliveries
                    .filter((delivery) => familyId ? Number(delivery.family_id) === Number(familyId) : userFamilyIds.has(Number(delivery.family_id)))
                    .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")))
                    .slice(0, limit)
                    .map(publicNotificationDelivery);
                write(res, 200, deliveries);
                return;
            }

            if (req.method === "POST" && pathname === "/api/v1/notifications/test") {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req).catch(() => ({}));
                const user = activeAppUser(req);
                const userFamilies = familiesForUser(user.id);
                const familyId = normalizeNumber(payload.family_id, userFamilies[0]?.id || null);
                if (!familyId || !requireFamilyAccess(req, res, familyId)) return;
                const message = upsertAppMessage({
                    message_id: `notification-test-${familyId}-${Date.now()}`,
                    family_id: familyId,
                    user_id: user.id,
                    message_type: "test",
                    title: String(payload.title || "测试通知").slice(0, 80),
                    subtitle: "这是一条 App 内通知测试记录。",
                    body: String(payload.body || "通知服务已写入本地送达记录。").slice(0, 300),
                    facts: ["App 内消息", "送达记录"],
                    actions: [{ key: "open_notifications", label: "查看通知设置" }],
                    priority: "normal",
                    generated_by: "notification-test",
                });
                const deliveries = queueNotificationDelivery(message);
                await store.save();
                write(res, 200, { ok: true, message: publicAppMessage(message), deliveries: deliveries.map(publicNotificationDelivery) });
                return;
            }

            if (req.method === "GET" && pathname === "/api/v1/app/push-tokens") {
                if (!requireApp(req, res)) return;
                const user = activeAppUser(req);
                const userFamilyIds = familyIdsForUser(user.id);
                const familyId = normalizeNumber(url.searchParams.get("family_id"), null);
                if (familyId && !requireFamilyAccess(req, res, familyId)) return;
                const tokens = store.db.app_push_tokens
                    .filter((token) => Number(token.user_id) === Number(user.id) || userFamilyIds.has(Number(token.family_id)))
                    .filter((token) => familyId ? Number(token.family_id) === Number(familyId) : true)
                    .filter((token) => String(token.status || "active") !== "revoked")
                    .map(publicAppPushToken);
                write(res, 200, tokens);
                return;
            }

            if (req.method === "POST" && pathname === "/api/v1/app/push-tokens") {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req).catch(() => ({}));
                const user = activeAppUser(req);
                const userFamilies = familiesForUser(user.id);
                const familyId = normalizeNumber(payload.family_id, userFamilies[0]?.id || null);
                if (!familyId || !requireFamilyAccess(req, res, familyId)) return;
                const appInstallId = String(payload.app_install_id || payload.appInstallId || "").trim();
                const pushToken = String(payload.push_token || payload.pushToken || "").trim();
                if (!appInstallId || !pushToken) {
                    writeError(res, 400, "app_install_id and push_token required");
                    return;
                }
                const tokenHash = sha256(pushToken);
                let token = store.db.app_push_tokens.find((item) => (
                    String(item.app_install_id || "") === appInstallId
                    && Number(item.user_id) === Number(user.id)
                ));
                const timestamp = nowIso();
                const patch = {
                    family_id: familyId,
                    user_id: user.id,
                    app_install_id: appInstallId,
                    platform: String(payload.platform || "ios").toLowerCase(),
                    push_token_hash: tokenHash,
                    token_preview: tokenPreview(pushToken),
                    status: "active",
                    device_name: String(payload.device_name || payload.deviceName || "").slice(0, 80),
                    app_version: String(payload.app_version || payload.appVersion || "").slice(0, 40),
                    metadata: payload.metadata && typeof payload.metadata === "object" ? payload.metadata : {},
                    last_seen_at: timestamp,
                    updated_at: timestamp,
                };
                if (!token) {
                    token = {
                        id: store.nextId("app_push_token"),
                        ...patch,
                        created_at: timestamp,
                    };
                    store.db.app_push_tokens.push(token);
                } else {
                    Object.assign(token, patch);
                }
                await store.save();
                write(res, 200, publicAppPushToken(token));
                return;
            }

            const appPushTokenMatch = pathname.match(/^\/api\/v1\/app\/push-tokens\/([^/]+)$/);
            if (appPushTokenMatch && req.method === "DELETE") {
                if (!requireApp(req, res)) return;
                const user = activeAppUser(req);
                const appInstallId = decodeURIComponent(appPushTokenMatch[1]);
                const token = store.db.app_push_tokens.find((item) => (
                    String(item.app_install_id || "") === appInstallId
                    && Number(item.user_id) === Number(user.id)
                ));
                if (token) {
                    token.status = "revoked";
                    token.updated_at = nowIso();
                    await store.save();
                }
                write(res, 200, { ok: true });
                return;
            }

            if (req.method === "POST" && pathname === "/api/v1/app/push-test") {
                if (!requireApp(req, res)) return;
                const payload = await parseJsonBody(req).catch(() => ({}));
                const user = activeAppUser(req);
                const userFamilies = familiesForUser(user.id);
                const familyId = normalizeNumber(payload.family_id, userFamilies[0]?.id || null);
                if (!familyId || !requireFamilyAccess(req, res, familyId)) return;
                const message = upsertAppMessage({
                    message_id: `push-test-${familyId}-${Date.now()}`,
                    family_id: familyId,
                    user_id: user.id,
                    message_type: "test",
                    title: "推送链路测试",
                    subtitle: "已写入 App 内消息和送达记录。",
                    body: "当前阶段未接 APNs 时会记录为模拟送达；接入 APNs 后同一接口会进入真实推送队列。",
                    facts: ["App 内消息已生成", appPushProviderConfigured() ? "推送 provider 已配置" : "APNs 尚未配置"],
                    actions: [{ key: "open_notifications", label: "查看通知设置" }],
                    priority: "normal",
                    generated_by: "push-test",
                });
                const deliveries = queueNotificationDelivery(message);
                await store.save();
                write(res, 200, { ok: true, message: publicAppMessage(message), deliveries: deliveries.map(publicNotificationDelivery) });
                return;
            }

            serveStatic(req, res, url);
        } catch (error) {
            writeError(res, Number(error?.statusCode) || 500, error.message || "server error");
        }
    }

    const server = http.createServer(route);
    let schedulerTimer = null;
    let visionVerificationTimer = null;
    if (normalizeBool(process.env.GOHOME_SCHEDULER_ENABLED)) {
        const intervalMs = Math.max(60000, normalizeNumber(process.env.GOHOME_SCHEDULER_INTERVAL_MS, 60000));
        schedulerTimer = setInterval(() => {
            runNotificationScheduler({ job_type: "background_scheduler" })
                .then(() => store.save())
                .catch((error) => {
                    console.error(`scheduler failed: ${error.message || error}`);
                });
        }, intervalMs);
        schedulerTimer.unref?.();
        server.on("close", () => clearInterval(schedulerTimer));
    }
    if (visionVerificationEnabled()) {
        const intervalMs = Math.max(5000, normalizeNumber(process.env.GOHOME_VISION_VERIFICATION_INTERVAL_MS, 10000));
        visionVerificationTimer = setInterval(() => {
            processVisionVerificationJobs({ limit: 3 })
                .catch((error) => console.error(`vision verification failed: ${error.message || error}`));
        }, intervalMs);
        visionVerificationTimer.unref?.();
        const initialTimer = setTimeout(() => {
            processVisionVerificationJobs({ limit: 3 })
                .catch((error) => console.error(`vision verification failed: ${error.message || error}`));
        }, 1000);
        initialTimer.unref?.();
        server.on("close", () => {
            clearInterval(visionVerificationTimer);
            clearTimeout(initialTimer);
        });
    }
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

function initialDbFromJsonFallback(filePath, { seedDefaultData = true } = {}) {
    if (fs.existsSync(filePath)) {
        return normalizeDb({ ...createDefaultDb(), ...safeJsonParse(fs.readFileSync(filePath, "utf8"), {}) });
    }
    return normalizeDb(seedDefaultData ? createDefaultDb() : createEmptyDb());
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
    const seedDefaultData = !["0", "false", "no"].includes(
        String(process.env.GOHOME_SEED_DEFAULT_DATA || "1").trim().toLowerCase(),
    );
    const { createPostgresStore } = require("./postgres-store");
    const store = await createPostgresStore({
        databaseUrl,
        ssl,
        initialDb: initialDbFromJsonFallback(localJsonDbPath(rootDir, dataDir), { seedDefaultData }),
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
                console.log(`App token: ${redactedSecret(app.appToken)}`);
                console.log(`Device token: ${redactedSecret(app.deviceToken)}`);
                console.log(`Data dir: ${app.dataDir}`);
            });
        })
        .catch((error) => {
            console.error(error.message || error);
            process.exit(1);
        });
}

module.exports = { createLocalAppServer, createLocalAppServerAsync, createDefaultDb, normalizeDb };
