"use strict";

const crypto = require("crypto");
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

function positiveInteger(value, fallback, maximum = Number.MAX_SAFE_INTEGER) {
    const number = Number(value);
    if (!Number.isFinite(number) || number <= 0) return fallback;
    return Math.min(maximum, Math.max(1, Math.trunc(number)));
}

function lifecycleLimits(env = process.env) {
    return Object.freeze({
        asset_count: positiveInteger(env.GOHOME_MEDIA_LIFECYCLE_MAX_ASSETS_PER_RUN, 10, 1000),
        asset_bytes: positiveInteger(env.GOHOME_MEDIA_LIFECYCLE_MAX_ASSET_BYTES_PER_RUN, 64 * 1024 * 1024),
        orphan_count: positiveInteger(env.GOHOME_MEDIA_LIFECYCLE_MAX_ORPHANS_PER_RUN, 25, 5000),
        orphan_bytes: positiveInteger(env.GOHOME_MEDIA_LIFECYCLE_MAX_ORPHAN_BYTES_PER_RUN, 64 * 1024 * 1024),
    });
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
    const eventsById = new Map((db.events || []).map((event) => [String(event.id || ""), event]));
    for (const event of db.events || []) {
        for (const assetId of eventAssetIds(event)) {
            const current = events.get(assetId) || [];
            current.push(event);
            events.set(assetId, current);
        }
    }
    for (const relation of db.event_media_assets || []) {
        const assetId = String(relation.asset_id || "");
        const event = eventsById.get(String(relation.event_id || ""));
        if (!assetId || !event) continue;
        const current = events.get(assetId) || [];
        if (!current.some((item) => String(item.id || "") === String(event.id || ""))) current.push(event);
        events.set(assetId, current);
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

function safeError(error) {
    const code = String(error?.code || error?.name || "ERROR").replace(/[^A-Za-z0-9_.-]/g, "").slice(0, 64) || "ERROR";
    const message = String(error?.message || "deletion failed")
        .replace(/https?:\/\/\S+/gi, "[url]")
        .replace(/\b(password|passwd|secret|secret_key|secretid|secret_id|token|authorization)=\S+/gi, "$1=[redacted]")
        .replace(/(?:\/[A-Za-z0-9._~:@%+,-]+){2,}/g, "[path]")
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 900);
    return `${code}: ${message || "deletion failed"}`.slice(0, 1000);
}

function normalizedOrphanKey(provider, value) {
    const key = String(value || "").replace(/\\/g, "/").replace(/^\/+/, "").trim();
    if (!key || key.split("/").includes("..")) {
        throw new Error(`invalid ${provider} orphan storage key`);
    }
    return key;
}

function orphanIdentity(provider, key) {
    return `${provider}\u0000${key}`;
}

function latestLifecycleResult(store) {
    return [...(store?.db?.scheduler_runs || [])]
        .filter((run) => String(run.job_type || "") === "media_lifecycle")
        .sort((first, second) => timestamp(second.updated_at || second.finished_at || second.started_at)
            - timestamp(first.updated_at || first.finished_at || first.started_at))[0]?.result || null;
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

function boundedSelection(items, { maxCount, maxBytes, sizeOf }) {
    const selected = [];
    let selectedBytes = 0;
    let oversized = 0;
    for (const item of items) {
        if (selected.length >= maxCount) break;
        const size = Math.max(0, Number(sizeOf(item) || 0));
        if (selectedBytes + size > maxBytes) {
            oversized += 1;
            continue;
        }
        selected.push(item);
        selectedBytes += size;
    }
    return { selected, selectedBytes, oversized };
}

function reconciliationResult(scanned = 0) {
    return {
        scanned,
        planned: 0,
        planned_bytes: 0,
        selected: 0,
        selected_bytes: 0,
        limited: 0,
        oversized: 0,
        deferred: 0,
        resolved: 0,
        deleted: 0,
        failed: 0,
    };
}

class MediaLifecycleManager {
    constructor({
        store,
        cosStorage,
        mediaDir,
        clock = () => Date.now(),
        env = process.env,
        logger = console,
        deleteLocalFile = (filePath) => fs.promises.unlink(filePath),
    }) {
        this.store = store;
        this.cosStorage = cosStorage;
        this.mediaDir = path.resolve(mediaDir);
        this.clock = clock;
        this.env = env;
        this.logger = logger;
        this.deleteLocalFile = deleteLocalFile;
        this.running = false;
        this.lastRun = latestLifecycleResult(store);
    }

    status() {
        return {
            running: this.running,
            last_run: this.lastRun,
            policies: retentionPolicies(this.env),
            limits: lifecycleLimits(this.env),
        };
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

    async saveOrphans(orphans) {
        if (!orphans.length) return;
        if (typeof this.store.saveMediaLifecycleOrphans === "function") {
            await this.store.saveMediaLifecycleOrphans(orphans);
            return;
        }
        const rows = Array.isArray(this.store.db.media_orphans) ? this.store.db.media_orphans : [];
        const index = new Map(rows.map((item) => [orphanIdentity(item.storage_provider, item.storage_key), item]));
        for (const orphan of orphans) index.set(orphanIdentity(orphan.storage_provider, orphan.storage_key), orphan);
        this.store.db.media_orphans = [...index.values()];
        await this.save();
    }

    async saveRun(result, error = null) {
        const now = new Date(Number(this.clock())).toISOString();
        const run = {
            id: crypto.randomUUID(),
            family_id: null,
            job_type: "media_lifecycle",
            status: result.ok ? "succeeded" : "failed",
            scope: {
                dry_run: Boolean(result.dry_run),
                classification_only: Boolean(result.classification_only),
            },
            result,
            error_message: error ? safeError(error) : "",
            started_at: result.started_at,
            finished_at: result.finished_at || now,
            created_at: result.started_at,
            updated_at: now,
        };
        this.store.db.scheduler_runs = Array.isArray(this.store.db.scheduler_runs) ? this.store.db.scheduler_runs : [];
        this.store.db.scheduler_runs.push(run);
        this.store.db.scheduler_runs = this.store.db.scheduler_runs
            .sort((first, second) => timestamp(first.updated_at || first.started_at) - timestamp(second.updated_at || second.started_at))
            .slice(-500);
        if (typeof this.store.saveSchedulerRun === "function") {
            await this.store.saveSchedulerRun(run, { retention: 500 });
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

    async reconcileOrphans({ provider, inventory, trackedKeys, existing, nowMs, graceMs, limits, dryRun, remove }) {
        const observed = inventory.map((item) => ({
            ...item,
            key: normalizedOrphanKey(provider, item.key),
            size: Math.max(0, Number(item.size || 0)),
            modifiedAt: Math.trunc(Number(item.modifiedAt || 0)),
        }));
        const candidates = observed
            .filter((item) => !trackedKeys.has(item.key) && item.modifiedAt && nowMs - item.modifiedAt >= graceMs)
            .sort((first, second) => first.modifiedAt - second.modifiedAt || first.key.localeCompare(second.key));
        const candidateKeys = new Set(candidates.map((item) => item.key));
        const states = new Map(
            (existing || [])
                .filter((item) => String(item.storage_provider || "") === provider)
                .map((item) => [String(item.storage_key || ""), { ...item }]),
        );
        const changes = new Map();
        let resolved = 0;

        if (!dryRun) {
            for (const state of states.values()) {
                if (candidateKeys.has(state.storage_key) || ["deleted", "resolved"].includes(String(state.status || ""))) continue;
                state.status = "resolved";
                state.resolved_at = new Date(nowMs).toISOString();
                state.next_deletion_at = null;
                state.deletion_error = "";
                state.updated_at = new Date(nowMs).toISOString();
                changes.set(orphanIdentity(provider, state.storage_key), state);
                resolved += 1;
            }
        }

        const due = [];
        let deferred = 0;
        for (const item of candidates) {
            const previous = states.get(item.key);
            const sourceModifiedAt = new Date(item.modifiedAt).toISOString();
            const replaced = previous && timestamp(previous.source_modified_at) !== item.modifiedAt;
            const reset = !previous || replaced || ["deleted", "resolved"].includes(String(previous.status || ""));
            const state = reset ? {
                storage_provider: provider,
                storage_key: item.key,
                size_bytes: item.size,
                source_modified_at: sourceModifiedAt,
                first_seen_at: new Date(nowMs).toISOString(),
                last_seen_at: new Date(nowMs).toISOString(),
                status: "pending",
                deletion_attempts: 0,
                deletion_error: "",
                next_deletion_at: null,
                deleted_at: null,
                resolved_at: null,
                created_at: new Date(nowMs).toISOString(),
                updated_at: new Date(nowMs).toISOString(),
            } : {
                ...previous,
                size_bytes: item.size,
                source_modified_at: sourceModifiedAt,
                last_seen_at: new Date(nowMs).toISOString(),
                resolved_at: null,
                updated_at: new Date(nowMs).toISOString(),
            };
            if (String(state.status || "") === "deleting") {
                state.status = "failed";
                state.deletion_error = "INTERRUPTED: previous deletion did not finish";
                state.next_deletion_at = null;
            }
            if (!dryRun) changes.set(orphanIdentity(provider, item.key), state);
            const nextRetryMs = timestamp(state.next_deletion_at);
            if (nextRetryMs && nextRetryMs > nowMs) {
                deferred += 1;
                continue;
            }
            due.push({ item, state });
        }

        const selection = boundedSelection(due, {
            maxCount: limits.orphan_count,
            maxBytes: limits.orphan_bytes,
            sizeOf: ({ item }) => item.size,
        });
        if (dryRun) {
            return {
                scanned: observed.length,
                planned: candidates.length,
                planned_bytes: candidates.reduce((total, item) => total + item.size, 0),
                selected: selection.selected.length,
                selected_bytes: selection.selectedBytes,
                limited: due.length - selection.selected.length,
                oversized: selection.oversized,
                deferred,
                resolved: 0,
                deleted: 0,
                failed: 0,
            };
        }

        await this.saveOrphans([...changes.values()]);
        const deleting = selection.selected.map(({ state }) => {
            state.status = "deleting";
            state.deletion_attempts = Number(state.deletion_attempts || 0) + 1;
            state.deletion_error = "";
            state.next_deletion_at = null;
            state.updated_at = new Date(nowMs).toISOString();
            return state;
        });
        await this.saveOrphans(deleting);

        let deleted = 0;
        let failed = 0;
        const completed = [];
        for (const { item, state } of selection.selected) {
            try {
                await remove(item);
                state.status = "deleted";
                state.deleted_at = new Date(nowMs).toISOString();
                state.deletion_error = "";
                state.next_deletion_at = null;
                deleted += 1;
            } catch (error) {
                state.status = "failed";
                state.deletion_error = safeError(error);
                state.next_deletion_at = retryAt(nowMs, state.deletion_attempts);
                failed += 1;
                this.logger.warn?.(`${provider} orphan cleanup failed for ${item.key}: ${state.deletion_error}`);
            }
            state.updated_at = new Date(nowMs).toISOString();
            completed.push(state);
        }
        await this.saveOrphans(completed);
        return {
            scanned: observed.length,
            planned: candidates.length,
            planned_bytes: candidates.reduce((total, item) => total + item.size, 0),
            selected: selection.selected.length,
            selected_bytes: selection.selectedBytes,
            limited: due.length - selection.selected.length,
            oversized: selection.oversized,
            deferred,
            resolved,
            deleted,
            failed,
        };
    }

    async reconcileCosOrphans({ trackedKeys, existing, nowMs, graceMs, limits, dryRun = false }) {
        if (!this.cosStorage?.enabled || typeof this.cosStorage.listObjects !== "function") {
            return reconciliationResult();
        }
        const inventory = [];
        for (const prefix of MANAGED_COS_PREFIXES) {
            const objects = await this.cosStorage.listObjects({ prefix });
            for (const object of objects) {
                inventory.push({
                    key: object.key,
                    size: object.size,
                    modifiedAt: timestamp(object.last_modified),
                });
            }
        }
        return this.reconcileOrphans({
            provider: "cos",
            inventory,
            trackedKeys,
            existing,
            nowMs,
            graceMs,
            limits,
            dryRun,
            remove: (object) => this.cosStorage.deleteObject({ key: object.key }),
        });
    }

    async reconcileLocalOrphans({ trackedKeys, existing, nowMs, graceMs, limits, dryRun = false }) {
        const files = await listLocalFiles(this.mediaDir);
        return this.reconcileOrphans({
            provider: "local",
            inventory: files.map((file) => ({
                key: file.key,
                size: file.size,
                modifiedAt: file.last_modified_ms,
                path: file.path,
            })),
            trackedKeys,
            existing,
            nowMs,
            graceMs,
            limits,
            dryRun,
            remove: async (file) => {
                await this.deleteLocalFile(file.path).catch((error) => {
                    if (error.code !== "ENOENT") throw error;
                });
            },
        });
    }

    async run({ reconcileOrphans = true, dryRun = false, classificationOnly = false } = {}) {
        if (this.running) return { ok: false, running: true, reason: "already_running" };
        this.running = true;
        let persistingRun = false;
        const nowMs = Number(this.clock());
        const policies = retentionPolicies(this.env);
        const limits = lifecycleLimits(this.env);
        const result = {
            ok: true,
            running: false,
            scanned: 0,
            classified: 0,
            planned_deletions: 0,
            planned_deletion_bytes: 0,
            selected_deletions: 0,
            selected_deletion_bytes: 0,
            limited_deletions: 0,
            oversized_deletions: 0,
            deleted: 0,
            failed: 0,
            protected: 0,
            deferred: 0,
            dry_run: Boolean(dryRun),
            classification_only: Boolean(classificationOnly),
            limits,
            cos_orphans: reconciliationResult(),
            local_orphans: reconciliationResult(),
            started_at: new Date(nowMs).toISOString(),
        };
        try {
            const db = await this.inventory();
            const references = buildAssetReferences(db);
            const classificationChanges = new Map();
            const dueAssets = [];
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
                dueAssets.push(asset);
            }

            if (!dryRun && classificationChanges.size) {
                await this.saveAssets([...classificationChanges.values()]);
                classificationChanges.clear();
            }

            dueAssets.sort((first, second) => (
                timestamp(first.created_at || first.updated_at) - timestamp(second.created_at || second.updated_at)
                || String(first.id || "").localeCompare(String(second.id || ""))
            ));
            const deletionSelection = boundedSelection(dueAssets, {
                maxCount: limits.asset_count,
                maxBytes: limits.asset_bytes,
                sizeOf: (asset) => asset.size ?? asset.size_bytes,
            });
            result.planned_deletions = dueAssets.length;
            result.planned_deletion_bytes = dueAssets.reduce(
                (total, asset) => total + Math.max(0, Number(asset.size ?? asset.size_bytes ?? 0)),
                0,
            );
            result.selected_deletions = deletionSelection.selected.length;
            result.selected_deletion_bytes = deletionSelection.selectedBytes;
            result.limited_deletions = dueAssets.length - deletionSelection.selected.length;
            result.oversized_deletions = deletionSelection.oversized;

            if (!dryRun && !classificationOnly) {
                for (const asset of deletionSelection.selected) {
                    const attempts = Number(asset.deletion_attempts || 0) + 1;
                    asset.retention_status = "deleting";
                    asset.deletion_attempts = attempts;
                    asset.deletion_error = "";
                    asset.updated_at = new Date(nowMs).toISOString();
                    await this.saveAssets([asset]);
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
                        asset.deletion_error = safeError(error);
                        asset.next_deletion_at = retryAt(nowMs, attempts);
                        asset.updated_at = new Date(nowMs).toISOString();
                        result.failed += 1;
                    }
                    await this.saveAssets([asset]);
                }
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
                    existing: db.media_orphans || [],
                    nowMs,
                    graceMs,
                    limits,
                    dryRun: dryRun || classificationOnly,
                });
                result.local_orphans = await this.reconcileLocalOrphans({
                    trackedKeys: localTrackedKeys,
                    existing: db.media_orphans || [],
                    nowMs,
                    graceMs,
                    limits,
                    dryRun: dryRun || classificationOnly,
                });
            }
            result.finished_at = new Date(Number(this.clock())).toISOString();
            result.ok = result.failed === 0
                && result.cos_orphans.failed === 0
                && result.local_orphans.failed === 0;
            this.lastRun = result;
            persistingRun = true;
            await this.saveRun(result);
            persistingRun = false;
            return result;
        } catch (error) {
            result.ok = false;
            result.finished_at = result.finished_at || new Date(Number(this.clock())).toISOString();
            this.lastRun = result;
            if (!persistingRun) {
                persistingRun = true;
                await this.saveRun(result, error);
                persistingRun = false;
            }
            throw error;
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
    lifecycleLimits,
    retentionPolicies,
};
