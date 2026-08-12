"use strict";

function normalizeText(value, limit = 160) {
    return String(value || "").replace(/\s+/g, " ").trim().slice(0, limit);
}

function factSignals(facts = []) {
    return (Array.isArray(facts) ? facts : [])
        .map((value, index) => {
            const source = value && typeof value === "object" && !Array.isArray(value) ? value : { text: value };
            return {
                id: `fact-${index + 1}`,
                type: normalizeText(source.type || "topic", 40),
                source_id: normalizeText(source.source_id, 100),
                text: normalizeText(source.text, 180),
                title: normalizeText(source.title, 24),
                body: normalizeText(source.body, 120),
                image_brief: normalizeText(source.image_brief, 120),
            };
        })
        .filter((fact) => fact.text);
}

function validateCareModelOutput(parsed, signals) {
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    const allowedKeys = new Set(["primary_fact_id", "supporting_fact_ids"]);
    if (Object.keys(parsed).some((key) => !allowedKeys.has(key))) return null;
    const allowed = new Map((Array.isArray(signals) ? signals : []).map((fact) => [fact.id, fact]));
    const primaryFactId = normalizeText(parsed.primary_fact_id, 40);
    if (!primaryFactId || !allowed.has(primaryFactId)) return null;
    const supportingFactIds = Array.isArray(parsed.supporting_fact_ids)
        ? [...new Set(parsed.supporting_fact_ids.map((item) => normalizeText(item, 40)).filter(Boolean))]
            .filter((id) => id !== primaryFactId)
            .slice(0, 2)
        : [];
    if (supportingFactIds.some((id) => !allowed.has(id))) return null;
    const factIds = [primaryFactId, ...supportingFactIds];
    return {
        primary_fact_id: primaryFactId,
        supporting_fact_ids: supportingFactIds,
        fact_ids: factIds,
        facts: factIds.map((id) => allowed.get(id)),
    };
}

module.exports = { factSignals, validateCareModelOutput };
