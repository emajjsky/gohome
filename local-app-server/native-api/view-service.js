"use strict";

const crypto = require("crypto");
const { normalizeProductPreferences, productView } = require("./product-policy");

const ONBOARDING_STEPS = new Set(["family", "profile", "device", "camera", "complete"]);

function canonical(value) {
    if (Array.isArray(value)) return value.map(canonical);
    if (value && typeof value === "object") {
        return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
    }
    return value;
}

function revisionFor(value) {
    return crypto.createHash("sha256").update(JSON.stringify(canonical(value))).digest("hex").slice(0, 24);
}

function httpsUrl(value) {
    try {
        const parsed = new URL(String(value || ""));
        return parsed.protocol === "https:" ? parsed.toString() : "";
    } catch (_error) {
        return "";
    }
}

function articleView(article) {
    const sourceUrl = httpsUrl(article.source_url || article.url);
    if (!sourceUrl) return null;
    return {
        id: String(article.id || ""),
        category: String(article.category || article.content_type || "生活"),
        title: String(article.title || "").trim(),
        summary: String(article.summary || "").trim(),
        image_url: httpsUrl(article.image_url || article.metadata?.image_url),
        source_name: String(article.source_name || "").trim(),
        source_url: sourceUrl,
        published_at: article.published_at || article.created_at || null,
    };
}

function criticalAlertView(event) {
    if (!event) return null;
    return {
        id: String(event.id || ""),
        title: String(event.summary || event.title || "需要确认一条安全提醒").trim(),
        level: String(event.level || "critical"),
        acknowledged: Boolean(event.acknowledged),
    };
}

function careMessageView(message) {
    if (!message) return null;
    const metadata = message.metadata && typeof message.metadata === "object" ? message.metadata : {};
    return {
        message_id: String(message.message_id || message.id || ""),
        message_type: String(message.message_type || "care"),
        title: String(message.title || "").trim(),
        subtitle: String(message.subtitle || "").trim(),
        body: String(message.body || "").trim(),
        facts: Array.isArray(message.facts) ? message.facts.map(String).filter(Boolean).slice(0, 4) : [],
        actions: Array.isArray(message.actions)
            ? message.actions.map((action) => ({
                type: String(action?.type || action?.key || ""),
                label: action?.label ? String(action.label) : null,
            })).filter((action) => action.type)
            : [],
        status: String(message.status || "open"),
        metadata: {
            trigger_reason: String(metadata.trigger_reason || ""),
            topics: Array.isArray(metadata.topics) ? metadata.topics.map(String).filter(Boolean).slice(0, 3) : [],
            message_variants: Array.isArray(metadata.message_variants)
                ? metadata.message_variants.map(String).filter(Boolean).slice(0, 3)
                : [],
            snoozed_until: metadata.snoozed_until || null,
        },
        created_at: message.created_at || null,
        updated_at: message.updated_at || null,
    };
}

class NativeViewService {
    constructor(repository, { homeEnricher = null } = {}) {
        this.repository = repository;
        this.homeEnricher = homeEnricher;
    }

    async bootstrapForUser(userId) {
        const source = await this.repository.bootstrapForUser(userId);
        const onboarding = source.onboarding || { next_step: "family", complete: false };
        const nextStep = ONBOARDING_STEPS.has(onboarding.next_step) ? onboarding.next_step : "family";
        const payload = {
            user: source.user,
            families: Array.isArray(source.families) ? source.families : [],
            active_family_id: source.active_family_id || null,
            onboarding: { ...onboarding, next_step: nextStep, complete: nextStep === "complete" },
            unread_count: Math.max(0, Number(source.unread_count || 0)),
        };
        return { ...payload, revision: revisionFor(payload) };
    }

    async homeForFamily(userId, familyId) {
        if (!familyId) {
            const error = new Error("family_id required");
            error.statusCode = 400;
            throw error;
        }
        const baseSource = await this.repository.homeForFamily(userId, familyId);
        const source = this.homeEnricher
            ? await this.homeEnricher({ userId, familyId, source: baseSource })
            : baseSource;
        const payload = {
            family: source.family || null,
            weather: source.weather || null,
            calendar: Array.isArray(source.calendar) ? source.calendar : [],
            distance: source.distance || null,
            critical_alert: criticalAlertView(source.critical_alert),
            care_message: careMessageView(source.care_message),
            articles: (source.articles || []).map(articleView).filter((article) => article && article.title),
            cameras: Array.isArray(source.cameras) ? source.cameras : [],
        };
        return { ...payload, revision: revisionFor(payload) };
    }

    async messagesForFamily(userId, familyId, options = {}) {
        if (!familyId) throw Object.assign(new Error("family_id required"), { statusCode: 400 });
        const messages = await this.repository.messagesForFamily(userId, familyId, options);
        const payload = { messages };
        return { ...payload, revision: revisionFor(payload) };
    }

    async messageForFamily(userId, familyId, messageId) {
        if (!familyId) throw Object.assign(new Error("family_id required"), { statusCode: 400 });
        const message = await this.repository.messageForFamily(userId, familyId, messageId);
        const payload = { message };
        return { ...payload, revision: revisionFor(payload) };
    }

    async recordMessageAction(userId, familyId, messageId, action) {
        if (!familyId) throw Object.assign(new Error("family_id required"), { statusCode: 400 });
        const recorded = await this.repository.recordMessageAction(userId, familyId, messageId, action);
        const message = await this.repository.messageForFamily(userId, familyId, messageId);
        return { action: recorded, message };
    }

    async productsForFamily(userId, familyId, options = {}) {
        if (!familyId) throw Object.assign(new Error("family_id required"), { statusCode: 400 });
        const preferences = await this.repository.productPreferences(userId, familyId);
        const products = await this.repository.productsForFamily(userId, familyId, options);
        const payload = { products: products.map((product) => productView(product, preferences)).filter(Boolean) };
        return { ...payload, revision: revisionFor(payload) };
    }

    async productForFamily(userId, familyId, productId) {
        if (!familyId) throw Object.assign(new Error("family_id required"), { statusCode: 400 });
        const preferences = await this.repository.productPreferences(userId, familyId);
        const source = await this.repository.productById(userId, familyId, productId);
        const product = productView(source, preferences);
        if (!product) throw Object.assign(new Error("product not found"), { statusCode: 404 });
        const payload = { product };
        return { ...payload, revision: revisionFor(payload) };
    }

    async productPreferences(userId, familyId) {
        if (!familyId) throw Object.assign(new Error("family_id required"), { statusCode: 400 });
        return { preferences: await this.repository.productPreferences(userId, familyId) };
    }

    async updateProductPreferences(userId, familyId, input) {
        if (!familyId) throw Object.assign(new Error("family_id required"), { statusCode: 400 });
        const preferences = await this.repository.updateProductPreferences(
            userId,
            familyId,
            normalizeProductPreferences(input),
        );
        return { preferences };
    }
}

module.exports = { NativeViewService, articleView, careMessageView, criticalAlertView, revisionFor };
