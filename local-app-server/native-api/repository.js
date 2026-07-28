"use strict";

const crypto = require("crypto");
const { dayBoundsShanghai } = require("./activity-reporting");

const ACTION_TYPES = new Set([
    "opened",
    "shared",
    "contacted",
    "snoozed",
    "dismissed",
    "returned_home",
]);

function repositoryError(message, statusCode) {
    return Object.assign(new Error(message), { statusCode });
}

function clone(value) {
    if (value === undefined) return undefined;
    return JSON.parse(JSON.stringify(value));
}

function textId(value) {
    return String(value || "");
}

function limitValue(value, fallback = 50, maximum = 100) {
    const parsed = Number(value);
    if (!Number.isInteger(parsed) || parsed < 1) return fallback;
    return Math.min(parsed, maximum);
}

function arrayValue(value) {
    return Array.isArray(value)
        ? [...new Set(value.map((item) => String(item || "").trim()).filter(Boolean))]
        : [];
}

function dateKeyShanghai(value = new Date()) {
    return new Intl.DateTimeFormat("en-CA", {
        timeZone: "Asia/Shanghai",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
    }).format(value);
}

function activityTrackingEnabled(metadata = {}) {
    const value = metadata?.activity_history?.tracking_enabled;
    return value === undefined ? true : Boolean(value);
}

function articlesFromCareCards(cards = [], familyId = "") {
    const seen = new Set();
    return [...cards]
        .filter((card) => textId(card.family_id) === textId(familyId))
        .sort((a, b) => String(b.card_date || b.updated_at || "").localeCompare(String(a.card_date || a.updated_at || "")))
        .flatMap((card) => Array.isArray(card.content_recommendations) ? card.content_recommendations : [])
        .filter((item) => item?.type === "search_result" && item.title && item.url)
        .filter((item) => {
            const url = String(item.url || "").trim();
            if (!url || seen.has(url)) return false;
            seen.add(url);
            return true;
        })
        .slice(0, 30)
        .map((item, index) => ({
            id: String(item.id || `care-article-${index}-${Buffer.from(String(item.url)).toString("base64url").slice(0, 12)}`),
            family_id: textId(familyId),
            content_type: String(item.module || item.topic || "生活"),
            title: String(item.title || ""),
            summary: String(item.summary || ""),
            source_name: String(item.source || ""),
            url: String(item.url || ""),
            metadata: { image_url: String(item.image_url || "") },
            published_at: item.published_at || null,
        }));
}

function actionInput(action = {}, now = Date.now()) {
    const actionType = textId(action.action_type || action.type);
    if (!ACTION_TYPES.has(actionType)) {
        throw repositoryError("invalid message action", 400);
    }
    const idempotencyKey = textId(action.idempotency_key || action.idempotencyKey);
    if (!idempotencyKey) throw repositoryError("idempotency key required", 400);
    const payload = action.payload && typeof action.payload === "object" && !Array.isArray(action.payload)
        ? clone(action.payload)
        : {};
    for (const key of ["selected_text", "topic"]) {
        if (payload[key] === undefined) continue;
        payload[key] = String(payload[key] || "").trim().slice(0, key === "selected_text" ? 1000 : 200);
    }
    if (payload.channel !== undefined) payload.channel = String(payload.channel || "").trim().slice(0, 40);
    if (actionType === "snoozed") {
        const snoozedUntil = Date.parse(payload.snoozed_until || payload.until || "");
        if (!Number.isFinite(snoozedUntil) || snoozedUntil <= now) throw repositoryError("snooze time must be in the future", 400);
    }
    return {
        action_type: actionType,
        payload,
        idempotency_key: idempotencyKey,
    };
}

function memoryInput(input = {}, { partial = false } = {}) {
    const body = input.body === undefined && partial ? undefined : String(input.body || "").trim().slice(0, 4000);
    const people = input.people === undefined && partial ? undefined : arrayValue(input.people).slice(0, 20);
    const locationName = input.location_name === undefined && partial
        ? undefined
        : String(input.location_name || "").trim().slice(0, 120);
    let happenedAt;
    if (input.happened_at !== undefined || !partial) {
        const timestamp = Date.parse(input.happened_at || new Date().toISOString());
        if (!Number.isFinite(timestamp)) throw repositoryError("invalid memory date", 400);
        happenedAt = new Date(timestamp).toISOString();
    }
    const assetIds = input.asset_ids === undefined && partial
        ? undefined
        : arrayValue(input.asset_ids).slice(0, 9);
    if (!partial && !body && !assetIds.length) throw repositoryError("memory content required", 400);
    return {
        ...(body !== undefined ? { body } : {}),
        ...(people !== undefined ? { people } : {}),
        ...(locationName !== undefined ? { location_name: locationName } : {}),
        ...(happenedAt !== undefined ? { happened_at: happenedAt } : {}),
        ...(assetIds !== undefined ? { asset_ids: assetIds } : {}),
    };
}

function validateMemoryAssets(assets) {
    const items = Array.isArray(assets) ? assets : [];
    const videoCount = items.filter((asset) => String(asset?.content_type || "").startsWith("video/")).length;
    if (videoCount > 1 || (videoCount === 1 && items.length !== 1)) {
        throw repositoryError("memory media must contain either one video or up to nine images", 400);
    }
}

function activityIntervalInput(input = {}, now = Date.now()) {
    const sourceIntervalId = textId(input.source_interval_id).trim().slice(0, 160);
    if (!sourceIntervalId) throw repositoryError("source_interval_id required", 400);
    const started = Date.parse(input.started_at || "");
    const ended = Date.parse(input.ended_at || "");
    if (!Number.isFinite(started) || !Number.isFinite(ended) || ended <= started) throw repositoryError("invalid activity interval", 400);
    if (ended - started > 6 * 60 * 60 * 1000) throw repositoryError("activity interval too long", 400);
    if (ended > now + 5 * 60 * 1000) throw repositoryError("activity interval is in the future", 400);
    const confidence = input.confidence === undefined || input.confidence === null ? null : Number(input.confidence);
    if (confidence !== null && (!Number.isFinite(confidence) || confidence < 0 || confidence > 1)) throw repositoryError("invalid activity confidence", 400);
    return {
        source_interval_id: sourceIntervalId,
        camera_id: textId(input.camera_id).trim().slice(0, 120) || null,
        room: String(input.room || "").trim().slice(0, 80),
        started_at: new Date(started).toISOString(),
        ended_at: new Date(ended).toISOString(),
        person_count_max: Math.max(0, Math.min(20, Number.parseInt(input.person_count_max ?? 1, 10) || 0)),
        postures: arrayValue(input.postures).slice(0, 12),
        confidence,
        metadata: input.metadata && typeof input.metadata === "object" && !Array.isArray(input.metadata) ? clone(input.metadata) : {},
    };
}

function safeUserExport(user = {}) {
    return {
        id: textId(user.id),
        email: String(user.email || ""),
        phone: String(user.phone || ""),
        display_name: String(user.display_name || ""),
        status: String(user.status || "active"),
        created_at: user.created_at || null,
        updated_at: user.updated_at || null,
    };
}

function maskedMemberAccount(user = {}) {
    const phone = String(user.phone || "").replace(/\D/g, "");
    if (/^1\d{10}$/.test(phone)) return `${phone.slice(0, 3)}****${phone.slice(-4)}`;
    const email = String(user.email || "").trim();
    if (!email.includes("@")) return "";
    const [name, domain] = email.split("@");
    return `${name.slice(0, 2)}***@${domain}`;
}

function familyMemberView(member, user, currentUserId) {
    return {
        id: textId(member.id),
        user_id: textId(member.user_id),
        display_name: String(user?.display_name || "家庭成员"),
        account_hint: maskedMemberAccount(user),
        role: String(member.role || "member"),
        is_current_user: textId(member.user_id) === textId(currentUserId),
        joined_at: member.joined_at || member.created_at || null,
    };
}

const FAMILY_INVITATION_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ";
const FAMILY_INVITATION_TTL_MINUTES = 10;

function generateFamilyInvitationCode() {
    let value = "";
    while (value.length < 12) {
        const byte = crypto.randomBytes(1)[0];
        if (byte >= 224) continue;
        value += FAMILY_INVITATION_ALPHABET[byte % FAMILY_INVITATION_ALPHABET.length];
    }
    return `GH-${value.slice(0, 4)}-${value.slice(4, 8)}-${value.slice(8)}`;
}

