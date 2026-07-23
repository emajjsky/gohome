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

function memoryView(memory) {
    const media = Array.isArray(memory?.media) ? memory.media : [];
    const comments = Array.isArray(memory?.comments) ? memory.comments : [];
    return {
        id: String(memory?.id || ""),
        family_id: String(memory?.family_id || ""),
        author: memory?.author ? {
            id: String(memory.author.id || ""),
            display_name: String(memory.author.display_name || "家庭成员"),
        } : null,
        body: String(memory?.body || "").trim(),
        happened_at: memory?.happened_at || memory?.created_at || null,
        location_name: String(memory?.location_name || "").trim(),
        people: Array.isArray(memory?.people) ? memory.people.map(String).filter(Boolean).slice(0, 20) : [],
        media: media.map((item) => ({
            id: String(item.id || ""),
            asset_id: String(item.asset_id || ""),
            image_url: String(item.image_url || `/api/v1/video/assets/${item.asset_id || ""}`),
            sort_order: Number(item.sort_order || 0),
            alt_text: String(item.alt_text || ""),
        })).filter((item) => item.asset_id),
        comments: comments.map((item) => ({
            id: String(item.id || ""),
            author_user_id: String(item.author_user_id || ""),
            body: String(item.body || "").trim(),
            created_at: item.created_at || null,
        })).filter((item) => item.id && item.body),
        favorite_count: Math.max(0, Number(memory?.favorite_count || 0)),
        is_favorite: Boolean(memory?.is_favorite),
        created_at: memory?.created_at || null,
        updated_at: memory?.updated_at || null,
    };
}

function activityIntervalView(interval) {
    return {
        id: String(interval?.id || ""),
        camera_id: interval?.camera_id ? String(interval.camera_id) : null,
        room: String(interval?.room || "").trim(),
        started_at: interval?.started_at || null,
        ended_at: interval?.ended_at || null,
        person_count_max: Math.max(0, Number(interval?.person_count_max || 0)),
        postures: Array.isArray(interval?.postures) ? interval.postures.map(String).filter(Boolean) : [],
        confidence: interval?.confidence === null || interval?.confidence === undefined ? null : Number(interval.confidence),
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

    async memoriesForFamily(userId, familyId, options = {}) {
        if (!familyId) throw Object.assign(new Error("family_id required"), { statusCode: 400 });
        const memories = await this.repository.memoriesForFamily(userId, familyId, options);
        const payload = { memories: memories.map(memoryView).filter((memory) => memory.id) };
        return { ...payload, revision: revisionFor(payload) };
    }

    async createMemory(userId, familyId, input) {
        if (!familyId) throw Object.assign(new Error("family_id required"), { statusCode: 400 });
        return { memory: memoryView(await this.repository.createMemory(userId, familyId, input)) };
    }

    async updateMemory(userId, familyId, memoryId, input) {
        if (!familyId) throw Object.assign(new Error("family_id required"), { statusCode: 400 });
        const result = await this.repository.updateMemory(userId, familyId, memoryId, input);
        return {
            memory: memoryView(result.memory),
            cleanup_asset_ids: result.cleanup_asset_ids || [],
        };
    }

    async deleteMemory(userId, familyId, memoryId) {
        if (!familyId) throw Object.assign(new Error("family_id required"), { statusCode: 400 });
        return await this.repository.deleteMemory(userId, familyId, memoryId);
    }

    async addMemoryComment(userId, familyId, memoryId, input) {
        if (!familyId) throw Object.assign(new Error("family_id required"), { statusCode: 400 });
        return { memory: memoryView(await this.repository.addMemoryComment(userId, familyId, memoryId, input)) };
    }

    async deleteMemoryComment(userId, familyId, memoryId, commentId) {
        if (!familyId) throw Object.assign(new Error("family_id required"), { statusCode: 400 });
        return { memory: memoryView(await this.repository.deleteMemoryComment(userId, familyId, memoryId, commentId)) };
    }

    async setMemoryFavorite(userId, familyId, memoryId, favorite) {
        if (!familyId) throw Object.assign(new Error("family_id required"), { statusCode: 400 });
        return { memory: memoryView(await this.repository.setMemoryFavorite(userId, familyId, memoryId, favorite)) };
    }

    async activityTimelineForFamily(userId, familyId, options = {}) {
        if (!familyId) throw Object.assign(new Error("family_id required"), { statusCode: 400 });
        const intervals = await this.repository.activityTimelineForFamily(userId, familyId, options);
        const payload = { date: options.date || null, intervals: intervals.map(activityIntervalView).filter((item) => item.id) };
        return { ...payload, revision: revisionFor(payload) };
    }
}

module.exports = { NativeViewService, activityIntervalView, articleView, careMessageView, criticalAlertView, memoryView, revisionFor };
