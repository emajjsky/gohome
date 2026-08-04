"use strict";

const fs = require("fs");
const path = require("path");

const DAY_MS = 24 * 60 * 60 * 1000;
const COS_PREFIXES = Object.freeze({
    eventEvidence: "event-evidence/",
    familyMemory: "memory-media/",
});
const MANAGED_COS_PREFIXES = Object.freeze(Object.values(COS_PREFIXES));

function positiveDays(value, fallback) {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? number : fallback;
}

function retentionPolicies(env = process.env) {
    return Object.freeze({
        family_memory: null,
        user_upload: null,
        critical_event_evidence: positiveDays(env.GOHOME_COS_CRITICAL_EVIDENCE_RETENTION_DAYS, 180),
        event_evidence: positiveDays(env.GOHOME_COS_EVENT_EVIDENCE_RETENTION_DAYS, 90),
        verification_evidence: positiveDays(env.GOHOME_COS_VERIFICATION_RETENTION_DAYS, 30),
        transient_upload: positiveDays(env.GOHOME_COS_TRANSIENT_RETENTION_DAYS, 7),
    });
}

function timestamp(value) {
    const parsed = Date.parse(value || "");
    return Number.isFinite(parsed) ? parsed : 0;
}

function objectValue(value) {
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function assetPurpose(asset) {
    return String(asset?.purpose || asset?.metadata?.purpose || "").trim().toLowerCase();
}

function eventAssetIds(event) {
    const ids = new Set();
    if (event?.media_asset_id) ids.add(String(event.media_asset_id));
    const payload = objectValue(event?.payload);
    const evidence = Array.isArray(payload.evidence_media_assets) ? payload.evidence_media_assets : [];
    for (const item of evidence) {
        const id = item?.asset_id || item?.asset?.id || item?.id;
        if (id !== null && id !== undefined && id !== "") ids.add(String(id));
    }
    const uploaded = payload.media_upload_result?.asset || event?.media_upload_result?.asset;
    if (uploaded?.id) ids.add(String(uploaded.id));
    return ids;
}

function mediaReferenceCandidates(value) {
    const raw = String(value || "").trim();
    if (!raw) return [];
    const candidates = new Set([raw]);
    try {
        const parsed = new URL(raw, "https://gohome.invalid");
        const pathname = decodeURIComponent(parsed.pathname || "").replace(/^\/+/, "");
        if (pathname) candidates.add(pathname);
        const mediaIndex = pathname.indexOf("media/");
        if (mediaIndex >= 0) candidates.add(pathname.slice(mediaIndex + "media/".length));
        const assetMatch = pathname.match(/(?:^|\/)assets\/([^/]+)$/);
        if (assetMatch?.[1]) candidates.add(assetMatch[1]);
    } catch (_error) {
        candidates.add(raw.split(/[?#]/, 1)[0].replace(/^\/+/, ""));
    }
    return [...candidates].filter(Boolean);
}

function assetReferenceIndex(assets) {
    const index = new Map();
    for (const asset of assets || []) {
        const id = String(asset?.id || "");
        if (!id) continue;
        const metadata = objectValue(asset.metadata);
        for (const value of [
            id,
            asset.relative_path,
            asset.storage_key,
            asset.file_name,
            asset.url,
            metadata.url,
        ]) {
            for (const candidate of mediaReferenceCandidates(value)) {
                if (!index.has(candidate)) index.set(candidate, id);
            }
        }
    }
    return index;
}

function referencedAssetIds(rows, referenceValue, index) {
    const ids = new Set();
    for (const row of rows || []) {
        for (const candidate of mediaReferenceCandidates(referenceValue(row))) {
            const id = index.get(candidate);
            if (id) ids.add(id);
        }
    }
    return ids;
}

function buildAssetReferences(db) {
    const events = new Map();
    for (const event of db.events || []) {
        for (const assetId of eventAssetIds(event)) {
            const current = events.get(assetId) || [];
            current.push(event);
            events.set(assetId, current);
        }
    }
    const memoryAssetIds = new Set(
        (db.family_memory_media || []).map((item) => String(item.asset_id || "")).filter(Boolean),
    );
    const index = assetReferenceIndex(db.assets || []);
    const careCardAssetIds = referencedAssetIds(db.care_cards, (card) => card?.image_url, index);
    const avatarAssetIds = referencedAssetIds(db.users, (user) => user?.metadata?.avatar_asset_id, index);
    return { events, memoryAssetIds, careCardAssetIds, avatarAssetIds };
}

function classifyAsset(asset, references, policies, nowMs) {
    const id = String(asset.id || "");
    const purpose = assetPurpose(asset);
    const metadata = objectValue(asset.metadata);
    const linkedEvents = references.events.get(id) || [];
    const linkedMemory = references.memoryAssetIds.has(id);
    const linkedCareCard = references.careCardAssetIds.has(id);
    const linkedAvatar = references.avatarAssetIds.has(id);
    let retentionClass = "";
    if (linkedMemory) retentionClass = "family_memory";
    else if (purpose.includes("validation") || purpose.includes("verification")) retentionClass = "verification_evidence";
    else if (linkedEvents.some((event) => String(event.level || "") === "critical")) retentionClass = "critical_event_evidence";
    else if (linkedEvents.length || purpose.includes("event_evidence")) retentionClass = "event_evidence";
    else if (purpose === "user_upload") retentionClass = "user_upload";
    else if (!retentionClass) retentionClass = "transient_upload";
    if (!(retentionClass in policies)) retentionClass = "transient_upload";

    const unresolvedCritical = linkedEvents.some((event) => (
        String(event.level || "") === "critical"
        && !event.acknowledged
        && !String(event.resolution || "").trim()
    ));
    const explicitlyProtected = metadata.retention_protected === true;
    const protectedAsset = policies[retentionClass] === null
        || unresolvedCritical
        || explicitlyProtected
        || linkedCareCard
        || linkedAvatar;
    const baseTime = timestamp(asset.created_at || asset.updated_at) || nowMs;
    const retainUntilMs = protectedAsset ? null : baseTime + policies[retentionClass] * DAY_MS;
    let reason = "retention_policy";
    if (policies[retentionClass] === null) reason = "user_managed";
    if (unresolvedCritical) reason = "unresolved_critical_event";
    if (linkedAvatar) reason = "active_avatar";
    if (linkedCareCard) reason = "active_care_card";
    if (explicitlyProtected) reason = "explicitly_protected";
    return {
        retention_class: retentionClass,
        retention_protected: protectedAsset,
        retain_until: retainUntilMs === null ? null : new Date(retainUntilMs).toISOString(),
        expired: retainUntilMs !== null && retainUntilMs <= nowMs,
        reason,
    };
}

function retryAt(nowMs, attemptCount) {
    const delaySeconds = Math.min(6 * 60 * 60, 60 * (2 ** Math.max(0, Math.min(Number(attemptCount) || 1, 9) - 1)));
    return new Date(nowMs + delaySeconds * 1000).toISOString();
}

function localAssetPath(mediaDir, asset) {
    const key = String(asset.relative_path || asset.storage_key || "").replace(/^[/\\]+/, "");
    if (!key) return null;
    const root = path.resolve(mediaDir);
    const candidate = path.resolve(root, key);
    if (candidate !== root && !candidate.startsWith(`${root}${path.sep}`)) {
        throw new Error("media asset path escapes storage root");
    }
    return candidate;
}

async function listLocalFiles(root) {
    const files = [];
    async function visit(directory) {
        let entries = [];
        try {
            entries = await fs.promises.readdir(directory, { withFileTypes: true });
        } catch (error) {
            if (error.code === "ENOENT") return;
            throw error;
        }
        for (const entry of entries) {
            const candidate = path.join(directory, entry.name);
            if (entry.isDirectory()) await visit(candidate);
            else if (entry.isFile()) {
                const stat = await fs.promises.stat(candidate);
                files.push({
                    path: candidate,
                    key: path.relative(root, candidate).split(path.sep).join("/"),
                    size: stat.size,
                    last_modified_ms: stat.mtimeMs,
                });
            }
        }
    }
    await visit(path.resolve(root));
    return files;
}

class MediaLifecycleManager {
    constructor({ store, cosStorage, mediaDir, clock = () => Date.now(), env = process.env, logger = console }) {
        this.store = store;
        this.cosStorage = cosStorage;
        this.mediaDir = path.resolve(mediaDir);
        this.clock = clock;
        this.env = env;
        this.logger = logger;
        this.running = false;
        this.lastRun = null;
    }

    status() {
        return { running: this.running, last_run: this.lastRun, policies: retentionPolicies(this.env) };
    }

    async save() {
        await Promise.resolve(this.store.save());
    }

    async inventory() {
        if (typeof this.store.mediaLifecycleInventory === "function") {
            return this.store.mediaLifecycleInventory();
        }
        return this.store.db;
    }

    async saveAssets(assets) {
        if (typeof this.store.saveMediaLifecycleAssets === "function") {
            await this.store.saveMediaLifecycleAssets(assets);
            return;
        }
        await this.save();
    }

    async deleteAssetObject(asset) {
        const provider = String(asset.storage_provider || "local").toLowerCase();
        if (provider === "cos") {
            if (!this.cosStorage?.enabled) throw new Error("COS storage is not configured");
            await this.cosStorage.deleteObject({ key: String(asset.storage_key || "") });
            return;
        }
        if (provider !== "local" && provider !== "localfs") {
            throw new Error(`unsupported media storage provider: ${provider}`);
        }
        const filePath = localAssetPath(this.mediaDir, asset);
        if (!filePath) return;
        await fs.promises.unlink(filePath).catch((error) => {
            if (error.code !== "ENOENT") throw error;
        });
    }

    async reconcileCosOrphans({ trackedKeys, nowMs, graceMs, dryRun = false }) {
        if (!this.cosStorage?.enabled || typeof this.cosStorage.listObjects !== "function") {
            return { scanned: 0, planned: 0, deleted: 0, failed: 0 };
        }
        let scanned = 0;
        let planned = 0;
        let deleted = 0;
        let failed = 0;
        for (const prefix of MANAGED_COS_PREFIXES) {
            const objects = await this.cosStorage.listObjects({ prefix });
            for (const object of objects) {
                scanned += 1;
                const key = String(object.key || "");
                const modifiedAt = timestamp(object.last_modified);
                if (!key || trackedKeys.has(key) || !modifiedAt || nowMs - modifiedAt < graceMs) continue;
                planned += 1;
                if (dryRun) continue;
                try {
                    await this.cosStorage.deleteObject({ key });
                    deleted += 1;
                } catch (error) {
                    failed += 1;
                    this.logger.warn?.(`COS orphan cleanup failed for ${key}: ${error.code || error.message}`);
                }
            }
        }
        return { scanned, planned, deleted, failed };
    }

    async reconcileLocalOrphans({ trackedKeys, nowMs, graceMs, dryRun = false }) {
        const files = await listLocalFiles(this.mediaDir);
        let planned = 0;
        let deleted = 0;
        let failed = 0;
        for (const file of files) {
            if (trackedKeys.has(file.key) || nowMs - file.last_modified_ms < graceMs) continue;
            planned += 1;
            if (dryRun) continue;
            try {
                await fs.promises.unlink(file.path);
                deleted += 1;
            } catch (error) {
                failed += 1;
                this.logger.warn?.(`Local media orphan cleanup failed for ${file.key}: ${error.message}`);
            }
        }
        return { scanned: files.length, planned, deleted, failed };
    }

    async run({ reconcileOrphans = true, dryRun = false, classificationOnly = false } = {}) {
        if (this.running) return { ok: false, running: true, reason: "already_running" };
        this.running = true;
        const nowMs = Number(this.clock());
        const policies = retentionPolicies(this.env);
        const result = {
            ok: true,
            running: false,
            scanned: 0,
            classified: 0,
            planned_deletions: 0,
            deleted: 0,
            failed: 0,
            protected: 0,
            deferred: 0,
            dry_run: Boolean(dryRun),
            classification_only: Boolean(classificationOnly),
            cos_orphans: { scanned: 0, planned: 0, deleted: 0, failed: 0 },
            local_orphans: { scanned: 0, planned: 0, deleted: 0, failed: 0 },
            started_at: new Date(nowMs).toISOString(),
        };
        try {
            const db = await this.inventory();
            const references = buildAssetReferences(db);
            const classificationChanges = new Map();
            for (const asset of db.assets || []) {
                result.scanned += 1;
                if (String(asset.retention_status || "active") === "deleted") continue;
                const classification = classifyAsset(asset, references, policies, nowMs);
                const changed = asset.retention_class !== classification.retention_class
                    || asset.retain_until !== classification.retain_until
                    || asset.retention_reason !== classification.reason
                    || !asset.retention_status;
                if (changed) result.classified += 1;
                if (!dryRun) {
                    asset.retention_class = classification.retention_class;
                    asset.retain_until = classification.retain_until;
                    asset.retention_reason = classification.reason;
                    asset.retention_status = String(asset.retention_status || "active");
                    if (changed) classificationChanges.set(String(asset.id), asset);
                }
                if (classification.retention_protected) {
                    if (!dryRun && asset.retention_status !== "active") {
                        asset.retention_status = "active";
                        asset.deletion_error = "";
                        asset.next_deletion_at = null;
                        result.classified += 1;
                        classificationChanges.set(String(asset.id), asset);
                    }
                    result.protected += 1;
                    continue;
                }
                if (!classification.expired) continue;
                const nextAttemptMs = timestamp(asset.next_deletion_at);
                if (nextAttemptMs && nextAttemptMs > nowMs) {
                    result.deferred += 1;
                    continue;
                }
                result.planned_deletions += 1;
                if (dryRun || classificationOnly) continue;
                const attempts = Number(asset.deletion_attempts || 0) + 1;
                asset.retention_status = "deleting";
                asset.deletion_attempts = attempts;
                asset.deletion_error = "";
                asset.updated_at = new Date(nowMs).toISOString();
                await this.saveAssets([asset]);
                classificationChanges.delete(String(asset.id));
                try {
                    await this.deleteAssetObject(asset);
                    asset.retention_status = "deleted";
                    asset.deleted_at = new Date(nowMs).toISOString();
                    asset.deletion_error = "";
                    asset.next_deletion_at = null;
                    asset.size = 0;
                    asset.updated_at = new Date(nowMs).toISOString();
                    result.deleted += 1;
                } catch (error) {
                    asset.retention_status = "failed";
                    asset.deletion_error = String(error.message || error).slice(0, 1000);
                    asset.next_deletion_at = retryAt(nowMs, attempts);
                    asset.updated_at = new Date(nowMs).toISOString();
                    result.failed += 1;
                }
                await this.saveAssets([asset]);
            }

            if (!dryRun && classificationChanges.size) {
                await this.saveAssets([...classificationChanges.values()]);
            }
            if (reconcileOrphans) {
                const activeAssets = (db.assets || [])
                    .filter((asset) => String(asset.retention_status || "active") !== "deleted");
                const cosTrackedKeys = new Set(
                    activeAssets
                        .filter((asset) => String(asset.storage_provider || "local").toLowerCase() === "cos")
                        .map((asset) => String(asset.storage_key || ""))
                        .filter(Boolean),
                );
                const localTrackedKeys = new Set(
                    activeAssets
                        .filter((asset) => ["local", "localfs"].includes(String(asset.storage_provider || "local").toLowerCase()))
                        .map((asset) => String(asset.relative_path || asset.storage_key || ""))
                        .filter(Boolean),
                );
                for (const intent of db.media_upload_intents || []) {
                    if (intent.object_key) cosTrackedKeys.add(String(intent.object_key));
                }
                const graceMs = positiveDays(this.env.GOHOME_COS_ORPHAN_GRACE_DAYS, 2) * DAY_MS;
                result.cos_orphans = await this.reconcileCosOrphans({
                    trackedKeys: cosTrackedKeys,
                    nowMs,
                    graceMs,
                    dryRun: dryRun || classificationOnly,
                });
                result.local_orphans = await this.reconcileLocalOrphans({
                    trackedKeys: localTrackedKeys,
                    nowMs,
                    graceMs,
                    dryRun: dryRun || classificationOnly,
                });
            }
            result.finished_at = new Date(Number(this.clock())).toISOString();
            result.ok = result.failed === 0
                && result.cos_orphans.failed === 0
                && result.local_orphans.failed === 0;
            this.lastRun = result;
            return result;
        } finally {
            this.running = false;
        }
    }
}

module.exports = {
    COS_PREFIXES,
    DAY_MS,
    MANAGED_COS_PREFIXES,
    MediaLifecycleManager,
    buildAssetReferences,
    classifyAsset,
    retentionPolicies,
};