function normalizeFamilyInvitationCode(value) {
    const compact = String(value || "").trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
    if (!/^GH[23456789ABCDEFGHJKMNPQRSTVWXYZ]{12}$/.test(compact)) return "";
    return `GH-${compact.slice(2, 6)}-${compact.slice(6, 10)}-${compact.slice(10, 14)}`;
}

function hashFamilyInvitationCode(value) {
    const normalized = normalizeFamilyInvitationCode(value);
    return normalized ? crypto.createHash("sha256").update(normalized).digest("hex") : "";
}

function familyInvitationDurationMinutes(value) {
    const parsed = Number.parseInt(value, 10);
    return Number.isInteger(parsed) ? Math.max(5, Math.min(60, parsed)) : FAMILY_INVITATION_TTL_MINUTES;
}

function familyInvitationView(invitation, now = Date.now()) {
    const expiresAt = Date.parse(invitation.expires_at || "");
    const status = String(invitation.status || "active") === "active" && Number.isFinite(expiresAt) && expiresAt <= now
        ? "expired"
        : String(invitation.status || "active");
    return {
        id: textId(invitation.id),
        family_id: textId(invitation.family_id),
        status,
        code_hint: String(invitation.code_hint || ""),
        expires_at: invitation.expires_at || null,
        created_at: invitation.created_at || null,
        used_at: invitation.used_at || null,
        revoked_at: invitation.revoked_at || null,
    };
}

function invalidFamilyInvitation() {
    return repositoryError("邀请码无效或已失效。", 404);
}

function accountDeletionPlanForDb(db, userId) {
    const user = textId(userId);
    const memberships = (db.family_members || []).filter((item) => (
        textId(item.user_id) === user && String(item.status || "active") === "active"
    ));
    const families = memberships.map((membership) => {
        const family = (db.families || []).find((item) => textId(item.id) === textId(membership.family_id)) || {};
        const activeMembers = (db.family_members || []).filter((item) => (
            textId(item.family_id) === textId(membership.family_id) && String(item.status || "active") === "active"
        ));
        const role = String(membership.role || "member").toLowerCase();
        const ownsFamily = ["owner", "creator"].includes(role) || textId(family.created_by_user_id) === user;
        return {
            id: textId(membership.family_id),
            name: String(family.name || "家庭"),
            role: String(membership.role || "member"),
            owns_family: ownsFamily,
            active_member_count: activeMembers.length,
            action: ownsFamily ? (activeMembers.length > 1 ? "transfer_ownership" : "delete_family") : "leave_family",
        };
    });
    const blockers = families
        .filter((family) => family.action === "transfer_ownership")
        .map((family) => ({
            code: "ownership_transfer_required",
            family_id: family.id,
            family_name: family.name,
            message: `请先为“${family.name}”转交家庭创建者身份`,
        }));
    const familyIdsToDelete = families.filter((family) => family.action === "delete_family").map((family) => family.id);
    const membershipIdsToLeave = families.filter((family) => family.action === "leave_family").map((family) => family.id);
    const authoredMemories = (db.family_memories || []).filter((item) => textId(item.author_user_id) === user).length;
    return {
        can_delete: blockers.length === 0,
        requires_ownership_transfer: blockers.length > 0,
        families,
        blockers,
        deletion_scope: {
            families_to_delete: familyIdsToDelete,
            memberships_to_leave: membershipIdsToLeave,
            authored_memories: authoredMemories,
        },
        retention_note: "账号、登录凭证、推送标识和可删除内容将被移除；依法必须保留的安全审计会解除账号关联后按期限留存。",
    };
}

function accountExportForDb(db, userId, generatedAt = new Date().toISOString()) {
    const user = textId(userId);
    const account = (db.users || []).find((item) => textId(item.id) === user);
    if (!account) throw repositoryError("user not found", 404);
    const memberships = (db.family_members || []).filter((item) => (
        textId(item.user_id) === user && String(item.status || "active") === "active"
    ));
    const usersById = new Map((db.users || []).map((item) => [textId(item.id), item]));
    const values = (source) => Array.isArray(source) ? source : Object.values(source || {});
    const forFamily = (source, familyId) => values(source).filter((item) => textId(item.family_id) === familyId);

    const families = memberships.map((membership) => {
        const familyId = textId(membership.family_id);
        const family = (db.families || []).find((item) => textId(item.id) === familyId) || {};
        const memoryRows = forFamily(db.family_memories, familyId);
        const memoryIds = new Set(memoryRows.map((item) => textId(item.id)));
        const memoryMedia = (db.family_memory_media || []).filter((item) => memoryIds.has(textId(item.memory_id)));
        const memoryComments = (db.family_memory_comments || []).filter((item) => memoryIds.has(textId(item.memory_id)));
        const memoryFavorites = (db.family_memory_favorites || []).filter((item) => memoryIds.has(textId(item.memory_id)));
        const messageIds = new Set(forFamily(db.app_messages, familyId).map((item) => textId(item.message_id || item.id)));
        const events = forFamily(db.events, familyId).map((item) => {
            const evidenceIds = [item.media_asset_id, ...(Array.isArray(item.payload?.evidence_media_assets)
                ? item.payload.evidence_media_assets.map((evidence) => evidence?.asset_id || evidence?.id)
                : [])].map(textId).filter(Boolean);
            return {
                id: textId(item.id),
                event_type: String(item.event_type || "event"),
                level: String(item.level || "warning"),
                summary: String(item.summary || ""),
                room: String(item.room || ""),
                camera_id: item.camera_id ? textId(item.camera_id) : null,
                camera_name: String(item.camera_name || ""),
                occurred_at: item.occurred_at || null,
                acknowledged: Boolean(item.acknowledged),
                resolution: String(item.resolution || ""),
                evidence_asset_ids: [...new Set(evidenceIds)],
                verification: item.payload?.verification ? {
                    status: String(item.payload.verification.status || ""),
                    reason: String(item.payload.verification.result?.reason || ""),
                } : null,
            };
        });
        return {
            family: {
                id: familyId,
                name: String(family.name || "家庭"),
                status: String(family.status || "active"),
                timezone: String(family.timezone || "Asia/Shanghai"),
                role: String(membership.role || "member"),
                joined_at: membership.joined_at || membership.created_at || null,
                created_at: family.created_at || null,
                updated_at: family.updated_at || null,
            },
            members: forFamily(db.family_members, familyId)
                .filter((item) => String(item.status || "active") === "active")
                .map((item) => ({
                    user_id: textId(item.user_id),
                    display_name: String(usersById.get(textId(item.user_id))?.display_name || "家庭成员"),
                    role: String(item.role || "member"),
                    status: String(item.status || "active"),
                    joined_at: item.joined_at || item.created_at || null,
                })),
            care_profiles: forFamily(db.elder_profiles, familyId).map((item) => ({
                id: textId(item.id),
                display_name: String(item.display_name || ""),
                relationship: String(item.relationship || ""),
                age: item.age ?? null,
                city: String(item.city || ""),
                phone: String(item.phone || ""),
                mobile_phone: String(item.mobile_phone || ""),
                home_phone: String(item.home_phone || ""),
                health_notes: String(item.health_notes || ""),
                care_preferences: clone(item.care_preferences || {}),
                created_at: item.created_at || null,
                updated_at: item.updated_at || null,
            })),
            devices: forFamily(db.devices, familyId).map((item) => ({
                device_id: textId(item.device_id || item.id),
                name: String(item.name || "回家盒子"),
                device_type: String(item.device_type || "edge-agent"),
                status: String(item.status || ""),
                app_version: String(item.app_version || ""),
                model_version: String(item.model_version || ""),
                last_seen_at: item.last_seen_at || null,
                created_at: item.created_at || null,
            })),
            device_bindings: forFamily(db.device_bindings, familyId).map((item) => ({
                id: textId(item.id),
                device_id: textId(item.device_id),
                device_name: String(item.device_name || "回家盒子"),
                status: String(item.status || ""),
                bound_at: item.bound_at || item.created_at || null,
                last_seen_at: item.last_seen_at || null,
            })),
            cameras: forFamily(db.cameras, familyId).map((item) => ({
                id: textId(item.id),
                device_id: item.device_id ? textId(item.device_id) : null,
                name: String(item.name || ""),
                room: String(item.room || ""),
                enabled: item.enabled !== false,
                status: String(item.status || ""),
                sync_status: String(item.sync_status || ""),
                created_at: item.created_at || null,
                updated_at: item.updated_at || null,
            })),
            rules: clone(db.family_rules?.[familyId] || {}),
            care_preferences: clone(db.care_preferences?.[familyId] || null),
            calendar: forFamily(db.calendar_events, familyId).map((item) => ({
                id: textId(item.id), title: String(item.title || ""), starts_at: item.starts_at || null,
                note: String(item.note || ""), created_at: item.created_at || null,
            })),
            events,
            media: forFamily(db.assets, familyId).map((item) => ({
                id: textId(item.id),
                camera_id: item.camera_id ? textId(item.camera_id) : null,
                device_id: item.device_id ? textId(item.device_id) : null,
                content_type: String(item.content_type || "application/octet-stream"),
                size_bytes: Number(item.size_bytes || item.size || 0),
                purpose: String(item.purpose || item.metadata?.purpose || "evidence"),
                created_at: item.created_at || null,
            })),
            memories: memoryRows.map((item) => ({
                id: textId(item.id),
                author_user_id: textId(item.author_user_id),
                body: String(item.body || ""),
                happened_at: item.happened_at || null,
                location_name: String(item.location_name || ""),
                people: arrayValue(item.people),
                media: memoryMedia.filter((media) => textId(media.memory_id) === textId(item.id)).map((media) => ({
                    asset_id: textId(media.asset_id), sort_order: Number(media.sort_order || 0), alt_text: String(media.alt_text || ""),
                })),
                comments: memoryComments.filter((comment) => textId(comment.memory_id) === textId(item.id)).map((comment) => ({
                    id: textId(comment.id), author_user_id: textId(comment.author_user_id), body: String(comment.body || ""), created_at: comment.created_at || null,
                })),
                favorite_user_ids: memoryFavorites.filter((favorite) => textId(favorite.memory_id) === textId(item.id)).map((favorite) => textId(favorite.user_id)),
                created_at: item.created_at || null,
                updated_at: item.updated_at || null,
            })),
            activity_intervals: forFamily(db.activity_intervals, familyId).map((item) => ({
                id: textId(item.id), camera_id: item.camera_id ? textId(item.camera_id) : null,
                room: String(item.room || ""), started_at: item.started_at || null, ended_at: item.ended_at || null,
                person_count_max: Number(item.person_count_max || 0), postures: arrayValue(item.postures), confidence: item.confidence ?? null,
            })),
            care_cards: forFamily(db.care_cards, familyId).map((item) => ({
                id: textId(item.id), card_date: item.card_date || null, card_type: String(item.card_type || "daily"),
                title: String(item.title || ""), body: String(item.body || ""), facts: clone(item.facts || []), status: String(item.status || "open"),
                created_at: item.created_at || null,
            })),
            messages: forFamily(db.app_messages, familyId).map((item) => ({
                id: textId(item.message_id || item.id), message_type: String(item.message_type || "care"),
                title: String(item.title || ""), subtitle: String(item.subtitle || ""), body: String(item.body || ""),
                facts: clone(item.facts || []), status: String(item.status || "open"), created_at: item.created_at || null,
            })),
            message_actions: (db.app_message_actions || []).filter((item) => (
                textId(item.family_id) === familyId && messageIds.has(textId(item.message_id))
            )).map((item) => ({
                id: textId(item.id), message_id: textId(item.message_id), user_id: item.user_id ? textId(item.user_id) : null,
                action_type: String(item.action_type || ""), payload: clone(item.payload || {}), created_at: item.created_at || null,
            })),
        };
    });
    return {
        schema_version: 1,
        generated_at: generatedAt,
        account: safeUserExport(account),
        families,
        export_scope: {
            family_count: families.length,
            includes_media_files: false,
            includes_media_metadata: true,
        },
    };
}

