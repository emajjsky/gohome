#!/usr/bin/env node
"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

function readJson(filePath) {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function ensureDir(dir) {
    fs.mkdirSync(dir, { recursive: true });
}

function toArray(value) {
    return Array.isArray(value) ? value : [];
}

function toObjectValues(value) {
    return value && typeof value === "object" ? Object.values(value) : [];
}

function textId(value, fallback = "") {
    if (value === null || value === undefined || value === "") return String(fallback || "");
    return String(value);
}

function nullableTextId(value) {
    const id = textId(value);
    return id || null;
}

function iso(value, fallback = null) {
    if (!value) return fallback;
    const time = Date.parse(value);
    return Number.isFinite(time) ? new Date(time).toISOString() : fallback;
}

function dateText(value, fallback = null) {
    if (!value) return fallback;
    if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
    const parsed = iso(value);
    return parsed ? parsed.slice(0, 10) : fallback;
}

function numberOrNull(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
}

function bool(value, fallback = false) {
    if (typeof value === "boolean") return value;
    if (value === "false" || value === "0" || value === 0) return false;
    if (value === "true" || value === "1" || value === 1) return true;
    return fallback;
}

function sha256(value) {
    if (!value) return "";
    return crypto.createHash("sha256").update(String(value)).digest("hex");
}

function phoneFromAccountEmail(email) {
    const match = String(email || "").trim().toLowerCase().match(/^(\d{11})@phone\.gohome\.local$/);
    return match ? match[1] : "";
}

function defaultFamilyId(db) {
    return textId(toArray(db.families)[0]?.id, "1");
}

function defaultDeviceId(db) {
    return textId(toObjectValues(db.devices)[0]?.device_id || toObjectValues(db.devices)[0]?.id || toArray(db.device_tokens)[0]?.device_id, "");
}

function cameraFamilyId(db, camera) {
    return textId(camera.family_id, defaultFamilyId(db));
}

function cameraDeviceId(db, camera) {
    return nullableTextId(camera.device_id || defaultDeviceId(db));
}

function buildCloudSeedBundle(db, options = {}) {
    const exportedAt = options.exportedAt || new Date().toISOString();
    const fallbackFamilyId = defaultFamilyId(db);
    const fallbackDeviceId = defaultDeviceId(db);

    const users = toArray(db.users).map((user) => ({
        id: textId(user.id),
        email: String(user.email || ""),
        display_name: String(user.display_name || ""),
        phone: String(user.phone || phoneFromAccountEmail(user.email)),
        password_hash: user.password_hash || null,
        status: String(user.status || "active"),
        metadata: {
            legacy_password_present: Boolean(user.password),
        },
        created_at: iso(user.created_at, exportedAt),
        updated_at: iso(user.updated_at, iso(user.created_at, exportedAt)),
    }));

    const families = toArray(db.families).map((family) => ({
        id: textId(family.id),
        name: String(family.name || "默认家庭"),
        status: String(family.status || "active"),
        timezone: String(family.timezone || "Asia/Shanghai"),
        metadata: {
            member_count: numberOrNull(family.member_count),
        },
        created_at: iso(family.created_at, exportedAt),
        updated_at: iso(family.updated_at, iso(family.created_at, exportedAt)),
    }));

    const rawFamilyMembers = toArray(db.family_members);
    const firstUserId = textId(toArray(db.users)[0]?.id, "");
    const familyMembers = rawFamilyMembers.length
        ? rawFamilyMembers.map((member) => ({
            id: textId(member.id || `${member.family_id}:member:${member.user_id}`),
            family_id: textId(member.family_id),
            user_id: textId(member.user_id),
            role: String(member.role || "member"),
            status: String(member.status || "active"),
            invited_by: nullableTextId(member.invited_by),
            joined_at: iso(member.joined_at, iso(member.created_at, exportedAt)),
            created_at: iso(member.created_at, exportedAt),
            updated_at: iso(member.updated_at, iso(member.created_at, exportedAt)),
        })).filter((member) => member.family_id && member.user_id)
        : (firstUserId
            ? families.map((family) => ({
                id: `${family.id}:owner:${firstUserId}`,
                family_id: family.id,
                user_id: firstUserId,
                role: "owner",
                status: "active",
                invited_by: null,
                joined_at: family.created_at,
                created_at: family.created_at,
                updated_at: family.updated_at,
            }))
            : []);

    const elderProfileEntries = new Map(Object.entries(db.elder_profiles || {}));
    for (const family of families) {
        const key = `${family.id}:elder_primary`;
        if (!elderProfileEntries.has(key)) {
            elderProfileEntries.set(key, {
                id: "elder_primary",
                elder_id: "elder_primary",
                family_id: family.id,
                display_name: "张阿姨",
                relationship: "母亲",
                city: "杭州",
                created_at: family.created_at,
                updated_at: family.updated_at,
            });
        }
    }

    const elderProfiles = Array.from(elderProfileEntries.entries()).map(([key, profile]) => {
        const familyId = textId(profile.family_id, key.split(":")[0] || fallbackFamilyId);
        const elderId = String(profile.elder_id || key.split(":")[1] || "elder_primary");
        return {
            id: `${familyId}:${elderId}`,
            family_id: familyId,
            elder_id: elderId,
            display_name: String(profile.display_name || ""),
            relationship: String(profile.relationship || ""),
            age: numberOrNull(profile.age),
            city: String(profile.city || ""),
            phone: String(profile.phone || ""),
            mobile_phone: String(profile.mobile_phone || ""),
            home_phone: String(profile.home_phone || ""),
            health_notes: String(profile.health_notes || ""),
            care_preferences: profile.care_preferences || {},
            metadata: profile.metadata && typeof profile.metadata === "object" ? profile.metadata : {},
            created_at: iso(profile.created_at, exportedAt),
            updated_at: iso(profile.updated_at, iso(profile.created_at, exportedAt)),
        };
    });

    const devices = toObjectValues(db.devices).map((device) => ({
        device_id: textId(device.device_id || device.id),
        family_id: nullableTextId(device.family_id),
        name: String(device.name || "回家盒子"),
        device_type: String(device.device_type || "edge-agent"),
        status: String(device.status || "active"),
        worker_running: "worker_running" in device ? bool(device.worker_running) : null,
        detector_backend: String(device.detector_backend || ""),
        yolo_model: String(device.yolo_model || ""),
        yolo_imgsz: numberOrNull(device.yolo_imgsz),
        lan_url: String(device.lan_url || ""),
        service_url: String(device.service_url || ""),
        reported_config_version: String(device.reported_config_version || ""),
        app_version: String(device.app_version || ""),
        model_version: String(device.model_version || ""),
        sync_status: String(device.sync_status || ""),
        last_error: String(device.last_error || ""),
        runtime: device.runtime || {},
        metadata: device.metadata && typeof device.metadata === "object" ? device.metadata : {},
        last_seen_at: iso(device.last_seen_at),
        last_sync_at: iso(device.last_sync_at),
        created_at: iso(device.created_at, exportedAt),
        updated_at: iso(device.updated_at, iso(device.created_at, exportedAt)),
    }));

    const deviceBindings = toArray(db.device_bindings).map((binding) => ({
        id: textId(binding.id),
        family_id: textId(binding.family_id, fallbackFamilyId),
        device_id: textId(binding.device_id, fallbackDeviceId),
        device_name: String(binding.device_name || "回家盒子"),
        device_type: String(binding.device_type || "edge-agent"),
        status: String(binding.status || "active"),
        note: String(binding.note || ""),
        bound_at: iso(binding.bound_at, exportedAt),
        last_seen_at: iso(binding.last_seen_at),
        created_at: iso(binding.created_at, iso(binding.bound_at, exportedAt)),
        updated_at: iso(binding.updated_at, iso(binding.bound_at, exportedAt)),
    }));

    const bindingCodes = toArray(db.binding_codes).map((code) => ({
        id: textId(code.id),
        family_id: textId(code.family_id, fallbackFamilyId),
        code: String(code.code || ""),
        status: String(code.status || "active"),
        note: String(code.note || ""),
        expires_at: iso(code.expires_at, exportedAt),
        used_at: iso(code.used_at),
        device_id: nullableTextId(code.device_id),
        created_at: iso(code.created_at, exportedAt),
        updated_at: iso(code.updated_at, iso(code.created_at, exportedAt)),
    }));

    const deviceTokens = toArray(db.device_tokens).map((token) => ({
        id: textId(token.id),
        family_id: textId(token.family_id, fallbackFamilyId),
        device_id: textId(token.device_id, fallbackDeviceId),
        token_hash: token.token_hash || sha256(token.token),
        status: String(token.status || "active"),
        note: String(token.note || ""),
        last_heartbeat_at: iso(token.last_heartbeat_at),
        created_at: iso(token.created_at, exportedAt),
        updated_at: iso(token.updated_at, iso(token.created_at, exportedAt)),
    }));

    const cameras = toObjectValues(db.cameras).map((camera) => ({
        id: textId(camera.id),
        family_id: cameraFamilyId(db, camera),
        device_id: cameraDeviceId(db, camera),
        name: String(camera.name || ""),
        room: String(camera.room || ""),
        enabled: bool(camera.enabled, true),
        status: String(camera.status || "pending_edge_sync"),
        sync_status: String(camera.sync_status || "pending_edge_sync"),
        source: String(camera.source || "app_server_config"),
        has_stream_config: Boolean(camera.stream_url),
        local_camera_id: nullableTextId(camera.local_camera_id),
        edge_camera_id: nullableTextId(camera.edge_camera_id || camera.local_id),
        last_error: String(camera.last_error || ""),
        last_seen_at: iso(camera.last_seen_at),
        edge_reported_at: iso(camera.edge_reported_at),
        metadata: {},
        created_at: iso(camera.created_at, exportedAt),
        updated_at: iso(camera.updated_at, iso(camera.created_at, exportedAt)),
    }));
    const validCameraIds = new Set(cameras.map((camera) => textId(camera.id)).filter(Boolean));
    const cameraReference = (value) => {
        const id = textId(value);
        return id && validCameraIds.has(id) ? id : null;
    };

    const cameraSecrets = toObjectValues(db.cameras)
        .filter((camera) => camera.stream_url || camera.username || camera.password)
        .map((camera) => ({
            camera_id: textId(camera.id),
            stream_url: String(camera.stream_url || ""),
            username: String(camera.username || ""),
            password_secret: String(camera.password || ""),
            secret_ref: "",
            created_at: iso(camera.created_at, exportedAt),
            updated_at: iso(camera.updated_at, iso(camera.created_at, exportedAt)),
        }));

    const carePreferences = Object.entries(db.care_preferences || {}).map(([key, preferences]) => ({
        family_id: textId(preferences.family_id, key || fallbackFamilyId),
        elder_id: String(preferences.elder_id || "elder_primary"),
        frequency: String(preferences.frequency || "daily"),
        quiet_hours: preferences.quiet_hours && typeof preferences.quiet_hours === "object" ? preferences.quiet_hours : {},
        interests: Array.isArray(preferences.interests) ? preferences.interests.map(String).filter(Boolean) : [],
        text_model_enabled: bool(preferences.text_model_enabled),
        image_generation_enabled: bool(preferences.image_generation_enabled),
        image_provider: String(preferences.image_provider || ""),
        image_model: String(preferences.image_model || ""),
        content_recommendations_enabled: bool(preferences.content_recommendations_enabled),
        content_sources_enabled: bool(preferences.content_sources_enabled),
        metadata: preferences.metadata && typeof preferences.metadata === "object" ? preferences.metadata : {},
        created_at: iso(preferences.created_at, iso(preferences.updated_at, exportedAt)),
        updated_at: iso(preferences.updated_at, exportedAt),
    }));

    const modelProviders = toArray(db.model_providers).map((provider) => ({
        provider_id: textId(provider.provider_id || provider.id),
        provider: String(provider.provider || ""),
        model: String(provider.model || ""),
        purpose: String(provider.purpose || "care_text"),
        enabled: bool(provider.enabled),
        configured: bool(provider.configured || provider.api_key_set),
        api_key_secret_ref: String(provider.api_key_secret_ref || provider.secret_ref || ""),
        metadata: {},
        created_at: iso(provider.created_at, iso(provider.updated_at, exportedAt)),
        updated_at: iso(provider.updated_at, exportedAt),
    }));

    const contentSources = toArray(db.content_sources).map((source) => ({
        id: textId(source.id),
        family_id: nullableTextId(source.family_id || fallbackFamilyId),
        source_type: String(source.source_type || source.content_type || "link"),
        title: String(source.title || source.name || ""),
        source_name: String(source.source_name || source.name || ""),
        url: String(source.url || ""),
        provider: String(source.provider || ""),
        enabled: bool(source.enabled, true),
        whitelist_status: String(source.whitelist_status || source.status || "manual"),
        metadata: source.metadata && typeof source.metadata === "object" ? source.metadata : {},
        created_at: iso(source.created_at, exportedAt),
        updated_at: iso(source.updated_at, iso(source.created_at, exportedAt)),
    }));

    const mediaAssets = toArray(db.assets).map((asset) => ({
        id: textId(asset.id),
        family_id: nullableTextId(asset.family_id || fallbackFamilyId),
        device_id: nullableTextId(asset.device_id || fallbackDeviceId),
        camera_id: cameraReference(asset.camera_id),
        file_name: String(asset.file_name || ""),
        content_type: String(asset.content_type || "image/jpeg"),
        snapshot_path: String(asset.snapshot_path || ""),
        relative_path: String(asset.relative_path || ""),
        storage_provider: String(asset.storage_provider || "local"),
        storage_key: String(asset.storage_key || asset.relative_path || ""),
        edge_event_id: String(asset.edge_event_id || ""),
        size_bytes: numberOrNull(asset.size || asset.size_bytes) || 0,
        metadata: {
            url: asset.url || "",
        },
        created_at: iso(asset.created_at, exportedAt),
        updated_at: iso(asset.updated_at, iso(asset.created_at, exportedAt)),
    }));

    const events = toArray(db.events).map((event) => ({
        id: textId(event.id),
        family_id: nullableTextId(event.family_id || fallbackFamilyId),
        device_id: nullableTextId(event.device_id || event.payload?.edge_upload?.edge_device_id || fallbackDeviceId),
        camera_id: cameraReference(event.camera_id),
        media_asset_id: nullableTextId(event.media_asset_id),
        idempotency_key: String(event.idempotency_key || `event:${event.id}`),
        edge_event_id: nullableTextId(event.edge_event_id || event.payload?.edge_upload?.edge_event_id),
        event_type: String(event.event_type || "event"),
        level: String(event.level || "warning"),
        summary: String(event.summary || ""),
        room: String(event.room || ""),
        camera_name: String(event.camera_name || ""),
        snapshot_path: String(event.snapshot_path || ""),
        acknowledged: bool(event.acknowledged),
        resolution: String(event.resolution || ""),
        payload: event.payload || {},
        occurred_at: iso(event.occurred_at, exportedAt),
        created_at: iso(event.created_at, iso(event.occurred_at, exportedAt)),
        updated_at: iso(event.updated_at, iso(event.created_at, exportedAt)),
    }));

    const deviceHeartbeats = toArray(db.heartbeats).map((heartbeat) => ({
        id: textId(heartbeat.id),
        device_id: textId(heartbeat.device_id, fallbackDeviceId),
        payload: heartbeat.payload || {},
        created_at: iso(heartbeat.created_at, exportedAt),
    }));

    const calendarEvents = toArray(db.calendar_events).map((event) => ({
        id: textId(event.id),
        family_id: textId(event.family_id, fallbackFamilyId),
        elder_id: String(event.elder_id || "elder_primary"),
        title: String(event.title || ""),
        starts_at: iso(event.starts_at, exportedAt),
        note: String(event.note || ""),
        created_at: iso(event.created_at, exportedAt),
        updated_at: iso(event.updated_at, iso(event.created_at, exportedAt)),
    }));

    const careCards = toArray(db.care_cards).map((card) => ({
        id: textId(card.id),
        card_id: String(card.card_id || `care:${card.family_id || fallbackFamilyId}:${card.card_date || exportedAt.slice(0, 10)}:${card.id || ""}`),
        family_id: textId(card.family_id, fallbackFamilyId),
        elder_id: String(card.elder_id || "elder_primary"),
        card_date: dateText(card.card_date, exportedAt.slice(0, 10)),
        card_type: String(card.card_type || "daily"),
        title: String(card.title || ""),
        body: String(card.body || ""),
        facts: Array.isArray(card.facts) ? card.facts : [],
        source_message_ids: Array.isArray(card.source_message_ids) ? card.source_message_ids.map(String) : [],
        image_mode: String(card.image_mode || "none"),
        image_url: String(card.image_url || ""),
        actions: Array.isArray(card.actions) ? card.actions : [],
        status: String(card.status || "open"),
        generated_by: String(card.generated_by || ""),
        source_summary: Array.isArray(card.source_summary) ? card.source_summary : [],
        content_recommendations: Array.isArray(card.content_recommendations) ? card.content_recommendations : [],
        metadata: {},
        created_at: iso(card.created_at, exportedAt),
        updated_at: iso(card.updated_at, iso(card.created_at, exportedAt)),
    }));

    const modelGenerationJobs = toArray(db.model_generation_jobs).map((job) => ({
        id: textId(job.id),
        family_id: nullableTextId(job.family_id || fallbackFamilyId),
        provider_id: nullableTextId(job.provider_id),
        purpose: String(job.purpose || "care_text"),
        model: String(job.model || ""),
        prompt_version: String(job.prompt_version || ""),
        input_hash: String(job.input_hash || ""),
        output_status: String(job.output_status || job.status || "pending"),
        request_payload: job.request_payload && typeof job.request_payload === "object" ? job.request_payload : {},
        response_payload: job.response_payload && typeof job.response_payload === "object" ? job.response_payload : {},
        error_message: String(job.error_message || job.error || ""),
        metadata: job.metadata && typeof job.metadata === "object" ? job.metadata : {},
        created_at: iso(job.created_at, exportedAt),
        updated_at: iso(job.updated_at, iso(job.created_at, exportedAt)),
    }));

    const contentRecommendations = toArray(db.content_recommendations).map((recommendation) => ({
        id: textId(recommendation.id),
        family_id: nullableTextId(recommendation.family_id || fallbackFamilyId),
        elder_id: String(recommendation.elder_id || "elder_primary"),
        source_id: nullableTextId(recommendation.source_id),
        content_type: String(recommendation.content_type || "article"),
        title: String(recommendation.title || ""),
        source_name: String(recommendation.source_name || ""),
        url: String(recommendation.url || ""),
        summary: String(recommendation.summary || ""),
        reason: String(recommendation.reason || recommendation.recommendation_reason || ""),
        status: String(recommendation.status || "candidate"),
        metadata: recommendation.metadata && typeof recommendation.metadata === "object" ? recommendation.metadata : {},
        created_at: iso(recommendation.created_at, exportedAt),
        updated_at: iso(recommendation.updated_at, iso(recommendation.created_at, exportedAt)),
    }));

    const tables = {
        users,
        families,
        family_members: familyMembers,
        elder_profiles: elderProfiles,
        devices,
        device_bindings: deviceBindings,
        binding_codes: bindingCodes,
        device_tokens: deviceTokens,
        cameras,
        camera_secrets: cameraSecrets,
        care_rules: [],
        care_preferences: carePreferences,
        model_providers: modelProviders,
        content_sources: contentSources,
        media_assets: mediaAssets,
        events,
        device_heartbeats: deviceHeartbeats,
        calendar_events: calendarEvents,
        care_cards: careCards,
        model_generation_jobs: modelGenerationJobs,
        content_recommendations: contentRecommendations,
        device_config_versions: [],
        audit_logs: [],
    };

    const counts = Object.fromEntries(Object.entries(tables).map(([name, rows]) => [name, rows.length]));

    return {
        schema_version: "001_initial_schema",
        exported_at: exportedAt,
        source: options.source || "local-app-server-json",
        counts,
        tables,
    };
}

function parseArgs(argv) {
    const args = {
        input: path.resolve("data/app-server/db.json"),
        output: path.resolve("data/app-server/cloud-seed.json"),
        stdout: false,
    };
    for (let index = 0; index < argv.length; index += 1) {
        const arg = argv[index];
        if (arg === "--input") args.input = path.resolve(argv[++index]);
        else if (arg === "--out" || arg === "--output") args.output = path.resolve(argv[++index]);
        else if (arg === "--stdout") args.stdout = true;
        else if (arg === "--help" || arg === "-h") {
            args.help = true;
        } else {
            throw new Error(`unknown argument: ${arg}`);
        }
    }
    return args;
}

function printHelp() {
    console.log([
        "Usage: node scripts/export-local-app-db.js [--input data/app-server/db.json] [--out data/app-server/cloud-seed.json]",
        "",
        "Exports the local App API JSON database into the table-shaped seed bundle",
        "used by local-app-server/migrations/001_initial_schema.sql.",
    ].join("\n"));
}

function main() {
    const args = parseArgs(process.argv.slice(2));
    if (args.help) {
        printHelp();
        return;
    }
    const db = readJson(args.input);
    const bundle = buildCloudSeedBundle(db, { source: args.input });
    const output = `${JSON.stringify(bundle, null, 2)}\n`;
    if (args.stdout) {
        process.stdout.write(output);
    } else {
        ensureDir(path.dirname(args.output));
        fs.writeFileSync(args.output, output);
        console.log(JSON.stringify({
            ok: true,
            input: args.input,
            output: args.output,
            schema_version: bundle.schema_version,
            counts: bundle.counts,
        }, null, 2));
    }
}

if (require.main === module) {
    try {
        main();
    } catch (error) {
        console.error(error.message || error);
        process.exit(1);
    }
}

module.exports = {
    buildCloudSeedBundle,
    sha256,
};
