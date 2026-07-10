"use strict";

const { buildCloudSeedBundle } = require("../scripts/export-local-app-db");

const TABLE_ORDER = [
    "users",
    "app_sessions",
    "families",
    "family_members",
    "elder_profiles",
    "devices",
    "device_bindings",
    "binding_codes",
    "device_tokens",
    "cameras",
    "camera_secrets",
    "care_rules",
    "care_preferences",
    "model_providers",
    "content_sources",
    "media_assets",
    "events",
    "device_heartbeats",
    "calendar_events",
    "care_cards",
    "app_messages",
    "app_push_tokens",
    "notification_deliveries",
    "scheduler_runs",
    "model_generation_jobs",
    "content_recommendations",
    "device_config_versions",
    "audit_logs",
];

const DELETE_ORDER = [...TABLE_ORDER].reverse();

function textId(value, fallback = "") {
    if (value === null || value === undefined || value === "") return String(fallback || "");
    return String(value);
}

function iso(value, fallback = null) {
    if (!value) return fallback;
    const time = Date.parse(value);
    return Number.isFinite(time) ? new Date(time).toISOString() : fallback;
}

function dateText(value, fallback = "") {
    if (!value) return fallback;
    if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
    const parsed = iso(value);
    return parsed ? parsed.slice(0, 10) : fallback;
}

function metadataValue(row, key, fallback = null) {
    const metadata = row?.metadata && typeof row.metadata === "object" ? row.metadata : {};
    return metadata[key] ?? fallback;
}