function applyAccountDeletionToDb(db, userId, plan) {
    const user = textId(userId);
    const deletedFamilyIds = new Set((plan?.deletion_scope?.families_to_delete || []).map(textId));
    const familyMatches = (item) => deletedFamilyIds.has(textId(item?.family_id));
    const arrayFilter = (key, predicate) => {
        if (Array.isArray(db[key])) db[key] = db[key].filter((item) => !predicate(item));
    };
    const deletedDeviceIds = new Set(Object.values(db.devices || {})
        .filter(familyMatches)
        .map((item) => textId(item.device_id || item.id)));
    const deletedMemoryIds = new Set((db.family_memories || [])
        .filter((item) => familyMatches(item) || textId(item.author_user_id) === user)
        .map((item) => textId(item.id)));
    const deletedMessageIds = new Set((db.app_messages || [])
        .filter((item) => familyMatches(item) || textId(item.user_id) === user)
        .map((item) => textId(item.message_id || item.id)));

    arrayFilter("families", (item) => deletedFamilyIds.has(textId(item.id)));
    arrayFilter("family_members", (item) => familyMatches(item) || textId(item.user_id) === user);
    arrayFilter("family_invitations", (item) => (
        familyMatches(item)
        || textId(item.created_by_user_id) === user
        || textId(item.used_by_user_id) === user
    ));
    arrayFilter("app_sessions", (item) => textId(item.user_id) === user);
    arrayFilter("device_bindings", familyMatches);
    arrayFilter("binding_codes", familyMatches);
    arrayFilter("device_tokens", familyMatches);
    arrayFilter("media_upload_intents", (item) => familyMatches(item) || textId(item.user_id) === user);
    arrayFilter("events", familyMatches);
    arrayFilter("heartbeats", (item) => deletedDeviceIds.has(textId(item.device_id)));
    arrayFilter("calendar_events", familyMatches);
    arrayFilter("care_cards", familyMatches);
    arrayFilter("app_messages", (item) => familyMatches(item) || textId(item.user_id) === user);
    arrayFilter("app_message_actions", (item) => (
        familyMatches(item) || textId(item.user_id) === user || deletedMessageIds.has(textId(item.message_id))
    ));
    arrayFilter("notification_deliveries", (item) => familyMatches(item) || textId(item.user_id) === user);
    arrayFilter("app_push_tokens", (item) => familyMatches(item) || textId(item.user_id) === user);
    arrayFilter("scheduler_runs", familyMatches);
    arrayFilter("model_generation_jobs", familyMatches);
    arrayFilter("content_sources", familyMatches);
    arrayFilter("content_recommendations", familyMatches);
    arrayFilter("activity_intervals", familyMatches);
    arrayFilter("family_memories", (item) => deletedMemoryIds.has(textId(item.id)));
    arrayFilter("family_memory_media", (item) => deletedMemoryIds.has(textId(item.memory_id)));
    arrayFilter("family_memory_comments", (item) => deletedMemoryIds.has(textId(item.memory_id)) || textId(item.author_user_id) === user);
    arrayFilter("family_memory_favorites", (item) => deletedMemoryIds.has(textId(item.memory_id)) || textId(item.user_id) === user);
    arrayFilter("device_config_versions", familyMatches);
    arrayFilter("audit_logs", familyMatches);
    arrayFilter("users", (item) => textId(item.id) === user);

    for (const [key, profile] of Object.entries(db.elder_profiles || {})) {
        if (familyMatches(profile)) delete db.elder_profiles[key];
    }
    for (const [key, camera] of Object.entries(db.cameras || {})) {
        if (familyMatches(camera)) delete db.cameras[key];
    }
    for (const device of Object.values(db.devices || {})) {
        if (!familyMatches(device)) continue;
        device.family_id = null;
        device.updated_at = new Date().toISOString();
    }
    for (const familyId of deletedFamilyIds) {
        if (db.family_rules) delete db.family_rules[familyId];
        if (db.care_preferences) delete db.care_preferences[familyId];
        if (db.product_preferences) delete db.product_preferences[familyId];
    }
    for (const preferences of Object.values(db.product_preferences || {})) {
        if (textId(preferences?.updated_by) === user) preferences.updated_by = null;
    }
    for (const log of db.audit_logs || []) {
        if (textId(log.actor_user_id) === user) log.actor_user_id = null;
    }
    if (textId(db.active_user_id) === user) db.active_user_id = db.users?.[0]?.id || null;
    return { deleted_family_ids: [...deletedFamilyIds], deleted_memory_ids: [...deletedMemoryIds] };
}

