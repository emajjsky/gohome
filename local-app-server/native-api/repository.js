"use strict";

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

class NativeRepository {
    bootstrapForUser(_userId) {
        throw new Error("NativeRepository.bootstrapForUser is not implemented");
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

    ingestActivityIntervals(_familyId, _deviceId, _intervals) {
        throw new Error("NativeRepository.ingestActivityIntervals is not implemented");
    }
}

class JsonNativeRepository extends NativeRepository {
    constructor(db, { idFactory = () => `action-${Date.now()}-${Math.random().toString(16).slice(2)}`, clock = () => new Date().toISOString() } = {}) {
        super();
        this.db = db || {};
        this.idFactory = idFactory;
        this.clock = clock;
        if (!Array.isArray(this.db.family_members)) this.db.family_members = [];
        if (!Array.isArray(this.db.app_messages)) this.db.app_messages = [];
        if (!Array.isArray(this.db.app_message_actions)) this.db.app_message_actions = [];
        if (!Array.isArray(this.db.product_catalog)) this.db.product_catalog = [];
        if (!this.db.product_preferences || typeof this.db.product_preferences !== "object") this.db.product_preferences = {};
        if (!Array.isArray(this.db.family_memories)) this.db.family_memories = [];
        if (!Array.isArray(this.db.family_memory_media)) this.db.family_memory_media = [];
        if (!Array.isArray(this.db.family_memory_comments)) this.db.family_memory_comments = [];
        if (!Array.isArray(this.db.family_memory_favorites)) this.db.family_memory_favorites = [];
        if (!Array.isArray(this.db.activity_intervals)) this.db.activity_intervals = [];
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

    family(familyId) {
        return clone((this.db.families || []).find((item) => textId(item.id) === textId(familyId)) || null);
    }

    bootstrapForUser(userId) {
        const user = this.user(userId);
        const memberships = this.db.family_members
            .filter((item) => textId(item.user_id) === textId(userId) && (item.status || "active") === "active")
            .sort((a, b) => textId(a.family_id).localeCompare(textId(b.family_id)));
        const families = memberships
            .map((member) => this.family(member.family_id))
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

    onboardingForFamily(userId, familyId) {
        this.assertFamilyAccess(userId, familyId);
        const hasProfile = Object.values(this.db.elder_profiles || {}).some((profile) => textId(profile.family_id) === textId(familyId));
        const hasDevice = Object.values(this.db.devices || {}).some((device) => textId(device.family_id) === textId(familyId));
        const hasCamera = Object.values(this.db.cameras || {}).some((camera) => textId(camera.family_id) === textId(familyId));
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
                && ["return_home", "care_card"].includes(textId(message.message_type))
                && textId(message.status || "open") === "open"
            ))
            .filter((message) => {
                const snoozedUntil = Date.parse(message.metadata?.snoozed_until || "");
                return !Number.isFinite(snoozedUntil) || snoozedUntil <= now;
            })
            .sort((a, b) => {
                const priority = (message) => textId(message.message_type) === "return_home" ? 0 : 1;
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
            .sort((a, b) => Number(a.sort_order || 0) - Number(b.sort_order || 0));
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
        return clone(this.db.activity_intervals
            .filter((item) => textId(item.family_id) === textId(familyId) && dateKeyShanghai(new Date(item.started_at)) === date)
            .sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at)));
    }

    ingestActivityIntervals(familyId, deviceId, intervals = []) {
        const family = textId(familyId);
        const device = textId(deviceId);
        const values = intervals.slice(0, 100).map((item) => activityIntervalInput(item, Date.parse(this.clock())));
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
    actionInput,
    memoryInput,
    activityIntervalInput,
    articlesFromCareCards,
    repositoryError,
};