function createDbFromCloudRows(rowsByTable, fallbackDb) {
    const db = {
        ...fallbackDb,
        users: [],
        families: [],
        family_members: [],
        app_sessions: [],
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
        app_messages: [],
        notification_deliveries: [],
        app_push_tokens: [],
        scheduler_runs: [],
        model_providers: [],
        model_generation_jobs: [],
        content_sources: [],
        content_recommendations: [],
    };

    for (const user of rowsByTable.users || []) {
        db.users.push({
            id: user.id,
            email: user.email,
            display_name: user.display_name || "",
            phone: user.phone || "",
            password: "",
            created_at: iso(user.created_at, db.created_at),
            updated_at: iso(user.updated_at, iso(user.created_at, db.created_at)),
        });
    }

    for (const session of rowsByTable.app_sessions || []) {
        db.app_sessions.push({
            id: session.id,
            user_id: session.user_id,
            token: "",
            token_hash: session.token_hash || "",
            status: session.status || "active",
            created_at: iso(session.created_at, db.created_at),
            updated_at: iso(session.updated_at, iso(session.created_at, db.created_at)),
            last_seen_at: iso(session.last_seen_at),
            expires_at: iso(session.expires_at),
            revoked_at: iso(session.revoked_at),
        });
    }

    for (const family of rowsByTable.families || []) {
        db.families.push({
            id: family.id,
            name: family.name || "默认家庭",
            member_count: Number(metadataValue(family, "member_count", 1)) || 1,
            created_by_user_id: metadataValue(family, "created_by_user_id", null),
            created_at: iso(family.created_at, db.created_at),
            updated_at: iso(family.updated_at, iso(family.created_at, db.created_at)),
        });
    }

    for (const member of rowsByTable.family_members || []) {
        db.family_members.push({
            id: member.id,
            family_id: member.family_id,
            user_id: member.user_id,
            role: member.role || "member",
            status: member.status || "active",
            invited_by: member.invited_by || null,
            joined_at: iso(member.joined_at, iso(member.created_at, db.created_at)),
            created_at: iso(member.created_at, db.created_at),
            updated_at: iso(member.updated_at, iso(member.created_at, db.created_at)),
        });
    }

    for (const profile of rowsByTable.elder_profiles || []) {
        const familyId = textId(profile.family_id);
        const elderId = String(profile.elder_id || profile.id || "elder_primary");
        db.elder_profiles[`${familyId}:${elderId}`] = {
            id: elderId,
            elder_id: elderId,
            family_id: familyId,
            display_name: profile.display_name || "",
            relationship: profile.relationship || "",
            age: profile.age ?? null,
            city: profile.city || "",
            phone: profile.phone || "",
            mobile_phone: profile.mobile_phone || "",
            home_phone: profile.home_phone || "",
            health_notes: profile.health_notes || "",
            care_preferences: profile.care_preferences || {},
            created_at: iso(profile.created_at, db.created_at),
            updated_at: iso(profile.updated_at, iso(profile.created_at, db.created_at)),
        };
    }

    for (const preferences of rowsByTable.care_preferences || []) {
        const familyId = textId(preferences.family_id);
        if (!familyId) continue;
        db.care_preferences[familyId] = {
            family_id: preferences.family_id,
            elder_id: preferences.elder_id || "elder_primary",
            frequency: preferences.frequency || "daily",
            quiet_hours: preferences.quiet_hours || {},
            interests: Array.isArray(preferences.interests) ? preferences.interests : [],
            text_model_enabled: preferences.text_model_enabled === true,
            image_generation_enabled: preferences.image_generation_enabled === true,
            image_provider: preferences.image_provider || "",
            image_model: preferences.image_model || "",
            content_recommendations_enabled: preferences.content_recommendations_enabled === true,
            content_sources_enabled: preferences.content_sources_enabled === true,
            metadata: preferences.metadata || {},
            created_at: iso(preferences.created_at, db.created_at),
            updated_at: iso(preferences.updated_at, iso(preferences.created_at, db.created_at)),
        };
    }

    for (const provider of rowsByTable.model_providers || []) {
        db.model_providers.push({
            provider_id: provider.provider_id,
            provider: provider.provider || "",
            model: provider.model || "",
            purpose: provider.purpose || "care_text",
            enabled: provider.enabled === true,
            configured: provider.configured === true,
            api_key_secret_ref: provider.api_key_secret_ref || "",
            api_key_set: provider.configured === true || Boolean(provider.api_key_secret_ref),
            created_at: iso(provider.created_at, db.created_at),
            updated_at: iso(provider.updated_at, iso(provider.created_at, db.created_at)),
        });
    }

    for (const device of rowsByTable.devices || []) {
        const deviceId = textId(device.device_id);
        if (!deviceId) continue;
        db.devices[deviceId] = {
            id: deviceId,
            device_id: deviceId,
            family_id: device.family_id || null,
            name: device.name || "回家盒子",
            device_type: device.device_type || "edge-agent",
            status: device.status || "active",
            worker_running: device.worker_running,
            detector_backend: device.detector_backend || "",
            yolo_model: device.yolo_model || "",
            yolo_imgsz: device.yolo_imgsz ?? null,
            lan_url: device.lan_url || "",
            service_url: device.service_url || "",
            reported_config_version: device.reported_config_version || "",
            app_version: device.app_version || "",
            model_version: device.model_version || "",
            sync_status: device.sync_status || "",
            last_error: device.last_error || "",
            runtime: device.runtime || {},
            metadata: device.metadata || {},
            last_seen_at: iso(device.last_seen_at),
            last_sync_at: iso(device.last_sync_at),
            created_at: iso(device.created_at, db.created_at),
            updated_at: iso(device.updated_at, iso(device.created_at, db.created_at)),
        };
    }

    for (const binding of rowsByTable.device_bindings || []) {
        db.device_bindings.push({
            id: binding.id,
            family_id: binding.family_id,
            device_id: binding.device_id,
            device_name: binding.device_name || "回家盒子",
            device_type: binding.device_type || "edge-agent",
            status: binding.status || "active",
            note: binding.note || "",
            bound_at: iso(binding.bound_at, db.created_at),
            last_seen_at: iso(binding.last_seen_at),
            created_at: iso(binding.created_at, iso(binding.bound_at, db.created_at)),
            updated_at: iso(binding.updated_at, iso(binding.bound_at, db.created_at)),
        });
    }

    for (const code of rowsByTable.binding_codes || []) {
        db.binding_codes.push({
            id: code.id,
            family_id: code.family_id,
            code: code.code,
            status: code.status || "active",
            note: code.note || "",
            expires_at: iso(code.expires_at, db.created_at),
            used_at: iso(code.used_at),
            device_id: code.device_id || "",
            created_at: iso(code.created_at, db.created_at),
            updated_at: iso(code.updated_at, iso(code.created_at, db.created_at)),
        });
    }

    for (const token of rowsByTable.device_tokens || []) {
        db.device_tokens.push({
            id: token.id,
            family_id: token.family_id,
            device_id: token.device_id,
            token: "",
            token_hash: token.token_hash || "",
            status: token.status || "active",
            note: token.note || "",
            created_at: iso(token.created_at, db.created_at),
            updated_at: iso(token.updated_at, iso(token.created_at, db.created_at)),
            last_heartbeat_at: iso(token.last_heartbeat_at),
        });
    }

    const secretsByCamera = new Map((rowsByTable.camera_secrets || []).map((secret) => [String(secret.camera_id), secret]));
    for (const camera of rowsByTable.cameras || []) {
        const cameraId = textId(camera.id);
        if (!cameraId) continue;
        const secret = secretsByCamera.get(cameraId) || {};
        db.cameras[cameraId] = {
            id: camera.id,
            family_id: camera.family_id,
            device_id: camera.device_id || "",
            name: camera.name || "",
            room: camera.room || "",
            stream_url: secret.stream_url || "",
            username: secret.username || "",
            password: secret.password_secret || "",
            enabled: camera.enabled !== false,
            status: camera.status || "pending_edge_sync",
            sync_status: camera.sync_status || "pending_edge_sync",
            source: camera.source || "app_server_config",
            local_camera_id: camera.local_camera_id || null,
            edge_camera_id: camera.edge_camera_id || null,
            last_error: camera.last_error || "",
            last_seen_at: iso(camera.last_seen_at),
            edge_reported_at: iso(camera.edge_reported_at),
            created_at: iso(camera.created_at, db.created_at),
            updated_at: iso(camera.updated_at, iso(camera.created_at, db.created_at)),
        };
    }

    for (const asset of rowsByTable.media_assets || []) {
        db.assets.push({
            id: asset.id,
            family_id: asset.family_id || null,
            device_id: asset.device_id || "",
            camera_id: asset.camera_id || null,
            file_name: asset.file_name || "",
            content_type: asset.content_type || "image/jpeg",
            snapshot_path: asset.snapshot_path || "",
            relative_path: asset.relative_path || "",
            storage_provider: asset.storage_provider || "local",
            storage_key: asset.storage_key || "",
            edge_event_id: asset.edge_event_id || "",
            size: Number(asset.size_bytes || 0),
            url: metadataValue(asset, "url", ""),
            created_at: iso(asset.created_at, db.created_at),
            updated_at: iso(asset.updated_at, iso(asset.created_at, db.created_at)),
        });
    }

    for (const source of rowsByTable.content_sources || []) {
        db.content_sources.push({
            id: source.id,
            family_id: source.family_id || null,
            source_type: source.source_type || "link",
            title: source.title || "",
            source_name: source.source_name || "",
            url: source.url || "",
            provider: source.provider || "",
            enabled: source.enabled !== false,
            whitelist_status: source.whitelist_status || "manual",
            metadata: source.metadata || {},
            created_at: iso(source.created_at, db.created_at),
            updated_at: iso(source.updated_at, iso(source.created_at, db.created_at)),
        });
    }

    for (const event of rowsByTable.events || []) {
        db.events.push({
            id: event.id,
            family_id: event.family_id || null,
            device_id: event.device_id || "",
            camera_id: event.camera_id || null,
            media_asset_id: event.media_asset_id || null,
            idempotency_key: event.idempotency_key,
            edge_event_id: event.edge_event_id || null,
            event_type: event.event_type || "event",
            level: event.level || "warning",
            summary: event.summary || "",
            room: event.room || "",
            camera_name: event.camera_name || "",
            snapshot_path: event.snapshot_path || "",
            acknowledged: event.acknowledged === true,
            resolution: event.resolution || "",
            payload: event.payload || {},
            occurred_at: iso(event.occurred_at, db.created_at),
            created_at: iso(event.created_at, iso(event.occurred_at, db.created_at)),
            updated_at: iso(event.updated_at, iso(event.created_at, db.created_at)),
        });
    }

    for (const heartbeat of rowsByTable.device_heartbeats || []) {
        db.heartbeats.push({
            id: heartbeat.id,
            device_id: heartbeat.device_id,
            payload: heartbeat.payload || {},
            created_at: iso(heartbeat.created_at, db.created_at),
        });
    }

    for (const event of rowsByTable.calendar_events || []) {
        db.calendar_events.push({
            id: event.id,
            family_id: event.family_id,
            elder_id: event.elder_id || "elder_primary",
            title: event.title || "",
            starts_at: iso(event.starts_at, db.created_at),
            note: event.note || "",
            created_at: iso(event.created_at, db.created_at),
            updated_at: iso(event.updated_at, iso(event.created_at, db.created_at)),
        });
    }

    for (const card of rowsByTable.care_cards || []) {
        db.care_cards.push({
            id: card.id,
            card_id: card.card_id,
            family_id: card.family_id,
            elder_id: card.elder_id || "elder_primary",
            card_date: dateText(card.card_date),
            card_type: card.card_type || "daily",
            title: card.title || "",
            body: card.body || "",
            facts: Array.isArray(card.facts) ? card.facts : [],
            source_message_ids: Array.isArray(card.source_message_ids) ? card.source_message_ids : [],
            image_mode: card.image_mode || "none",
            image_url: card.image_url || "",
            actions: Array.isArray(card.actions) ? card.actions : [],
            status: card.status || "open",
            generated_by: card.generated_by || "",
            source_summary: Array.isArray(card.source_summary) ? card.source_summary : [],
            content_recommendations: Array.isArray(card.content_recommendations) ? card.content_recommendations : [],
            created_at: iso(card.created_at, db.created_at),
            updated_at: iso(card.updated_at, iso(card.created_at, db.created_at)),
        });
    }

    for (const message of rowsByTable.app_messages || []) {
        db.app_messages.push({
            id: message.id,
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
            generated_by: message.generated_by || "",
            idempotency_key: message.idempotency_key || message.message_id || message.id,
            metadata: message.metadata || {},
            scheduled_for: iso(message.scheduled_for),
            delivered_at: iso(message.delivered_at),
            read_at: iso(message.read_at),
            created_at: iso(message.created_at, db.created_at),
            updated_at: iso(message.updated_at, iso(message.created_at, db.created_at)),
        });
    }

    for (const token of rowsByTable.app_push_tokens || []) {
        db.app_push_tokens.push({
            id: token.id,
            family_id: token.family_id,
            user_id: token.user_id || "",
            app_install_id: token.app_install_id || "",
            platform: token.platform || "ios",
            push_token_hash: token.push_token_hash || "",
            token_preview: token.token_preview || "",
            status: token.status || "active",
            device_name: token.device_name || "",
            app_version: token.app_version || "",
            metadata: token.metadata || {},
            last_seen_at: iso(token.last_seen_at),
            created_at: iso(token.created_at, db.created_at),
            updated_at: iso(token.updated_at, iso(token.created_at, db.created_at)),
        });
    }

    for (const delivery of rowsByTable.notification_deliveries || []) {
        db.notification_deliveries.push({
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
            request_payload: delivery.request_payload || {},
            response_payload: delivery.response_payload || {},
            idempotency_key: delivery.idempotency_key || delivery.id,
            scheduled_for: iso(delivery.scheduled_for),
            sent_at: iso(delivery.sent_at),
            delivered_at: iso(delivery.delivered_at),
            clicked_at: iso(delivery.clicked_at),
            created_at: iso(delivery.created_at, db.created_at),
            updated_at: iso(delivery.updated_at, iso(delivery.created_at, db.created_at)),
        });
    }

    for (const run of rowsByTable.scheduler_runs || []) {
        db.scheduler_runs.push({
            id: run.id,
            family_id: run.family_id || null,
            job_type: run.job_type || "care_notification",
            status: run.status || "running",
            scope: run.scope || {},
            result: run.result || {},
            error_message: run.error_message || "",
            started_at: iso(run.started_at, db.created_at),
            finished_at: iso(run.finished_at),
            created_at: iso(run.created_at, db.created_at),
            updated_at: iso(run.updated_at, iso(run.created_at, db.created_at)),
        });
    }

    for (const job of rowsByTable.model_generation_jobs || []) {
        db.model_generation_jobs.push({
            id: job.id,
            family_id: job.family_id || null,
            provider_id: job.provider_id || "",
            purpose: job.purpose || "care_text",
            model: job.model || "",
            prompt_version: job.prompt_version || "",
            input_hash: job.input_hash || "",
            output_status: job.output_status || "pending",
            status: job.output_status || "pending",
            request_payload: job.request_payload || {},
            response_payload: job.response_payload || {},
            error_message: job.error_message || "",
            created_at: iso(job.created_at, db.created_at),
            updated_at: iso(job.updated_at, iso(job.created_at, db.created_at)),
        });
    }

    for (const recommendation of rowsByTable.content_recommendations || []) {
        db.content_recommendations.push({
            id: recommendation.id,
            family_id: recommendation.family_id || null,
            elder_id: recommendation.elder_id || "elder_primary",
            source_id: recommendation.source_id || null,
            content_type: recommendation.content_type || "article",
            title: recommendation.title || "",
            source_name: recommendation.source_name || "",
            url: recommendation.url || "",
            summary: recommendation.summary || "",
            reason: recommendation.reason || "",
            status: recommendation.status || "candidate",
            metadata: recommendation.metadata || {},
            created_at: iso(recommendation.created_at, db.created_at),
            updated_at: iso(recommendation.updated_at, iso(recommendation.created_at, db.created_at)),
        });
    }

    db.family_rules = {};
    for (const edgeRules of rowsByTable.care_rules || []) {
        if (
            edgeRules.rule_type !== "edge_rules"
            || edgeRules.enabled === false
            || !edgeRules.family_id
            || !edgeRules.config
            || typeof edgeRules.config !== "object"
        ) continue;
        db.family_rules[String(edgeRules.family_id)] = {
            ...db.rules,
            ...edgeRules.config,
            updated_at: iso(edgeRules.updated_at, edgeRules.config.updated_at || db.updated_at),
        };
    }
    const firstFamilyRules = Object.values(db.family_rules)[0];
    if (firstFamilyRules) {
        db.rules = { ...db.rules, ...firstFamilyRules };
    }

    return db;
}