class NativeRepository {
    bootstrapForUser(_userId) {
        throw new Error("NativeRepository.bootstrapForUser is not implemented");
    }

    familyMembers(_userId, _familyId) {
        throw new Error("NativeRepository.familyMembers is not implemented");
    }

    removeFamilyMember(_userId, _familyId, _memberId) {
        throw new Error("NativeRepository.removeFamilyMember is not implemented");
    }

    leaveFamily(_userId, _familyId) {
        throw new Error("NativeRepository.leaveFamily is not implemented");
    }

    transferFamilyOwnership(_userId, _familyId, _targetMemberId, _input) {
        throw new Error("NativeRepository.transferFamilyOwnership is not implemented");
    }

    familyInvitations(_userId, _familyId) {
        throw new Error("NativeRepository.familyInvitations is not implemented");
    }

    createFamilyInvitation(_userId, _familyId, _input) {
        throw new Error("NativeRepository.createFamilyInvitation is not implemented");
    }

    revokeFamilyInvitation(_userId, _familyId, _invitationId) {
        throw new Error("NativeRepository.revokeFamilyInvitation is not implemented");
    }

    consumeFamilyInvitation(_userId, _code) {
        throw new Error("NativeRepository.consumeFamilyInvitation is not implemented");
    }

    homeForFamily(_userId, _familyId) {
        throw new Error("NativeRepository.homeForFamily is not implemented");
    }

    messagesForFamily(_userId, _familyId, _options = {}) {
        throw new Error("NativeRepository.messagesForFamily is not implemented");
    }

    messageForFamily(_userId, _familyId, _messageId) {
        throw new Error("NativeRepository.messageForFamily is not implemented");
    }

    recordMessageAction(_userId, _familyId, _messageId, _action) {
        throw new Error("NativeRepository.recordMessageAction is not implemented");
    }

    productsForFamily(_userId, _familyId, _options = {}) {
        throw new Error("NativeRepository.productsForFamily is not implemented");
    }

    productById(_userId, _familyId, _productId) {
        throw new Error("NativeRepository.productById is not implemented");
    }

    productPreferences(_userId, _familyId) {
        throw new Error("NativeRepository.productPreferences is not implemented");
    }

    updateProductPreferences(_userId, _familyId, _input) {
        throw new Error("NativeRepository.updateProductPreferences is not implemented");
    }

    memoriesForFamily(_userId, _familyId, _options = {}) {
        throw new Error("NativeRepository.memoriesForFamily is not implemented");
    }

    createMemory(_userId, _familyId, _input) {
        throw new Error("NativeRepository.createMemory is not implemented");
    }

    updateMemory(_userId, _familyId, _memoryId, _input) {
        throw new Error("NativeRepository.updateMemory is not implemented");
    }

    deleteMemory(_userId, _familyId, _memoryId) {
        throw new Error("NativeRepository.deleteMemory is not implemented");
    }

    addMemoryComment(_userId, _familyId, _memoryId, _input) {
        throw new Error("NativeRepository.addMemoryComment is not implemented");
    }

    deleteMemoryComment(_userId, _familyId, _memoryId, _commentId) {
        throw new Error("NativeRepository.deleteMemoryComment is not implemented");
    }

    setMemoryFavorite(_userId, _familyId, _memoryId, _favorite) {
        throw new Error("NativeRepository.setMemoryFavorite is not implemented");
    }

    activityTimelineForFamily(_userId, _familyId, _options = {}) {
        throw new Error("NativeRepository.activityTimelineForFamily is not implemented");
    }

    activityIntervalsForFamily(_userId, _familyId, _options = {}) {
        throw new Error("NativeRepository.activityIntervalsForFamily is not implemented");
    }

    deleteActivityHistory(_userId, _familyId) {
        throw new Error("NativeRepository.deleteActivityHistory is not implemented");
    }

    cleanupExpiredActivityIntervals() {
        throw new Error("NativeRepository.cleanupExpiredActivityIntervals is not implemented");
    }

    ingestActivityIntervals(_familyId, _deviceId, _intervals) {
        throw new Error("NativeRepository.ingestActivityIntervals is not implemented");
    }

    accountExport(_userId) {
        throw new Error("NativeRepository.accountExport is not implemented");
    }

    accountDeletionPlan(_userId) {
        throw new Error("NativeRepository.accountDeletionPlan is not implemented");
    }

    deleteAccount(_userId, _input) {
        throw new Error("NativeRepository.deleteAccount is not implemented");
    }
}

