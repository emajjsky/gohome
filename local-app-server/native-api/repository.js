"use strict";

const ACTION_TYPES = new Set([
    "opened",
    "shared",
    "contacted",
    "snoozed",
    "dismissed",
    "returned_home",
]);

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

function actionInput(action = {}) {
    const actionType = textId(action.action_type || action.type);
    if (!ACTION_TYPES.has(actionType)) {
        throw new Error("invalid message action");
    }
    const idempotencyKey = textId(action.idempotency_key || action.idempotencyKey);
    if (!idempotencyKey) throw new Error("idempotency key required");
    return {
        action_type: actionType,
        payload: action.payload && typeof action.payload === "object" ? clone(action.payload) : {},
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
        if (!user) throw new Error("user not found");
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
        if (!member) throw new Error("family access denied");
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
        const articles = (this.db.content_recommendations || []).filter((article) => textId(article.family_id) === textId(familyId) || !article.family_id);
        return clone({
            family,
            elder,
            cameras,
            calendar,
            critical_alert: events.find((event) => !event.acknowledged && ["critical", "emergency"].includes(event.level)) || null,
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
        if (!message) throw new Error("message not found");
        return clone(message);
    }

    recordMessageAction(userId, familyId, messageId, action) {
        this.assertFamilyAccess(userId, familyId);
        const message = this.db.app_messages.find((item) => textId(item.family_id) === textId(familyId) && textId(item.message_id || item.id) === textId(messageId));
        if (!message) throw new Error("message not found");
        const input = actionInput(action);
        const existing = this.db.app_message_actions.find((item) => item.idempotency_key === input.idempotency_key);
        if (existing) {
            if (textId(existing.family_id) !== textId(familyId)) throw new Error("idempotency key conflict");
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
            created_at: this.clock(),
        };
        this.db.app_message_actions.push(row);
        return clone(row);
    }

    productsForFamily(userId, familyId, options = {}) {
        this.assertFamilyAccess(userId, familyId);
        const preferences = this.db.product_preferences[textId(familyId)] || {};
        const categories = arrayValue(options.categories || preferences.categories);
        const catalog = this.db.product_catalog
            .filter((product) => (product.status || "draft") === "active")
            .filter((product) => !categories.length || categories.includes(textId(product.category)))
            .sort((a, b) => Date.parse(b.verified_at || b.updated_at || 0) - Date.parse(a.verified_at || a.updated_at || 0));
        return clone(catalog.slice(0, limitValue(options.limit)));
    }

    productById(userId, familyId, productId) {
        this.assertFamilyAccess(userId, familyId);
        const product = this.db.product_catalog.find((item) => textId(item.id) === textId(productId) && (item.status || "draft") === "active");
        if (!product) throw new Error("product not found");
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
};