async function readRowsByTable(pool) {
    const rowsByTable = {};
    for (const table of TABLE_ORDER) {
        const result = await pool.query(`select * from ${table}`);
        rowsByTable[table] = result.rows;
    }
    return rowsByTable;
}

async function insertRows(client, table, rows) {
    for (const row of rows) {
        const columns = Object.keys(row);
        if (!columns.length) continue;
        const placeholders = columns.map((_, index) => `$${index + 1}`).join(", ");
        const values = columns.map((column) => {
            const value = row[column];
            if (value && typeof value === "object" && !Buffer.isBuffer(value) && !(value instanceof Date)) {
                return JSON.stringify(value);
            }
            return value;
        });
        await client.query(`insert into ${table} (${columns.join(", ")}) values (${placeholders})`, values);
    }
}

async function replaceAllRows(pool, bundle) {
    const client = await pool.connect();
    try {
        await client.query("begin");
        for (const table of DELETE_ORDER) {
            await client.query(`delete from ${table}`);
        }
        for (const table of TABLE_ORDER) {
            await insertRows(client, table, bundle.tables[table] || []);
        }
        await client.query("commit");
    } catch (error) {
        await client.query("rollback");
        throw error;
    } finally {
        client.release();
    }
}

class PostgresStore {
    constructor(options) {
        this.kind = "postgres";
        this.pool = options.pool;
        this.db = options.db;
        this.pendingSave = Promise.resolve();
        this.last_save_error = "";
    }