class JsonNativeRepository extends NativeRepository {
    constructor(db, {
        idFactory = () => `action-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        clock = () => new Date().toISOString(),
        onFamilyMetadataChange = () => {},
        onFamilyMembershipChange = () => {},
        onFamilyInvitationChange = () => {},
        invitationCodeFactory = generateFamilyInvitationCode,
    } = {}) {
        super();
        this.db = db || {};
        this.idFactory = idFactory;
        this.clock = clock;
        this.onFamilyMetadataChange = onFamilyMetadataChange;
        this.onFamilyMembershipChange = onFamilyMembershipChange;
        this.onFamilyInvitationChange = onFamilyInvitationChange;
        this.invitationCodeFactory = invitationCodeFactory;
        if (!Array.isArray(this.db.family_members)) this.db.family_members = [];
        if (!Array.isArray(this.db.family_invitations)) this.db.family_invitations = [];
        if (!Array.isArray(this.db.app_messages)) this.db.app_messages = [];
        if (!Array.isArray(this.db.app_message_actions)) this.db.app_message_actions = [];
        if (!Array.isArray(this.db.product_catalog)) this.db.product_catalog = [];
        if (!this.db.product_preferences || typeof this.db.product_preferences !== "object") this.db.product_preferences = {};
        if (!Array.isArray(this.db.family_memories)) this.db.family_memories = [];
        if (!Array.isArray(this.db.family_memory_media)) this.db.family_memory_media = [];
        if (!Array.isArray(this.db.family_memory_comments)) this.db.family_memory_comments = [];
        if (!Array.isArray(this.db.family_memory_favorites)) this.db.family_memory_favorites = [];
        if (!Array.isArray(this.db.activity_intervals)) this.db.activity_intervals = [];
        if (!Array.isArray(this.db.app_message_actions)) this.db.app_message_actions = [];
        if (!Array.isArray(this.db.media_upload_intents)) this.db.media_upload_intents = [];
    }

    user(userId) {
        const id = textId(userId);
        const user = (this.db.users || []).find((item) => textId(item.id) === id);
        if (!user) throw repositoryError("user not found", 404);
        return clone(user);
    }

    assertFamilyAccess(userId, familyId) {
        const user = textId(userId);
        const family = textId(familyId);
        const member = this.db.family_members.find((item) => (
            textId(item.user_id) === user &&
            textId(item.family_id) === family &&
            (item.status || "active") === "active"
        ));
        if (!member) throw repositoryError("family access denied", 403);
        return member;
    }

    assertFamilyManager(userId, familyId) {
        const member = this.assertFamilyAccess(userId, familyId);
        if (!["owner", "creator"].includes(textId(member.role).toLowerCase())) {
            throw repositoryError("family management permission required", 403);
        }
        return member;
    }

    family(familyId) {
        return clone((this.db.families || []).find((item) => textId(item.id) === textId(familyId)) || null);
    }

    bootstrapForUser(userId) {
        const user = this.user(userId);
        const memberships = this.db.family_members
            .filter((item) => textId(item.user_id) === textId(userId) && (item.status || "active") === "active")
            .sort((a, b) => textId(a.family_id).localeCompare(textId(b.family_id)));
        const families = memberships
            .map((member) => {
                const family = this.family(member.family_id);
                if (!family) return null;
                return {
                    ...family,
                    role: String(member.role || "member"),
                    member_count: this.db.family_members.filter((item) => textId(item.family_id) === textId(member.family_id) && String(item.status || "active") === "active").length,
                };
            })
            .filter(Boolean);
        const activeFamilyId = families[0]?.id || null;
        const onboarding = activeFamilyId
            ? this.onboardingForFamily(userId, activeFamilyId)
            : { next_step: "family", complete: false };
        return clone({
            user,
            families,
            active_family_id: activeFamilyId,
            onboarding,
            unread_count: this.db.app_messages.filter((message) => (
                textId(message.family_id) === textId(activeFamilyId) &&
                !message.read_at &&
                (message.status || "open") !== "dismissed"
            )).length,
            revision: textId(this.db.updated_at || this.clock()),
        });
    }

    familyMembers(userId, familyId) {
        this.assertFamilyAccess(userId, familyId);
        const users = new Map((this.db.users || []).map((user) => [textId(user.id), user]));
        return clone(this.db.family_members
            .filter((member) => textId(member.family_id) === textId(familyId) && String(member.status || "active") === "active")
            .sort((left, right) => {
                const rank = (member) => ["owner", "creator"].includes(String(member.role || "").toLowerCase()) ? 0 : 1;
                return rank(left) - rank(right) || String(left.joined_at || left.created_at || "").localeCompare(String(right.joined_at || right.created_at || ""));
            })
            .map((member) => familyMemberView(member, users.get(textId(member.user_id)), userId)));
    }

    removeFamilyMember(userId, familyId, memberId) {
        this.assertFamilyManager(userId, familyId);
        const member = this.db.family_members.find((item) => textId(item.id) === textId(memberId) && textId(item.family_id) === textId(familyId) && String(item.status || "active") === "active");
        if (!member) throw repositoryError("family member not found", 404);
        if (textId(member.user_id) === textId(userId)) throw repositoryError("creator cannot remove self", 409);
        if (["owner", "creator"].includes(String(member.role || "").toLowerCase())) throw repositoryError("family creator cannot be removed", 409);
        member.status = "removed";
        member.updated_at = this.clock();
        this.onFamilyMembershipChange({ family_id: textId(familyId), memberships: [clone(member)] });
        return { removed: true, member_id: textId(member.id), family_id: textId(familyId) };
    }

    leaveFamily(userId, familyId) {
        const member = this.assertFamilyAccess(userId, familyId);
        if (["owner", "creator"].includes(String(member.role || "").toLowerCase())) throw repositoryError("transfer family ownership before leaving", 409);
        member.status = "left";
        member.updated_at = this.clock();
        this.onFamilyMembershipChange({ family_id: textId(familyId), memberships: [clone(member)] });
        return { left: true, family_id: textId(familyId) };
    }

    transferFamilyOwnership(userId, familyId, targetMemberId, input = {}) {
        if (String(input.confirmation || "") !== "TRANSFER_OWNERSHIP") throw repositoryError("ownership transfer confirmation required", 400);
        const current = this.assertFamilyManager(userId, familyId);
        const target = this.db.family_members.find((item) => textId(item.id) === textId(targetMemberId) && textId(item.family_id) === textId(familyId) && String(item.status || "active") === "active");
        if (!target) throw repositoryError("family member not found", 404);
        if (textId(target.user_id) === textId(userId)) throw repositoryError("select another family member", 400);
        const changedMemberships = [];
        for (const member of this.db.family_members) {
            if (textId(member.family_id) !== textId(familyId) || String(member.status || "active") !== "active") continue;
            if (textId(member.id) === textId(target.id)) continue;
            if (!["owner", "creator"].includes(String(member.role || "").toLowerCase())) continue;
            member.role = "member";
            member.updated_at = this.clock();
            changedMemberships.push(clone(member));
        }
        target.role = "owner";
        target.updated_at = this.clock();
        changedMemberships.push(clone(target));
        const family = (this.db.families || []).find((item) => textId(item.id) === textId(familyId));
        if (family) {
            family.created_by_user_id = target.user_id;
            family.metadata = { ...(family.metadata || {}), created_by_user_id: target.user_id };
            family.updated_at = this.clock();
        }
        this.onFamilyMembershipChange({ family_id: textId(familyId), created_by_user_id: textId(target.user_id), memberships: changedMemberships });
        return { transferred: true, family_id: textId(familyId), new_owner_member_id: textId(target.id), new_owner_user_id: textId(target.user_id) };
    }

    familyInvitations(userId, familyId) {
        this.assertFamilyManager(userId, familyId);
        const now = Date.parse(this.clock());
        return clone(this.db.family_invitations
            .filter((item) => textId(item.family_id) === textId(familyId))
            .sort((left, right) => String(right.created_at || "").localeCompare(String(left.created_at || "")))
            .map((item) => familyInvitationView(item, now)));
    }

    createFamilyInvitation(userId, familyId, input = {}) {
        this.assertFamilyManager(userId, familyId);
        const family = this.family(familyId);
        if (!family) throw repositoryError("family not found", 404);
        const timestamp = this.clock();
        const now = Date.parse(timestamp);
        for (const existing of this.db.family_invitations) {
            if (textId(existing.family_id) !== textId(familyId) || String(existing.status || "active") !== "active") continue;
            existing.status = Date.parse(existing.expires_at || "") <= now ? "expired" : "revoked";
            if (existing.status === "revoked") existing.revoked_at = timestamp;
            existing.updated_at = timestamp;
        }
        let code = "";
        let codeHash = "";
        for (let attempt = 0; attempt < 5; attempt += 1) {
            code = normalizeFamilyInvitationCode(this.invitationCodeFactory());
            codeHash = hashFamilyInvitationCode(code);
            if (codeHash && !this.db.family_invitations.some((item) => item.code_hash === codeHash)) break;
            code = "";
        }
        if (!code) throw repositoryError("could not create invitation", 503);
        const expiresAt = new Date(now + familyInvitationDurationMinutes(input.expires_in_minutes) * 60 * 1000).toISOString();
        const invitation = {
            id: textId(this.idFactory()).replace(/^action-/, "family-invitation-"),
            family_id: textId(familyId),
            code_hash: codeHash,
            code_hint: code.slice(-4),
            created_by_user_id: textId(userId),
            status: "active",
            expires_at: expiresAt,
            used_by_user_id: null,
            used_at: null,
            revoked_at: null,
            created_at: timestamp,
            updated_at: timestamp,
        };
        this.db.family_invitations.push(invitation);
        this.onFamilyInvitationChange({ invitations: this.db.family_invitations.filter((item) => textId(item.family_id) === textId(familyId)).map(clone) });
        return { ...familyInvitationView(invitation, now), code };
    }

    revokeFamilyInvitation(userId, familyId, invitationId) {
        this.assertFamilyManager(userId, familyId);
        const invitation = this.db.family_invitations.find((item) => (
            textId(item.id) === textId(invitationId) && textId(item.family_id) === textId(familyId)
        ));
        if (!invitation) throw repositoryError("invitation not found", 404);
        if (String(invitation.status || "active") === "active") {
            invitation.status = "revoked";
            invitation.revoked_at = this.clock();
            invitation.updated_at = invitation.revoked_at;
            this.onFamilyInvitationChange({ invitations: [clone(invitation)] });
        }
        return familyInvitationView(invitation, Date.parse(this.clock()));
    }

    consumeFamilyInvitation(userId, rawCode) {
        this.user(userId);
        const codeHash = hashFamilyInvitationCode(rawCode);
        if (!codeHash) throw invalidFamilyInvitation();
        const invitation = this.db.family_invitations.find((item) => item.code_hash === codeHash);
        const timestamp = this.clock();
        const now = Date.parse(timestamp);
        if (!invitation || String(invitation.status || "active") !== "active") throw invalidFamilyInvitation();
        if (Date.parse(invitation.expires_at || "") <= now) {
            invitation.status = "expired";
            invitation.updated_at = timestamp;
            this.onFamilyInvitationChange({ invitations: [clone(invitation)] });
            throw invalidFamilyInvitation();
        }
        const family = this.family(invitation.family_id);
        if (!family || String(family.status || "active") !== "active") throw invalidFamilyInvitation();
        let membership = this.db.family_members.find((item) => (
            textId(item.family_id) === textId(invitation.family_id) && textId(item.user_id) === textId(userId)
        ));
        if (membership && String(membership.status || "active") === "active") {
            throw repositoryError("你已经加入这个家庭。", 409);
        }
        if (!membership) {
            membership = {
                id: `family-member-${crypto.randomUUID()}`,
                family_id: textId(invitation.family_id),
                user_id: textId(userId),
                role: "member",
                status: "active",
                invited_by: invitation.created_by_user_id || null,
                joined_at: timestamp,
                created_at: timestamp,
                updated_at: timestamp,
            };
            this.db.family_members.push(membership);
        } else {
            Object.assign(membership, {
                role: "member",
                status: "active",
                invited_by: invitation.created_by_user_id || null,
                joined_at: timestamp,
                updated_at: timestamp,
            });
        }
        invitation.status = "used";
        invitation.used_by_user_id = textId(userId);
        invitation.used_at = timestamp;
        invitation.updated_at = timestamp;
        this.onFamilyMembershipChange({ family_id: textId(invitation.family_id), memberships: [clone(membership)] });
        this.onFamilyInvitationChange({ invitations: [clone(invitation)] });
        const memberCount = this.db.family_members.filter((item) => (
            textId(item.family_id) === textId(invitation.family_id) && String(item.status || "active") === "active"
        )).length;
        return { joined: true, family: { id: textId(family.id), name: String(family.name || "家庭"), member_count: memberCount } };
    }

    accountExport(userId) {
        this.user(userId);
        return clone(accountExportForDb(this.db, userId, this.clock()));
    }

    accountDeletionPlan(userId) {
        this.user(userId);
        return clone(accountDeletionPlanForDb(this.db, userId));
    }

    deleteAccount(userId, input = {}) {
        this.user(userId);
        if (String(input.confirmation || "") !== "DELETE_ACCOUNT") {
            throw repositoryError("account deletion confirmation required", 400);
        }
        const plan = accountDeletionPlanForDb(this.db, userId);
        if (!plan.can_delete) throw repositoryError("family ownership transfer required", 409);
        const deletedFamilyIds = new Set(plan.deletion_scope.families_to_delete.map(textId));
        const deletedMemoryIds = new Set((this.db.family_memories || [])
            .filter((item) => deletedFamilyIds.has(textId(item.family_id)) || textId(item.author_user_id) === textId(userId))
            .map((item) => textId(item.id)));
        const cleanupAssetIds = new Set((this.db.assets || [])
            .filter((item) => deletedFamilyIds.has(textId(item.family_id)))
            .map((item) => textId(item.id)));
        for (const media of this.db.family_memory_media || []) {
            if (!deletedMemoryIds.has(textId(media.memory_id))) continue;
            const usedByRetainedMemory = this.db.family_memory_media.some((candidate) => (
                textId(candidate.asset_id) === textId(media.asset_id) && !deletedMemoryIds.has(textId(candidate.memory_id))
            ));
            if (!usedByRetainedMemory) cleanupAssetIds.add(textId(media.asset_id));
        }
        const cleanupObjects = (this.db.media_upload_intents || [])
            .filter((item) => deletedFamilyIds.has(textId(item.family_id)) || textId(item.user_id) === textId(userId))
            .map((item) => ({ storage_provider: "cos", storage_key: String(item.object_key || "") }))
            .filter((item) => item.storage_key);
        applyAccountDeletionToDb(this.db, userId, plan);
        return {
            deleted: true,
            deleted_user_id: textId(userId),
            deleted_family_ids: [...deletedFamilyIds],
            cleanup_all_asset_ids: [...cleanupAssetIds].filter(Boolean),
            cleanup_storage_objects: cleanupObjects,
        };
    }

    onboardingForFamily(userId, familyId) {
        this.assertFamilyAccess(userId, familyId);
        const family = (this.db.families || []).find((item) => textId(item.id) === textId(familyId));
        const metadata = family?.metadata && typeof family.metadata === "object" && !Array.isArray(family.metadata)
            ? family.metadata
            : {};
        if (textId(metadata.onboarding_completed_at)) {
            return { next_step: "complete", complete: true };
        }
        const hasProfile = Object.values(this.db.elder_profiles || {}).some((profile) => textId(profile.family_id) === textId(familyId));
        const hasDevice = Object.values(this.db.devices || {}).some((device) => (
            textId(device.family_id) === textId(familyId) && textId(device.status).toLowerCase() !== "revoked"
        ));
        const hasCamera = Object.values(this.db.cameras || {}).some((camera) => (
            textId(camera.family_id) === textId(familyId) && textId(camera.status).toLowerCase() !== "deleted"
        ));
        const hasCameraHistory = (this.db.events || []).some((event) => textId(event.family_id) === textId(familyId));
        if (hasProfile && ((hasDevice && hasCamera) || hasCameraHistory)) {
            if (family) {
                family.metadata = { ...metadata, onboarding_completed_at: this.clock() };
                this.onFamilyMetadataChange(textId(familyId), family.metadata);
            }
            return { next_step: "complete", complete: true };
        }
        const nextStep = !hasProfile ? "profile" : !hasDevice ? "device" : !hasCamera ? "camera" : "complete";
        return { next_step: nextStep, complete: nextStep === "complete" };
    }

    homeForFamily(userId, familyId) {
        this.assertFamilyAccess(userId, familyId);
        const family = this.family(familyId);
        const elder = Object.values(this.db.elder_profiles || {}).find((profile) => textId(profile.family_id) === textId(familyId)) || null;
        const cameras = Object.values(this.db.cameras || {}).filter((camera) => textId(camera.family_id) === textId(familyId));
        const calendar = (this.db.calendar_events || []).filter((event) => textId(event.family_id) === textId(familyId));
        const events = (this.db.events || []).filter((event) => textId(event.family_id) === textId(familyId));
        const published = (this.db.content_recommendations || []).filter((article) => (
            (textId(article.family_id) === textId(familyId) || !article.family_id)
            && (article.status || "published") === "published"
        ));
        const articles = published.length
            ? published
            : articlesFromCareCards(this.db.care_cards || [], familyId);
        const now = Date.parse(this.clock());
        const careMessage = this.db.app_messages
            .filter((message) => (
                textId(message.family_id) === textId(familyId)
                && ["activity_insight", "return_home", "care_card"].includes(textId(message.message_type))
                && textId(message.status || "open") === "open"
            ))
            .filter((message) => {
                const snoozedUntil = Date.parse(message.metadata?.snoozed_until || "");
                return !Number.isFinite(snoozedUntil) || snoozedUntil <= now;
            })
            .sort((a, b) => {
                const priority = (message) => ({ activity_insight: 0, return_home: 1, care_card: 2 }[textId(message.message_type)] ?? 3);
                return priority(a) - priority(b) || Date.parse(b.created_at || 0) - Date.parse(a.created_at || 0);
            })[0] || null;
        return clone({
            family,
            elder,
            cameras,
            calendar,
            critical_alert: events.find((event) => !event.acknowledged && ["critical", "emergency"].includes(event.level)) || null,
            care_message: careMessage,
            articles,
            weather: null,
            distance: null,
        });
    }

    messagesForFamily(userId, familyId, options = {}) {
        this.assertFamilyAccess(userId, familyId);
        const status = textId(options.status);
        return clone(this.db.app_messages
            .filter((message) => textId(message.family_id) === textId(familyId) && (!status || textId(message.status) === status))
            .sort((a, b) => Date.parse(b.created_at || 0) - Date.parse(a.created_at || 0))
            .slice(0, limitValue(options.limit)));
    }

    messageForFamily(userId, familyId, messageId) {
        this.assertFamilyAccess(userId, familyId);
        const message = this.db.app_messages.find((item) => textId(item.family_id) === textId(familyId) && textId(item.message_id || item.id) === textId(messageId));
        if (!message) throw repositoryError("message not found", 404);
        return clone(message);
    }

    recordMessageAction(userId, familyId, messageId, action) {
        this.assertFamilyAccess(userId, familyId);
        const message = this.db.app_messages.find((item) => textId(item.family_id) === textId(familyId) && textId(item.message_id || item.id) === textId(messageId));
        if (!message) throw repositoryError("message not found", 404);
        const timestamp = this.clock();
        const input = actionInput(action, Date.parse(timestamp));
        const existing = this.db.app_message_actions.find((item) => item.idempotency_key === input.idempotency_key);
        if (existing) {
            if (textId(existing.family_id) !== textId(familyId)) throw repositoryError("idempotency key conflict", 409);
            return clone(existing);
        }
        const row = {
            id: textId(this.idFactory()),
            family_id: textId(familyId),
            message_id: textId(message.message_id || message.id),
            user_id: textId(userId),
            action_type: input.action_type,
            payload: input.payload,
            idempotency_key: input.idempotency_key,
            created_at: timestamp,
        };
        this.db.app_message_actions.push(row);
        if (input.action_type === "opened") message.read_at = message.read_at || timestamp;
        if (input.action_type === "dismissed") message.status = "dismissed";
        if (["contacted", "returned_home"].includes(input.action_type)) message.status = "closed";
        if (input.action_type === "snoozed") {
            message.metadata = { ...(message.metadata || {}), snoozed_until: input.payload.snoozed_until || input.payload.until };
        }
        message.updated_at = timestamp;
        if (input.action_type === "returned_home") {
            const family = textId(familyId);
            const preferences = this.db.care_preferences[family] || { family_id: family, metadata: {} };
            const metadata = preferences.metadata && typeof preferences.metadata === "object" ? preferences.metadata : {};
            const schedule = metadata.care_card_schedule && typeof metadata.care_card_schedule === "object"
                ? metadata.care_card_schedule
                : {};
            preferences.metadata = {
                ...metadata,
                care_card_schedule: {
                    ...schedule,
                    visit_reminder: {
                        ...(schedule.visit_reminder || {}),
                        last_visit_at: dateKeyShanghai(new Date(timestamp)),
                        next_visit_at: "",
                    },
                },
            };
            preferences.updated_at = timestamp;
            this.db.care_preferences[family] = preferences;
        }
        return clone(row);
    }

    productsForFamily(userId, familyId, options = {}) {
        this.assertFamilyAccess(userId, familyId);
        const preferences = this.db.product_preferences[textId(familyId)] || {};
        const requestedCategories = arrayValue(options.categories);
        const categories = requestedCategories.length ? requestedCategories : arrayValue(preferences.categories);
        const catalog = this.db.product_catalog
            .filter((product) => (product.status || "draft") === "active")
            .filter((product) => !categories.length || categories.includes(textId(product.category)))
            .sort((a, b) => Date.parse(b.verified_at || b.updated_at || 0) - Date.parse(a.verified_at || a.updated_at || 0));
        return clone(catalog.slice(0, limitValue(options.limit)));
    }

    productById(userId, familyId, productId) {
        this.assertFamilyAccess(userId, familyId);
        const product = this.db.product_catalog.find((item) => textId(item.id) === textId(productId) && (item.status || "draft") === "active");
        if (!product) throw repositoryError("product not found", 404);
        return clone(product);
    }

    productPreferences(userId, familyId) {
        this.assertFamilyAccess(userId, familyId);
        return clone(this.db.product_preferences[textId(familyId)] || {
            family_id: textId(familyId),
            categories: [],
            needs: [],
            updated_by: null,
            updated_at: null,
        });
    }

    updateProductPreferences(userId, familyId, input = {}) {
        this.assertFamilyAccess(userId, familyId);
        const family = textId(familyId);
        const row = {
            ...(this.db.product_preferences[family] || {}),
            family_id: family,
            categories: arrayValue(input.categories),
            needs: arrayValue(input.needs),
            updated_by: textId(userId),
            updated_at: this.clock(),
        };
        this.db.product_preferences[family] = row;
        return clone(row);
    }

    memoryView(userId, memory) {
        const author = (this.db.users || []).find((item) => textId(item.id) === textId(memory.author_user_id));
        const media = this.db.family_memory_media
            .filter((item) => textId(item.memory_id) === textId(memory.id))
            .sort((a, b) => Number(a.sort_order || 0) - Number(b.sort_order || 0))
            .map((item) => {
                const asset = (this.db.assets || []).find((candidate) => textId(candidate.id) === textId(item.asset_id));
                const contentType = String(asset?.content_type || "image/jpeg");
                const mediaURL = `/api/v1/video/assets/${encodeURIComponent(item.asset_id)}`;
                return {
                    ...item,
                    content_type: contentType,
                    media_type: contentType.startsWith("video/") ? "video" : "image",
                    image_url: mediaURL,
                    media_url: mediaURL,
                    duration_seconds: Number(asset?.metadata?.duration_seconds || 0),
                };
            });
        const comments = this.db.family_memory_comments
            .filter((item) => textId(item.memory_id) === textId(memory.id))
            .sort((a, b) => Date.parse(a.created_at || 0) - Date.parse(b.created_at || 0));
        const favorites = this.db.family_memory_favorites.filter((item) => textId(item.memory_id) === textId(memory.id));
        return {
            ...memory,
            author: author ? { id: textId(author.id), display_name: String(author.display_name || "家庭成员") } : null,
            media,
            comments,
            favorite_count: favorites.length,
            is_favorite: favorites.some((item) => textId(item.user_id) === textId(userId)),
        };
    }

    memoriesForFamily(userId, familyId, options = {}) {
        this.assertFamilyAccess(userId, familyId);
        return clone(this.db.family_memories
            .filter((memory) => textId(memory.family_id) === textId(familyId) && (memory.status || "published") === "published")
            .sort((a, b) => Date.parse(b.happened_at || b.created_at || 0) - Date.parse(a.happened_at || a.created_at || 0))
            .slice(0, limitValue(options.limit, 30, 50))
            .map((memory) => this.memoryView(userId, memory)));
    }

    createMemory(userId, familyId, input = {}) {
        this.assertFamilyAccess(userId, familyId);
        const value = memoryInput(input);
        const timestamp = this.clock();
        const assets = value.asset_ids.map((assetId) => {
            const asset = (this.db.assets || []).find((item) => textId(item.id) === textId(assetId) && textId(item.family_id) === textId(familyId));
            if (!asset) throw repositoryError("memory asset not found", 400);
            return asset;
        });
        validateMemoryAssets(assets);
        const memory = {
            id: textId(this.idFactory()).replace(/^action-/, "memory-"),
            family_id: textId(familyId),
            author_user_id: textId(userId),
            body: value.body,
            happened_at: value.happened_at,
            location_name: value.location_name,
            people: value.people,
            visibility: "family",
            status: "published",
            metadata: {},
            created_at: timestamp,
            updated_at: timestamp,
        };
        this.db.family_memories.push(memory);
        assets.forEach((asset, index) => {
            this.db.family_memory_media.push({
                id: `${memory.id}-media-${index}`,
                family_id: textId(familyId),
                memory_id: memory.id,
                asset_id: textId(asset.id),
                sort_order: index,
                alt_text: "",
                created_at: timestamp,
            });
        });
        return clone(this.memoryView(userId, memory));
    }

    updateMemory(userId, familyId, memoryId, input = {}) {
        const member = this.assertFamilyAccess(userId, familyId);
        const memory = this.db.family_memories.find((item) => textId(item.id) === textId(memoryId) && textId(item.family_id) === textId(familyId));
        if (!memory) throw repositoryError("memory not found", 404);
        if (textId(memory.author_user_id) !== textId(userId) && textId(member.role) !== "creator") throw repositoryError("memory edit denied", 403);
        const value = memoryInput(input, { partial: true });
        const assets = value.asset_ids?.map((assetId) => {
            const asset = (this.db.assets || []).find((item) => textId(item.id) === textId(assetId) && textId(item.family_id) === textId(familyId));
            if (!asset) throw repositoryError("memory asset not found", 400);
            return asset;
        });
        if (assets !== undefined) validateMemoryAssets(assets);
        const nextBody = value.body ?? memory.body;
        const nextMediaCount = assets === undefined
            ? this.db.family_memory_media.filter((item) => textId(item.memory_id) === textId(memory.id)).length
            : assets.length;
        if (!String(nextBody || "").trim() && !nextMediaCount) throw repositoryError("memory content required", 400);
        for (const key of ["body", "people", "location_name", "happened_at"]) {
            if (value[key] !== undefined) memory[key] = value[key];
        }
        let cleanupAssetIds = [];
        if (assets !== undefined) {
            const nextAssetIds = new Set(assets.map((asset) => textId(asset.id)));
            cleanupAssetIds = this.db.family_memory_media
                .filter((item) => textId(item.memory_id) === textId(memory.id) && !nextAssetIds.has(textId(item.asset_id)))
                .map((item) => textId(item.asset_id));
            this.db.family_memory_media = this.db.family_memory_media.filter((item) => textId(item.memory_id) !== textId(memory.id));
            assets.forEach((asset, index) => {
                this.db.family_memory_media.push({ id: `${memory.id}-media-${index}`, family_id: textId(familyId), memory_id: memory.id, asset_id: textId(asset.id), sort_order: index, alt_text: "", created_at: this.clock() });
            });
        }
        memory.updated_at = this.clock();
        return { memory: clone(this.memoryView(userId, memory)), cleanup_asset_ids: cleanupAssetIds };
    }

    deleteMemory(userId, familyId, memoryId) {
        const member = this.assertFamilyAccess(userId, familyId);
        const index = this.db.family_memories.findIndex((item) => textId(item.id) === textId(memoryId) && textId(item.family_id) === textId(familyId));
        if (index < 0) throw repositoryError("memory not found", 404);
        const memory = this.db.family_memories[index];
        if (textId(memory.author_user_id) !== textId(userId) && textId(member.role) !== "creator") throw repositoryError("memory delete denied", 403);
        const assetIds = this.db.family_memory_media
            .filter((item) => textId(item.memory_id) === textId(memoryId))
            .map((item) => textId(item.asset_id));
        this.db.family_memories.splice(index, 1);
        this.db.family_memory_media = this.db.family_memory_media.filter((item) => textId(item.memory_id) !== textId(memoryId));
        this.db.family_memory_comments = this.db.family_memory_comments.filter((item) => textId(item.memory_id) !== textId(memoryId));
        this.db.family_memory_favorites = this.db.family_memory_favorites.filter((item) => textId(item.memory_id) !== textId(memoryId));
        return { deleted: true, memory_id: textId(memoryId), cleanup_asset_ids: assetIds };
    }

    addMemoryComment(userId, familyId, memoryId, input = {}) {
        this.assertFamilyAccess(userId, familyId);
        const memory = this.db.family_memories.find((item) => textId(item.id) === textId(memoryId) && textId(item.family_id) === textId(familyId));
        if (!memory) throw repositoryError("memory not found", 404);
        const body = String(input.body || "").trim().slice(0, 500);
        if (!body) throw repositoryError("comment required", 400);
        const timestamp = this.clock();
        const comment = {
            id: textId(this.idFactory()).replace(/^action-/, "memory-comment-"),
            family_id: textId(familyId),
            memory_id: textId(memoryId),
            author_user_id: textId(userId),
            body,
            created_at: timestamp,
            updated_at: timestamp,
        };
        this.db.family_memory_comments.push(comment);
        return clone(this.memoryView(userId, memory));
    }

    deleteMemoryComment(userId, familyId, memoryId, commentId) {
        const member = this.assertFamilyAccess(userId, familyId);
        const memory = this.db.family_memories.find((item) => textId(item.id) === textId(memoryId) && textId(item.family_id) === textId(familyId));
        if (!memory) throw repositoryError("memory not found", 404);
        const index = this.db.family_memory_comments.findIndex((item) => textId(item.id) === textId(commentId) && textId(item.memory_id) === textId(memoryId));
        if (index < 0) throw repositoryError("comment not found", 404);
        const comment = this.db.family_memory_comments[index];
        if (textId(comment.author_user_id) !== textId(userId) && textId(member.role) !== "creator") throw repositoryError("comment delete denied", 403);
        this.db.family_memory_comments.splice(index, 1);
        return clone(this.memoryView(userId, memory));
    }

    setMemoryFavorite(userId, familyId, memoryId, favorite) {
        this.assertFamilyAccess(userId, familyId);
        const memory = this.db.family_memories.find((item) => textId(item.id) === textId(memoryId) && textId(item.family_id) === textId(familyId));
        if (!memory) throw repositoryError("memory not found", 404);
        const index = this.db.family_memory_favorites.findIndex((item) => textId(item.memory_id) === textId(memoryId) && textId(item.user_id) === textId(userId));
        if (favorite && index < 0) {
            this.db.family_memory_favorites.push({ family_id: textId(familyId), memory_id: textId(memoryId), user_id: textId(userId), created_at: this.clock() });
        } else if (!favorite && index >= 0) {
            this.db.family_memory_favorites.splice(index, 1);
        }
        return clone(this.memoryView(userId, memory));
    }

    activityTimelineForFamily(userId, familyId, options = {}) {
        this.assertFamilyAccess(userId, familyId);
        const date = /^\d{4}-\d{2}-\d{2}$/.test(String(options.date || "")) ? String(options.date) : dateKeyShanghai(new Date(this.clock()));
        const [rangeStart, rangeEnd] = dayBoundsShanghai(date);
        return clone(this.db.activity_intervals
            .filter((item) => (
                textId(item.family_id) === textId(familyId)
                && Date.parse(item.ended_at || "") > rangeStart
                && Date.parse(item.started_at || "") < rangeEnd
            ))
            .sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at)));
    }

    activityIntervalsForFamily(userId, familyId, options = {}) {
        this.assertFamilyAccess(userId, familyId);
        const startDate = String(options.start_date || "");
        const endDate = String(options.end_date || "");
        if (!/^\d{4}-\d{2}-\d{2}$/.test(startDate) || !/^\d{4}-\d{2}-\d{2}$/.test(endDate)) {
            throw repositoryError("invalid activity date range", 400);
        }
        const [rangeStart] = dayBoundsShanghai(startDate);
        const [, rangeEnd] = dayBoundsShanghai(endDate);
        if (rangeEnd <= rangeStart) throw repositoryError("invalid activity date range", 400);
        return clone(this.db.activity_intervals
            .filter((item) => {
                if (textId(item.family_id) !== textId(familyId)) return false;
                return Date.parse(item.ended_at || "") > rangeStart && Date.parse(item.started_at || "") < rangeEnd;
            })
            .sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at)));
    }

    deleteActivityHistory(userId, familyId) {
        this.assertFamilyManager(userId, familyId);
        const before = this.db.activity_intervals.length;
        this.db.activity_intervals = this.db.activity_intervals.filter((item) => textId(item.family_id) !== textId(familyId));
        return { deleted: before - this.db.activity_intervals.length };
    }

    cleanupExpiredActivityIntervals() {
        const now = Date.parse(this.clock());
        const before = this.db.activity_intervals.length;
        this.db.activity_intervals = this.db.activity_intervals.filter((item) => {
            const preferences = this.db.care_preferences?.[textId(item.family_id)] || {};
            const configured = Number(preferences.metadata?.activity_history?.retention_days);
            const retentionDays = Number.isInteger(configured) ? Math.max(7, Math.min(365, configured)) : 30;
            return Date.parse(item.ended_at || item.started_at || 0) >= now - retentionDays * 24 * 60 * 60 * 1000;
        });
        return { deleted: before - this.db.activity_intervals.length };
    }

    ingestActivityIntervals(familyId, deviceId, intervals = []) {
        const family = textId(familyId);
        const device = textId(deviceId);
        const values = intervals.slice(0, 100).map((item) => activityIntervalInput(item, Date.parse(this.clock())));
        const preferences = this.db.care_preferences?.[family] || {};
        if (!activityTrackingEnabled(preferences.metadata)) {
            return { accepted: 0, inserted: 0, skipped: values.length, reason: "activity_tracking_disabled" };
        }
        let inserted = 0;
        for (const value of values) {
            const existing = this.db.activity_intervals.find((item) => textId(item.device_id) === device && item.source_interval_id === value.source_interval_id);
            if (existing) continue;
            this.db.activity_intervals.push({ id: textId(this.idFactory()).replace(/^action-/, "activity-"), family_id: family, device_id: device, ...value, received_at: this.clock() });
            inserted += 1;
        }
        return { accepted: values.length, inserted };
    }
}

module.exports = {
    ACTION_TYPES,
    NativeRepository,
    JsonNativeRepository,
    accountDeletionPlanForDb,
    accountExportForDb,
    applyAccountDeletionToDb,
    actionInput,
    memoryInput,
    activityIntervalInput,
    activityTrackingEnabled,
    articlesFromCareCards,
    familyMemberView,
    familyInvitationView,
    generateFamilyInvitationCode,
    hashFamilyInvitationCode,
    invalidFamilyInvitation,
    normalizeFamilyInvitationCode,
    familyInvitationDurationMinutes,
    repositoryError,
};
