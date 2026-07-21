"use strict";

const crypto = require("crypto");

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

class NativeViewService {
    constructor(repository) {
        this.repository = repository;
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
        const source = await this.repository.homeForFamily(userId, familyId);
        const payload = {
            family: source.family || null,
            weather: source.weather || null,
            calendar: Array.isArray(source.calendar) ? source.calendar : [],
            distance: source.distance || null,
            critical_alert: source.critical_alert || null,
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
}

module.exports = { NativeViewService, articleView, revisionFor };