    nextId(type) {
        const next = Number(this.db.next_ids[type] || 1);
        this.db.next_ids[type] = next + 1;
        return next;
    }

    save() {
        this.db.updated_at = new Date().toISOString();
        const bundle = buildCloudSeedBundle(this.db, { source: "postgres-store" });
        this.pendingSave = this.pendingSave
            .then(() => replaceAllRows(this.pool, bundle))
            .then(() => {
                this.last_save_error = "";
            })
            .catch((error) => {
                this.last_save_error = error.message || String(error);
                throw error;
            });
        return this.pendingSave;
    }

    async close() {
        await this.pendingSave;
        await this.pool.end();
    }
}

async function createPostgresStore(options) {
    const { Pool } = require("pg");
    const pool = new Pool({
        connectionString: options.databaseUrl,
        ssl: options.ssl || undefined,
    });
    await pool.query("select 1");
    const rowsByTable = await readRowsByTable(pool);
    const hasSeedRows = TABLE_ORDER.some((table) => (rowsByTable[table] || []).length > 0);
    const rawDb = hasSeedRows ? createDbFromCloudRows(rowsByTable, options.initialDb) : options.initialDb;
    const db = options.normalizeDb(rawDb);
    const store = new PostgresStore({ pool, db });
    if (!hasSeedRows && options.seedWhenEmpty !== false) {
        await store.save();
    }
    return store;
}

module.exports = {
    createPostgresStore,
    createDbFromCloudRows,
    TABLE_ORDER,
};
