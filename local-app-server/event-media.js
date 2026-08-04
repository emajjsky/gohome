"use strict";

const EVENT_MEDIA_ROLES = new Set(["before", "transition", "current", "evidence"]);

function eventMediaRole(value) {
    const role = String(value || "");
    return EVENT_MEDIA_ROLES.has(role) ? role : "evidence";
}

function canonicalizeEventMedia(entries) {
    const eventAssetPairs = new Set();
    const canonicalRoles = new Set();
    const normalized = [];
    for (const entry of entries || []) {
        const eventId = String(entry?.event_id || "");
        const assetId = String(entry?.asset_id || "");
        if (!eventId || !assetId) continue;
        const pairKey = `${eventId}\u0000${assetId}`;
        if (eventAssetPairs.has(pairKey)) continue;
        eventAssetPairs.add(pairKey);
        const role = eventMediaRole(entry.role);
        const roleKey = `${eventId}\u0000${role}`;
        const canonical = entry.canonical !== false && !canonicalRoles.has(roleKey);
        if (canonical) canonicalRoles.add(roleKey);
        normalized.push({ ...entry, event_id: eventId, asset_id: assetId, role, canonical });
    }
    return normalized;
}

function withoutEventMediaPayload(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return {};
    const payload = { ...value };
    delete payload.evidence_media_assets;
    return payload;
}

module.exports = {
    canonicalizeEventMedia,
    eventMediaRole,
    withoutEventMediaPayload,
};
