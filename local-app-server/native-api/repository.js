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
}

module.exports = {
    ACTION_TYPES,
    NativeRepository,
    JsonNativeRepository,
    actionInput,
    articlesFromCareCards,
    repositoryError,
};
