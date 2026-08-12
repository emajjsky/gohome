"use strict";

const { dayBoundsShanghai } = require("./activity-reporting");
const { CARE_CARD_CONTRACT_VERSION } = require("../care-card-contract");
const {
    NativeRepository,
    accountExportForDb,
    actionInput,
    activityIntervalInput,
    articlesFromCareCards,
    familyMemberView,
    familyInvitationDurationMinutes,
    familyInvitationView,
    generateFamilyInvitationCode,
    hashFamilyInvitationCode,
    invalidFamilyInvitation,
    normalizeFamilyInvitationCode,
    memoryInput,
    currentHomeNetworkFingerprint,
    repositoryError,
} = require("./repository");

const USER_COLUMNS = "id, email, display_name, phone, status, metadata, created_at, updated_at";
const FAMILY_COLUMNS = "f.id, f.name, f.status, f.timezone, f.metadata, f.created_at, f.updated_at, fm.role, (select count(*)::int from family_members active_members where active_members.family_id = f.id and active_members.status = 'active') as member_count";

function row(result) {
    return result?.rows?.[0] || null;
}

function rows(result) {
    return result?.rows || [];
}

function textId(value) {
    return String(value || "");
}

function arrayValue(value) {
    return Array.isArray(value)
        ? [...new Set(value.map((item) => String(item || "").trim()).filter(Boolean))]
        : [];
}

function limitValue(value, fallback = 50, maximum = 100) {
    const parsed = Number(value);
    if (!Number.isInteger(parsed) || parsed < 1) return fallback;
    return Math.min(parsed, maximum);
}

function dateKeyShanghai(value = new Date()) {
    return new Intl.DateTimeFormat("en-CA", {
        timeZone: "Asia/Shanghai",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
    }).format(value);
}

function accessDenied() {
    return repositoryError("family access denied", 403);
}

function validateMemoryAssets(assets) {
    const videoCount = assets.filter((asset) => String(asset?.content_type || "").startsWith("video/")).length;
    if (videoCount > 1 || (videoCount === 1 && assets.length !== 1)) {
        throw repositoryError("memory media must contain either one video or up to nine images", 400);
    }
}

class PostgresNativeRepository extends NativeRepository {
    constructor(pool, {
        clock = () => new Date(),
        onFamilyMetadataChange = () => {},
        onFamilyMembershipChange = () => {},
        onFamilyInvitationChange = () => {},
        invitationCodeFactory = generateFamilyInvitationCode,
    } = {}) {
        super();
        if (!pool || typeof pool.query !== "function") throw new Error("postgres pool required");
        this.pool = pool;
        this.clock = clock;
        this.onFamilyMetadataChange = onFamilyMetadataChange;
        this.onFamilyMembershipChange = onFamilyMembershipChange;
        this.onFamilyInvitationChange = onFamilyInvitationChange;
        this.invitationCodeFactory = invitationCodeFactory;
    }

    async assertFamilyAccess(client, userId, familyId) {
        const result = await client.query(
            `select 1 from family_members where family_id = $1 and user_id = $2 and status = 'active' limit 1 for share`,
            [textId(familyId), textId(userId)],
        );
        if (!result.rowCount) throw accessDenied();
    }

    async assertFamilyManager(client, userId, familyId) {
        const result = await client.query(
            `select role from family_members
             where family_id = $1 and user_id = $2 and status = 'active'
             limit 1 for share`,
            [textId(familyId), textId(userId)],
        );
        const role = textId(row(result)?.role).toLowerCase();
        if (!["owner", "creator"].includes(role)) {
            throw repositoryError(result.rowCount ? "family management permission required" : "family access denied", 403);
        }
    }

    async accountProfile(userId) {
        const user = row(await this.pool.query(
            `select ${USER_COLUMNS} from users where id = $1 and status = 'active'`,
            [textId(userId)],
        ));
        if (!user) throw repositoryError("user not found", 404);
        return user;
    }

    async updateAccountProfile(userId, input = {}) {
        const current = await this.accountProfile(userId);
        const displayName = String(input.display_name ?? current.display_name ?? "").trim();
        if (!displayName || displayName.length > 40) throw repositoryError("display_name must contain 1 to 40 characters", 400);
        const metadata = current.metadata && typeof current.metadata === "object" ? { ...current.metadata } : {};
        for (const key of ["city", "district"]) {
            if (Object.prototype.hasOwnProperty.call(input, key)) metadata[key] = String(input[key] || "").trim().slice(0, 40);
        }
        if (Object.prototype.hasOwnProperty.call(input, "avatar_asset_id")) {
            const assetId = String(input.avatar_asset_id || "").trim();
            if (assetId) {
                const asset = row(await this.pool.query(
                    `select a.id
                     from media_assets a
                     where a.id = $1
                       and a.content_type like 'image/%'
                       and exists (
                           select 1 from family_members fm
                           where fm.family_id = a.family_id and fm.user_id = $2 and fm.status = 'active'
                       )`,
                    [assetId, textId(userId)],
                ));
                if (!asset) throw repositoryError("avatar image is unavailable", 400);
            }
            metadata.avatar_asset_id = assetId;
        }
        return row(await this.pool.query(
            `update users set display_name = $2, metadata = $3::jsonb, updated_at = now()
             where id = $1 and status = 'active'
             returning ${USER_COLUMNS}`,
            [textId(userId), displayName, JSON.stringify(metadata)],
        ));
    }

    async bootstrapForUser(userId) {
        const userResult = await this.pool.query(
            `select ${USER_COLUMNS} from users where id = $1 and status = 'active'`,
            [textId(userId)],
        );
        const user = row(userResult);
        if (!user) throw repositoryError("user not found", 404);
        const familiesResult = await this.pool.query(
            `select ${FAMILY_COLUMNS}
             from family_members fm
             join families f on f.id = fm.family_id
             where fm.user_id = $1 and fm.status = 'active' and f.status = 'active'
             order by f.created_at asc`,
            [textId(userId)],
        );
        const families = rows(familiesResult);
        for (const family of families) family.member_count = Number(family.member_count || 0);
        const activeFamilyId = families[0]?.id || null;
        let onboarding = { next_step: "family", complete: false };
        if (activeFamilyId) onboarding = await this.onboardingForFamily(userId, activeFamilyId);
        const unread = activeFamilyId
            ? await this.pool.query(
                `select count(*)::int as count from app_messages
                 where family_id = $1 and read_at is null and status <> 'dismissed'`,
                [activeFamilyId],
            )
            : { rows: [{ count: 0 }] };
        return {
            user,
            families,
            active_family_id: activeFamilyId,
            onboarding,
            unread_count: Number(row(unread)?.count || 0),
            revision: new Date(this.clock()).toISOString(),
        };
    }

    async familyMembers(userId, familyId) {
        await this.assertFamilyAccess(this.pool, userId, familyId);
        const result = await this.pool.query(
            `select fm.*, u.email, u.phone, u.display_name
             from family_members fm join users u on u.id = fm.user_id
             where fm.family_id = $1 and fm.status = 'active' and u.status = 'active'
             order by case when fm.role in ('owner', 'creator') then 0 else 1 end, fm.joined_at asc, fm.created_at asc`,
            [textId(familyId)],
        );
        return rows(result).map((member) => familyMemberView(member, member, userId));
    }

    async removeFamilyMember(userId, familyId, memberId) {
        const client = await this.pool.connect();
        let transaction = false;
        try {
            await client.query("begin");
            transaction = true;
            await client.query(`select id from families where id = $1 for update`, [textId(familyId)]);
            await this.assertFamilyManager(client, userId, familyId);
            const member = row(await client.query(
                `select * from family_members where id = $1 and family_id = $2 and status = 'active' for update`,
                [textId(memberId), textId(familyId)],
            ));
            if (!member) throw repositoryError("family member not found", 404);
            if (textId(member.user_id) === textId(userId)) throw repositoryError("creator cannot remove self", 409);
            if (["owner", "creator"].includes(textId(member.role).toLowerCase())) throw repositoryError("family creator cannot be removed", 409);
            const updated = row(await client.query(
                `update family_members set status = 'removed', updated_at = now() where id = $1 returning *`,
                [textId(memberId)],
            ));
            await client.query("commit");
            transaction = false;
            this.onFamilyMembershipChange({ family_id: textId(familyId), memberships: [updated] });
            return { removed: true, member_id: textId(memberId), family_id: textId(familyId) };
        } catch (error) {
            if (transaction) await client.query("rollback");
            throw error;
        } finally {
            client.release();
        }
    }

    async leaveFamily(userId, familyId) {
        const client = await this.pool.connect();
        let transaction = false;
        try {
            await client.query("begin");
            transaction = true;
            await client.query(`select id from families where id = $1 for update`, [textId(familyId)]);
            const member = row(await client.query(
                `select * from family_members where family_id = $1 and user_id = $2 and status = 'active' for update`,
                [textId(familyId), textId(userId)],
            ));
            if (!member) throw accessDenied();
            if (["owner", "creator"].includes(textId(member.role).toLowerCase())) throw repositoryError("transfer family ownership before leaving", 409);
            const updated = row(await client.query(`update family_members set status = 'left', updated_at = now() where id = $1 returning *`, [textId(member.id)]));
            await client.query("commit");
            transaction = false;
            this.onFamilyMembershipChange({ family_id: textId(familyId), memberships: [updated] });
            return { left: true, family_id: textId(familyId) };
        } catch (error) {
            if (transaction) await client.query("rollback");
            throw error;
        } finally {
            client.release();
        }
    }

    async transferFamilyOwnership(userId, familyId, targetMemberId, input = {}) {
        if (String(input.confirmation || "") !== "TRANSFER_OWNERSHIP") throw repositoryError("ownership transfer confirmation required", 400);
        const client = await this.pool.connect();
        let transaction = false;
        try {
            await client.query("begin");
            transaction = true;
            const family = row(await client.query(`select id from families where id = $1 and status = 'active' for update`, [textId(familyId)]));
            if (!family) throw repositoryError("family not found", 404);
            const memberships = rows(await client.query(`select * from family_members where family_id = $1 and status = 'active' order by id for update`, [textId(familyId)]));
            const current = memberships.find((member) => textId(member.user_id) === textId(userId));
            if (!current || !["owner", "creator"].includes(textId(current.role).toLowerCase())) throw repositoryError("family management permission required", 403);
            const target = memberships.find((member) => textId(member.id) === textId(targetMemberId));
            if (!target) throw repositoryError("family member not found", 404);
            if (textId(target.user_id) === textId(userId)) throw repositoryError("select another family member", 400);
            const previous = rows(await client.query(
                `update family_members set role = 'member', updated_at = now()
                 where family_id = $1 and status = 'active' and id <> $2 and role in ('owner', 'creator')
                 returning *`,
                [textId(familyId), textId(target.id)],
            ));
            const next = row(await client.query(`update family_members set role = 'owner', updated_at = now() where id = $1 returning *`, [textId(target.id)]));
            await client.query(
                `update families set metadata = coalesce(metadata, '{}'::jsonb) || jsonb_build_object('created_by_user_id', $2::text), updated_at = now() where id = $1`,
                [textId(familyId), textId(target.user_id)],
            );
            await client.query("commit");
            transaction = false;
            this.onFamilyMembershipChange({ family_id: textId(familyId), created_by_user_id: textId(target.user_id), memberships: [...previous, next].filter(Boolean) });
            return { transferred: true, family_id: textId(familyId), new_owner_member_id: textId(target.id), new_owner_user_id: textId(target.user_id) };
        } catch (error) {
            if (transaction) await client.query("rollback");
            throw error;
        } finally {
            client.release();
        }
    }

    async familyInvitations(userId, familyId) {
        await this.assertFamilyManager(this.pool, userId, familyId);
        const result = await this.pool.query(
            `select id, family_id, code_hint, status, expires_at, used_at, revoked_at, created_at
             from family_invitations where family_id = $1 order by created_at desc limit 20`,
            [textId(familyId)],
        );
        const now = new Date(this.clock()).getTime();
        return rows(result).map((invitation) => familyInvitationView(invitation, now));
    }

    async createFamilyInvitation(userId, familyId, input = {}) {
        let code = "";
        let codeHash = "";
        for (let attempt = 0; attempt < 5; attempt += 1) {
            code = normalizeFamilyInvitationCode(this.invitationCodeFactory());
            codeHash = hashFamilyInvitationCode(code);
            if (codeHash) break;
        }
        if (!codeHash) throw repositoryError("could not create invitation", 503);
        const now = new Date(this.clock());
        const expiresAt = new Date(now.getTime() + familyInvitationDurationMinutes(input.expires_in_minutes) * 60 * 1000);
        const client = await this.pool.connect();
        let transaction = false;
        try {
            await client.query("begin");
            transaction = true;
            const family = row(await client.query(`select id from families where id = $1 and status = 'active' for update`, [textId(familyId)]));
            if (!family) throw repositoryError("family not found", 404);
            await this.assertFamilyManager(client, userId, familyId);
            const revoked = rows(await client.query(
                `update family_invitations
                 set status = 'revoked', revoked_at = $2, updated_at = $2
                 where family_id = $1 and status = 'active'
                 returning *`,
                [textId(familyId), now],
            ));
            const invitation = row(await client.query(
                `insert into family_invitations
                    (family_id, code_hash, code_hint, created_by_user_id, status, expires_at, created_at, updated_at)
                 values ($1, $2, $3, $4, 'active', $5, $6, $6)
                 returning *`,
                [textId(familyId), codeHash, code.slice(-4), textId(userId), expiresAt, now],
            ));
            await client.query("commit");
            transaction = false;
            this.onFamilyInvitationChange({ invitations: [...revoked, invitation] });
            return { ...familyInvitationView(invitation, now.getTime()), code };
        } catch (error) {
            if (transaction) await client.query("rollback");
            if (error?.code === "23505") throw repositoryError("could not create invitation", 503);
            throw error;
        } finally {
            client.release();
        }
    }

    async revokeFamilyInvitation(userId, familyId, invitationId) {
        const client = await this.pool.connect();
        let transaction = false;
        try {
            await client.query("begin");
            transaction = true;
            await client.query(`select id from families where id = $1 for update`, [textId(familyId)]);
            await this.assertFamilyManager(client, userId, familyId);
            const existing = row(await client.query(
                `select * from family_invitations where id = $1 and family_id = $2 for update`,
                [textId(invitationId), textId(familyId)],
            ));
            if (!existing) throw repositoryError("invitation not found", 404);
            const invitation = String(existing.status || "active") === "active"
                ? row(await client.query(
                    `update family_invitations set status = 'revoked', revoked_at = now(), updated_at = now() where id = $1 returning *`,
                    [textId(invitationId)],
                ))
                : existing;
            await client.query("commit");
            transaction = false;
            this.onFamilyInvitationChange({ invitations: [invitation] });
            return familyInvitationView(invitation, new Date(this.clock()).getTime());
        } catch (error) {
            if (transaction) await client.query("rollback");
            throw error;
        } finally {
            client.release();
        }
    }

    async consumeFamilyInvitation(userId, rawCode) {
        const codeHash = hashFamilyInvitationCode(rawCode);
        if (!codeHash) throw invalidFamilyInvitation();
        const client = await this.pool.connect();
        let transaction = false;
        try {
            await client.query("begin");
            transaction = true;
            const invitation = row(await client.query(
                `select * from family_invitations where code_hash = $1 for update`,
                [codeHash],
            ));
            if (!invitation || String(invitation.status || "active") !== "active") throw invalidFamilyInvitation();
            const now = new Date(this.clock());
            if (new Date(invitation.expires_at).getTime() <= now.getTime()) {
                const expired = row(await client.query(
                    `update family_invitations set status = 'expired', updated_at = $2 where id = $1 returning *`,
                    [textId(invitation.id), now],
                ));
                await client.query("commit");
                transaction = false;
                this.onFamilyInvitationChange({ invitations: [expired] });
                throw invalidFamilyInvitation();
            }
            const family = row(await client.query(
                `select id, name from families where id = $1 and status = 'active' for share`,
                [textId(invitation.family_id)],
            ));
            if (!family) throw invalidFamilyInvitation();
            const existing = row(await client.query(
                `select * from family_members where family_id = $1 and user_id = $2 for update`,
                [textId(invitation.family_id), textId(userId)],
            ));
            if (existing && String(existing.status || "active") === "active") {
                throw repositoryError("你已经加入这个家庭。", 409);
            }
            const membership = existing
                ? row(await client.query(
                    `update family_members
                     set role = 'member', status = 'active', invited_by = $2, joined_at = $3, updated_at = $3
                     where id = $1 returning *`,
                    [textId(existing.id), invitation.created_by_user_id || null, now],
                ))
                : row(await client.query(
                    `insert into family_members (family_id, user_id, role, status, invited_by, joined_at, created_at, updated_at)
                     values ($1, $2, 'member', 'active', $3, $4, $4, $4) returning *`,
                    [textId(invitation.family_id), textId(userId), invitation.created_by_user_id || null, now],
                ));
            const used = row(await client.query(
                `update family_invitations
                 set status = 'used', used_by_user_id = $2, used_at = $3, updated_at = $3
                 where id = $1 and status = 'active' returning *`,
                [textId(invitation.id), textId(userId), now],
            ));
            if (!used) throw invalidFamilyInvitation();
            const count = row(await client.query(
                `select count(*)::int as count from family_members where family_id = $1 and status = 'active'`,
                [textId(invitation.family_id)],
            ));
            await client.query("commit");
            transaction = false;
            this.onFamilyMembershipChange({ family_id: textId(invitation.family_id), memberships: [membership] });
            this.onFamilyInvitationChange({ invitations: [used] });
            return {
                joined: true,
                family: { id: textId(family.id), name: String(family.name || "家庭"), member_count: Number(count?.count || 1) },
            };
        } catch (error) {
            if (transaction) await client.query("rollback");
            throw error;
        } finally {
            client.release();
        }
    }

    async accountExport(userId) {
        const client = typeof this.pool.connect === "function" ? await this.pool.connect() : this.pool;
        let transaction = false;
        try {
            await client.query("begin isolation level repeatable read read only");
            transaction = true;
            const account = row(await client.query(`select ${USER_COLUMNS} from users where id = $1 and status = 'active'`, [textId(userId)]));
            if (!account) throw repositoryError("user not found", 404);
            const memberships = rows(await client.query(
                `select fm.*, f.name, f.status as family_status, f.timezone, f.metadata as family_metadata,
                        f.created_at as family_created_at, f.updated_at as family_updated_at
                 from family_members fm
                 join families f on f.id = fm.family_id
                 where fm.user_id = $1 and fm.status = 'active' and f.status = 'active'
                 order by f.created_at`,
                [textId(userId)],
            ));
            const familyIds = memberships.map((item) => textId(item.family_id));
            const db = {
                users: [account], families: [], family_members: memberships,
                elder_profiles: {}, devices: {}, device_bindings: [], cameras: {}, family_rules: {}, care_preferences: {},
                calendar_events: [], events: [], assets: [], family_memories: [], family_memory_media: [],
                family_memory_comments: [], family_memory_favorites: [], activity_intervals: [], care_cards: [],
                app_messages: [], app_message_actions: [], home_visits: [], home_return_plans: [],
            };
            for (const membership of memberships) {
                db.families.push({
                    id: membership.family_id,
                    name: membership.name,
                    status: membership.family_status,
                    timezone: membership.timezone,
                    metadata: membership.family_metadata,
                    created_at: membership.family_created_at,
                    updated_at: membership.family_updated_at,
                });
            }
            if (familyIds.length) {
                const familyValues = [familyIds];
                const familyMembers = rows(await client.query(
                    `select * from family_members where family_id::text = any($1::text[]) and status = 'active'`,
                    familyValues,
                ));
                db.family_members = familyMembers;
                const memberUserIds = [...new Set(familyMembers.map((item) => textId(item.user_id)))];
                db.users = rows(await client.query(
                    `select ${USER_COLUMNS} from users where id::text = any($1::text[])`,
                    [memberUserIds],
                ));
                const collections = await Promise.all([
                    client.query(`select * from elder_profiles where family_id::text = any($1::text[])`, familyValues),
                    client.query(`select device_id, family_id, name, device_type, status, app_version, model_version, last_seen_at, created_at, updated_at from devices where family_id::text = any($1::text[])`, familyValues),
                    client.query(`select id, family_id, device_id, device_name, status, bound_at, last_seen_at, created_at from device_bindings where family_id::text = any($1::text[])`, familyValues),
                    client.query(`select id, family_id, device_id, name, room, enabled, status, sync_status, created_at, updated_at from cameras where family_id::text = any($1::text[])`, familyValues),
                    client.query(`select family_id, config, updated_at from care_rules where family_id::text = any($1::text[]) and camera_id is null and rule_type = 'edge_rules' and enabled = true`, familyValues),
                    client.query(`select * from care_preferences where family_id::text = any($1::text[])`, familyValues),
                    client.query(`select * from calendar_events where family_id::text = any($1::text[]) order by starts_at`, familyValues),
                    client.query(`select * from home_visits where family_id::text = any($1::text[]) and user_id = $2 order by verified_at`, [familyIds, textId(userId)]),
                    client.query(`select * from home_return_plans where family_id::text = any($1::text[]) and user_id = $2`, [familyIds, textId(userId)]),
                    client.query(`select id, family_id, camera_id, media_asset_id, event_type, level, summary, room, camera_name, acknowledged, resolution, payload, occurred_at, created_at, updated_at from events where family_id::text = any($1::text[]) order by occurred_at`, familyValues),
                    client.query(`select id, family_id, device_id, camera_id, content_type, size_bytes, metadata, created_at from media_assets where family_id::text = any($1::text[]) order by created_at`, familyValues),
                    client.query(`select * from family_memories where family_id::text = any($1::text[]) order by happened_at`, familyValues),
                    client.query(`select * from family_memory_media where family_id::text = any($1::text[]) order by memory_id, sort_order`, familyValues),
                    client.query(`select * from family_memory_comments where family_id::text = any($1::text[]) order by created_at`, familyValues),
                    client.query(`select * from family_memory_favorites where family_id::text = any($1::text[]) order by created_at`, familyValues),
                    client.query(`select * from activity_intervals where family_id::text = any($1::text[]) order by started_at`, familyValues),
                    client.query(`select id, family_id, card_date, card_type, title, body, facts, status, created_at from care_cards where family_id::text = any($1::text[]) order by card_date`, familyValues),
                    client.query(`select id, message_id, family_id, user_id, message_type, title, subtitle, body, facts, status, created_at from app_messages where family_id::text = any($1::text[]) order by created_at`, familyValues),
                    client.query(`select id, family_id, message_id, user_id, action_type, payload, created_at from app_message_actions where family_id::text = any($1::text[]) order by created_at`, familyValues),
                ]);
                const [profiles, devices, bindings, cameras, rules, preferences, calendar, visits, returnPlans, events, assets, memories, media, comments, favorites, activity, cards, messages, actions] = collections.map(rows);
                db.elder_profiles = Object.fromEntries(profiles.map((item) => [textId(item.id), item]));
                db.devices = Object.fromEntries(devices.map((item) => [textId(item.device_id), item]));
                db.device_bindings = bindings;
                db.cameras = Object.fromEntries(cameras.map((item) => [textId(item.id), item]));
                db.family_rules = Object.fromEntries(rules.map((item) => [textId(item.family_id), { ...(item.config || {}), updated_at: item.updated_at }]));
                db.care_preferences = Object.fromEntries(preferences.map((item) => [textId(item.family_id), item]));
                db.calendar_events = calendar;
                db.home_visits = visits;
                db.home_return_plans = returnPlans;
                db.events = events;
                db.assets = assets;
                db.family_memories = memories;
                db.family_memory_media = media;
                db.family_memory_comments = comments;
                db.family_memory_favorites = favorites;
                db.activity_intervals = activity;
                db.care_cards = cards;
                db.app_messages = messages;
                db.app_message_actions = actions;
            }
            await client.query("commit");
            transaction = false;
            return accountExportForDb(db, userId, new Date(this.clock()).toISOString());
        } catch (error) {
            if (transaction) await client.query("rollback");
            throw error;
        } finally {
            if (client !== this.pool && typeof client.release === "function") client.release();
        }
    }

    async accountDeletionPlan(userId) {
        return this.accountDeletionPlanWithClient(this.pool, userId, false);
    }

    async accountDeletionPlanWithClient(client, userId, lock = false) {
        const account = row(await client.query(
            `select id from users where id = $1 and status = 'active'${lock ? " for update" : ""}`,
            [textId(userId)],
        ));
        if (!account) throw repositoryError("user not found", 404);
        if (lock) {
            const lockedMemberships = rows(await client.query(
                `select id, family_id from family_members where user_id = $1 and status = 'active' for update`,
                [textId(userId)],
            ));
            const lockedFamilyIds = lockedMemberships.map((item) => textId(item.family_id));
            if (lockedFamilyIds.length) {
                await client.query(`select id from families where id::text = any($1::text[]) for update`, [lockedFamilyIds]);
            }
        }
        const memberships = rows(await client.query(
            `select fm.family_id, fm.role, f.name,
                    (select count(*)::int from family_members members where members.family_id = fm.family_id and members.status = 'active') as active_member_count
             from family_members fm join families f on f.id = fm.family_id
             where fm.user_id = $1 and fm.status = 'active'
             order by f.created_at`,
            [textId(userId)],
        ));
        const families = memberships.map((item) => {
            const ownsFamily = ["owner", "creator"].includes(textId(item.role).toLowerCase());
            const memberCount = Number(item.active_member_count || 0);
            return {
                id: textId(item.family_id),
                name: String(item.name || "家庭"),
                role: String(item.role || "member"),
                owns_family: ownsFamily,
                active_member_count: memberCount,
                action: ownsFamily ? (memberCount > 1 ? "transfer_ownership" : "delete_family") : "leave_family",
            };
        });
        const blockers = families.filter((item) => item.action === "transfer_ownership").map((item) => ({
            code: "ownership_transfer_required",
            family_id: item.id,
            family_name: item.name,
            message: `请先为“${item.name}”转交家庭创建者身份`,
        }));
        const authored = row(await client.query(`select count(*)::int as count from family_memories where author_user_id = $1`, [textId(userId)]));
        return {
            can_delete: blockers.length === 0,
            requires_ownership_transfer: blockers.length > 0,
            families,
            blockers,
            deletion_scope: {
                families_to_delete: families.filter((item) => item.action === "delete_family").map((item) => item.id),
                memberships_to_leave: families.filter((item) => item.action === "leave_family").map((item) => item.id),
                authored_memories: Number(authored?.count || 0),
            },
            retention_note: "账号、登录凭证、推送标识和可删除内容将被移除；依法必须保留的安全审计会解除账号关联后按期限留存。",
        };
    }

    async deleteAccount(userId, input = {}) {
        if (String(input.confirmation || "") !== "DELETE_ACCOUNT") {
            throw repositoryError("account deletion confirmation required", 400);
        }
        const client = typeof this.pool.connect === "function" ? await this.pool.connect() : this.pool;
        let transaction = false;
        try {
            await client.query("begin");
            transaction = true;
            const plan = await this.accountDeletionPlanWithClient(client, userId, true);
            if (!plan.can_delete) throw repositoryError("family ownership transfer required", 409);
            const familyIds = plan.deletion_scope.families_to_delete;
            const deviceIds = rows(await client.query(
                `select device_id from devices where family_id::text = any($1::text[]) for update`,
                [familyIds],
            )).map((item) => textId(item.device_id));
            const cleanupAssets = rows(await client.query(
                `select distinct a.id
                 from media_assets a
                 left join family_memory_media mm on mm.asset_id = a.id
                 left join family_memories m on m.id = mm.memory_id
                 where a.family_id::text = any($1::text[])
                    or (m.author_user_id = $2 and not exists (
                        select 1 from family_memory_media retained_mm
                        join family_memories retained_m on retained_m.id = retained_mm.memory_id
                        where retained_mm.asset_id = a.id
                          and retained_m.author_user_id <> $2
                          and not (retained_m.family_id::text = any($1::text[]))
                    ))`,
                [familyIds, textId(userId)],
            )).map((item) => textId(item.id));
            const cleanupObjects = rows(await client.query(
                `select distinct object_key from media_upload_intents
                 where user_id = $1 or family_id::text = any($2::text[])`,
                [textId(userId), familyIds],
            )).map((item) => ({ storage_provider: "cos", storage_key: String(item.object_key || "") })).filter((item) => item.storage_key);

            if (familyIds.length) {
                await client.query(`delete from events where family_id::text = any($1::text[])`, [familyIds]);
                await client.query(`delete from scheduler_runs where family_id::text = any($1::text[])`, [familyIds]);
                await client.query(`delete from device_config_versions where family_id::text = any($1::text[]) or device_id::text = any($2::text[])`, [familyIds, deviceIds]);
                await client.query(`delete from audit_logs where family_id::text = any($1::text[])`, [familyIds]);
                if (deviceIds.length) await client.query(`delete from device_heartbeats where device_id::text = any($1::text[])`, [deviceIds]);
                await client.query(`delete from families where id::text = any($1::text[])`, [familyIds]);
            }
            await client.query(`delete from family_memory_comments where author_user_id = $1`, [textId(userId)]);
            await client.query(`delete from family_memories where author_user_id = $1`, [textId(userId)]);
            await client.query(`delete from family_memory_favorites where user_id = $1`, [textId(userId)]);
            await client.query(`delete from app_message_actions where user_id = $1`, [textId(userId)]);
            await client.query(`delete from home_visits where user_id = $1`, [textId(userId)]);
            await client.query(`delete from home_return_plans where user_id = $1`, [textId(userId)]);
            await client.query(`delete from notification_deliveries where user_id = $1`, [textId(userId)]);
            await client.query(`delete from app_messages where user_id = $1`, [textId(userId)]);
            await client.query(`delete from app_push_tokens where user_id = $1`, [textId(userId)]);
            await client.query(`delete from users where id = $1`, [textId(userId)]);
            await client.query("commit");
            transaction = false;
            return {
                deleted: true,
                deleted_user_id: textId(userId),
                deleted_family_ids: familyIds,
                cleanup_all_asset_ids: cleanupAssets,
                cleanup_storage_objects: cleanupObjects,
            };
        } catch (error) {
            if (transaction) await client.query("rollback");
            throw error;
        } finally {
            if (client !== this.pool && typeof client.release === "function") client.release();
        }
    }

    async onboardingForFamily(userId, familyId) {
        await this.assertFamilyAccess(this.pool, userId, familyId);
        const result = await this.pool.query(
            `select
                coalesce(f.metadata->>'onboarding_completed_at', '') as onboarding_completed_at,
                exists(select 1 from elder_profiles where family_id = $1) as has_profile,
                exists(select 1 from devices where family_id = $1 and status <> 'revoked') as has_device,
                exists(select 1 from cameras where family_id = $1 and status <> 'deleted') as has_camera,
                exists(select 1 from events where family_id = $1) as has_camera_history
             from families f
             where f.id = $1`,
            [textId(familyId)],
        );
        const state = row(result) || {};
        if (textId(state.onboarding_completed_at)) {
            return { next_step: "complete", complete: true };
        }
        if (state.has_profile && ((state.has_device && state.has_camera) || state.has_camera_history)) {
            const completedAt = new Date(this.clock()).toISOString();
            await this.pool.query(
                `update families
                 set metadata = coalesce(metadata, '{}'::jsonb) || jsonb_build_object('onboarding_completed_at', $2::text),
                     updated_at = now()
                 where id = $1 and coalesce(metadata->>'onboarding_completed_at', '') = ''`,
                [textId(familyId), completedAt],
            );
            this.onFamilyMetadataChange(textId(familyId), { onboarding_completed_at: completedAt });
            return { next_step: "complete", complete: true };
        }
        const nextStep = !state.has_profile ? "profile" : !state.has_device ? "device" : !state.has_camera ? "camera" : "complete";
        return { next_step: nextStep, complete: nextStep === "complete" };
    }

    async homeForFamily(userId, familyId) {
        await this.assertFamilyAccess(this.pool, userId, familyId);
        const id = textId(familyId);
        const [familyResult, elderResult, camerasResult, calendarResult, eventsResult, articleResult, careCardResult, careMessageResult, deviceResult, carePreferencesResult, homeVisitResult, returnPlanResult] = await Promise.all([
            this.pool.query(`select ${FAMILY_COLUMNS} from family_members fm join families f on f.id = fm.family_id where fm.user_id = $1 and fm.family_id = $2 and fm.status = 'active'`, [textId(userId), id]),
            this.pool.query(`select * from elder_profiles where family_id = $1 order by created_at asc limit 1`, [id]),
            this.pool.query(`select * from cameras where family_id = $1 order by created_at asc`, [id]),
            this.pool.query(`select * from calendar_events where family_id = $1 order by starts_at asc limit 20`, [id]),
            this.pool.query(`select * from events where family_id = $1 and acknowledged = false order by occurred_at desc limit 20`, [id]),
            this.pool.query(`select * from content_recommendations where (family_id = $1 or family_id is null) and status = 'published' order by created_at desc limit 30`, [id]),
            this.pool.query(`select family_id, card_date, updated_at, content_recommendations from care_cards where family_id = $1 and jsonb_array_length(content_recommendations) > 0 order by card_date desc limit 14`, [id]),
            this.pool.query(
                `select * from app_messages
                 where family_id = $1
                   and message_type in ('activity_insight', 'return_home', 'care_card')
                   and status = 'open'
                   and (message_type <> 'care_card' or (
                       message_id = 'care-daily-' || $1 || '-' || to_char(now() at time zone 'Asia/Shanghai', 'YYYY-MM-DD')
                       and metadata->>'care_contract_version' = $2
                   ))
                   and (
                       nullif(metadata->>'snoozed_until', '') is null
                       or (metadata->>'snoozed_until')::timestamptz <= now()
                   )
                 order by case message_type when 'activity_insight' then 0 when 'return_home' then 1 else 2 end, created_at desc
                 limit 1`,
                [id, CARE_CARD_CONTRACT_VERSION],
            ),
            this.pool.query(`select * from devices where family_id = $1 and status <> 'revoked' order by last_seen_at desc nulls last limit 1`, [id]),
            this.pool.query(`select metadata from care_preferences where family_id = $1`, [id]),
            this.pool.query(`select * from home_visits where family_id = $1 and user_id = $2 order by verified_at desc limit 1`, [id, textId(userId)]),
            this.pool.query(`select * from home_return_plans where family_id = $1 and user_id = $2 and status = 'planned' limit 1`, [id, textId(userId)]),
        ]);
        const events = rows(eventsResult);
        const publishedArticles = rows(articleResult);
        const cardArticles = articlesFromCareCards(rows(careCardResult), id);
        const seenArticleKeys = new Set();
        const articles = [...publishedArticles, ...cardArticles].filter((article) => {
            const key = String(article.url || article.source_url || article.id || "").trim();
            if (!key || seenArticleKeys.has(key)) return false;
            seenArticleKeys.add(key);
            return true;
        }).slice(0, 30);
        return {
            family: row(familyResult),
            elder: row(elderResult),
            cameras: rows(camerasResult),
            calendar: rows(calendarResult),
            critical_alert: events.find((event) => (
                ["critical", "emergency"].includes(event.level)
                && event.payload?.incident?.status !== "rejected"
                && event.payload?.verification?.status !== "rejected"
            )) || null,
            care_message: row(careMessageResult),
            care_preferences: row(carePreferencesResult),
            articles,
            weather: null,
            distance: null,
            device: row(deviceResult),
            latest_home_visit: row(homeVisitResult),
            return_plan: row(returnPlanResult),
        };
    }

    async verifyHomeVisit(userId, familyId, networkFingerprint) {
        const fingerprint = String(networkFingerprint || "").trim();
        const client = typeof this.pool.connect === "function" ? await this.pool.connect() : this.pool;
        let transaction = false;
        try {
            await client.query("begin");
            transaction = true;
            await this.assertFamilyAccess(client, userId, familyId);
            const verifiedAt = new Date(this.clock());
            const device = row(await client.query(
                `select runtime, last_seen_at from devices where family_id = $1 and status <> 'revoked' order by last_seen_at desc nulls last limit 1 for share`,
                [textId(familyId)],
            ));
            const boxFingerprint = currentHomeNetworkFingerprint(device, verifiedAt);
            if (!fingerprint || !boxFingerprint || fingerprint !== boxFingerprint) {
                await client.query("commit");
                transaction = false;
                return { matched: false, recorded: false, verified_at: null };
            }
            const visitDate = dateKeyShanghai(verifiedAt);
            const result = await client.query(
                `insert into home_visits (family_id, user_id, visit_date, verified_at, verification_method)
                 values ($1, $2, $3, $4, 'public_network_match')
                 on conflict (family_id, user_id, visit_date) do update set
                     verified_at = excluded.verified_at,
                     updated_at = excluded.verified_at
                 returning *, (xmax = 0) as inserted`,
                [textId(familyId), textId(userId), visitDate, verifiedAt.toISOString()],
            );
            await client.query(
                `update home_return_plans set status = 'completed', updated_at = $3
                 where family_id = $1 and user_id = $2 and status = 'planned' and starts_at <= $3`,
                [textId(familyId), textId(userId), verifiedAt.toISOString()],
            );
            await client.query("commit");
            transaction = false;
            const visit = row(result);
            return { matched: true, recorded: Boolean(visit?.inserted), verified_at: visit?.verified_at || verifiedAt.toISOString() };
        } catch (error) {
            if (transaction) await client.query("rollback");
            throw error;
        } finally {
            if (client !== this.pool && typeof client.release === "function") client.release();
        }
    }

    async updateHomeReturnPlan(userId, familyId, input = {}) {
        await this.assertFamilyAccess(this.pool, userId, familyId);
        const startsAt = new Date(input.starts_at || "");
        const now = new Date(this.clock());
        if (!Number.isFinite(startsAt.getTime()) || startsAt.getTime() < now.getTime() - 300_000 || startsAt.getTime() > now.getTime() + 2 * 365 * 86_400_000) {
            throw repositoryError("return plan time is invalid", 400);
        }
        return row(await this.pool.query(
            `insert into home_return_plans (family_id, user_id, starts_at, note, status)
             values ($1, $2, $3, $4, 'planned')
             on conflict (family_id, user_id) do update set
                 starts_at = excluded.starts_at,
                 note = excluded.note,
                 status = 'planned',
                 updated_at = now()
             returning *`,
            [textId(familyId), textId(userId), startsAt.toISOString(), String(input.note || "").trim().slice(0, 120)],
        ));
    }

    async cancelHomeReturnPlan(userId, familyId) {
        await this.assertFamilyAccess(this.pool, userId, familyId);
        const result = await this.pool.query(
            `update home_return_plans set status = 'cancelled', updated_at = now()
             where family_id = $1 and user_id = $2 and status = 'planned'`,
            [textId(familyId), textId(userId)],
        );
        return { cancelled: result.rowCount > 0 };
    }

    async messagesForFamily(userId, familyId, options = {}) {
        await this.assertFamilyAccess(this.pool, userId, familyId);
        const values = [textId(familyId)];
        const filters = ["family_id = $1"];
        if (options.status) {
            values.push(textId(options.status));
            filters.push(`status = $${values.length}`);
        }
        values.push(limitValue(options.limit));
        return rows(await this.pool.query(
            `select * from app_messages where ${filters.join(" and ")} order by created_at desc limit $${values.length}`,
            values,
        ));
    }

    async messageForFamily(userId, familyId, messageId) {
        await this.assertFamilyAccess(this.pool, userId, familyId);
        const result = await this.pool.query(
            `select * from app_messages where family_id = $1 and message_id = $2`,
            [textId(familyId), textId(messageId)],
        );
        const message = row(result);
        if (!message) throw repositoryError("message not found", 404);
        return message;
    }

    async recordMessageAction(userId, familyId, messageId, action) {
        const input = actionInput(action, new Date(this.clock()).getTime());
        const client = typeof this.pool.connect === "function" ? await this.pool.connect() : this.pool;
        let transaction = false;
        try {
            if (typeof client.query !== "function") throw new Error("postgres client required");
            await client.query("begin");
            transaction = true;
            await this.assertFamilyAccess(client, userId, familyId);
            const messageResult = await client.query(
                `select message_id from app_messages where family_id = $1 and message_id = $2 for update`,
                [textId(familyId), textId(messageId)],
            );
            if (!messageResult.rowCount) throw repositoryError("message not found", 404);
            const inserted = await client.query(
                `insert into app_message_actions
                    (family_id, message_id, user_id, action_type, payload, idempotency_key)
                 values ($1, $2, $3, $4, $5::jsonb, $6)
                 on conflict (idempotency_key) do nothing
                 returning *`,
                [textId(familyId), textId(messageId), textId(userId), input.action_type, JSON.stringify(input.payload), input.idempotency_key],
            );
            const persisted = inserted.rowCount
                ? row(inserted)
                : row(await client.query(
                    `select * from app_message_actions where idempotency_key = $1`,
                    [input.idempotency_key],
                ));
            if (!persisted || textId(persisted.family_id) !== textId(familyId)) throw repositoryError("idempotency key conflict", 409);
            if (inserted.rowCount) {
                await client.query(
                    `update app_messages set
                        read_at = case when $3 = 'opened' then coalesce(read_at, now()) else read_at end,
                        status = case
                            when $3 = 'dismissed' then 'dismissed'
                            when $3 in ('contacted', 'returned_home') then 'closed'
                            else status
                        end,
                        metadata = case
                            when $3 = 'snoozed' then metadata || jsonb_build_object('snoozed_until', $4)
                            else metadata
                        end,
                        updated_at = now()
                     where family_id = $1 and message_id = $2`,
                    [textId(familyId), textId(messageId), input.action_type, input.payload.snoozed_until || input.payload.until || null],
                );
                if (input.action_type === "returned_home") {
                    const preferencesResult = await client.query(
                        `select metadata from care_preferences where family_id = $1 for update`,
                        [textId(familyId)],
                    );
                    const metadata = preferencesResult.rows[0]?.metadata || {};
                    const schedule = metadata.care_card_schedule || {};
                    const updatedMetadata = {
                        ...metadata,
                        care_card_schedule: {
                            ...schedule,
                            visit_reminder: {
                                ...(schedule.visit_reminder || {}),
                                last_visit_at: dateKeyShanghai(new Date(this.clock())),
                                next_visit_at: "",
                            },
                        },
                    };
                    await client.query(
                        `insert into care_preferences (family_id, metadata)
                         values ($1, $2::jsonb)
                         on conflict (family_id) do update set metadata = excluded.metadata, updated_at = now()`,
                        [textId(familyId), JSON.stringify(updatedMetadata)],
                    );
                }
            }
            await client.query("commit");
            transaction = false;
            return persisted;
        } catch (error) {
            if (transaction) await client.query("rollback");
            throw error;
        } finally {
            if (client !== this.pool && typeof client.release === "function") client.release();
        }
    }

    async productsForFamily(userId, familyId, options = {}) {
        await this.assertFamilyAccess(this.pool, userId, familyId);
        const preferences = await this.productPreferences(userId, familyId);
        const requestedCategories = arrayValue(options.categories);
        const categories = requestedCategories.length ? requestedCategories : arrayValue(preferences.categories);
        const values = [categories, limitValue(options.limit)];
        return rows(await this.pool.query(
            `select * from product_catalog
             where status = 'active'
               and (cardinality($1::text[]) = 0 or category = any($1::text[]))
             order by verified_at desc, updated_at desc
             limit $2`,
            values,
        ));
    }

    async productById(userId, familyId, productId) {
        await this.assertFamilyAccess(this.pool, userId, familyId);
        const result = await this.pool.query(
            `select * from product_catalog where id = $1 and status = 'active'`,
            [textId(productId)],
        );
        const product = row(result);
        if (!product) throw repositoryError("product not found", 404);
        return product;
    }

    async productPreferences(userId, familyId) {
        await this.assertFamilyAccess(this.pool, userId, familyId);
        const result = await this.pool.query(
            `select * from product_preferences where family_id = $1`,
            [textId(familyId)],
        );
        return row(result) || { family_id: textId(familyId), categories: [], needs: [], updated_by: null, updated_at: null };
    }

    async updateProductPreferences(userId, familyId, input = {}) {
        const categories = arrayValue(input.categories);
        const needs = arrayValue(input.needs);
        const result = await this.pool.query(
            `insert into product_preferences (family_id, categories, needs, updated_by)
             select $1, $2::jsonb, $3::jsonb, $4
             from family_members
             where family_id = $1 and user_id = $4 and status = 'active'
             on conflict (family_id) do update set
                 categories = excluded.categories,
                 needs = excluded.needs,
                 updated_by = excluded.updated_by,
                 updated_at = now()
             returning *`,
            [textId(familyId), JSON.stringify(categories), JSON.stringify(needs), textId(userId)],
        );
        const preferences = row(result);
        if (!preferences) throw accessDenied();
        return preferences;
    }

    async memoryById(client, userId, familyId, memoryId) {
        const result = await client.query(
            `select m.*,
                    jsonb_build_object('id', u.id, 'display_name', coalesce(u.display_name, '家庭成员')) as author,
                    coalesce((select jsonb_agg(jsonb_build_object(
                        'id', mm.id, 'asset_id', mm.asset_id, 'sort_order', mm.sort_order,
                        'alt_text', mm.alt_text, 'content_type', a.content_type,
                        'media_type', case when a.content_type like 'video/%' then 'video' else 'image' end,
                        'image_url', '/api/v1/video/assets/' || mm.asset_id,
                        'media_url', '/api/v1/video/assets/' || mm.asset_id,
                        'duration_seconds', coalesce(a.metadata->'duration_seconds', '0'::jsonb)
                    ) order by mm.sort_order) from family_memory_media mm
                    join media_assets a on a.id = mm.asset_id where mm.memory_id = m.id), '[]'::jsonb) as media,
                    coalesce((select jsonb_agg(to_jsonb(c) order by c.created_at) from family_memory_comments c where c.memory_id = m.id), '[]'::jsonb) as comments,
                    (select count(*)::int from family_memory_favorites f where f.memory_id = m.id) as favorite_count,
                    exists(select 1 from family_memory_favorites f where f.memory_id = m.id and f.user_id = $3) as is_favorite
             from family_memories m
             join users u on u.id = m.author_user_id
             where m.family_id = $1 and m.id = $2 and m.status = 'published'`,
            [textId(familyId), textId(memoryId), textId(userId)],
        );
        const memory = row(result);
        if (!memory) throw repositoryError("memory not found", 404);
        return memory;
    }

    async memoriesForFamily(userId, familyId, options = {}) {
        await this.assertFamilyAccess(this.pool, userId, familyId);
        const result = await this.pool.query(
            `select m.*,
                    jsonb_build_object('id', u.id, 'display_name', coalesce(u.display_name, '家庭成员')) as author,
                    coalesce((select jsonb_agg(jsonb_build_object(
                        'id', mm.id, 'asset_id', mm.asset_id, 'sort_order', mm.sort_order,
                        'alt_text', mm.alt_text, 'content_type', a.content_type,
                        'media_type', case when a.content_type like 'video/%' then 'video' else 'image' end,
                        'image_url', '/api/v1/video/assets/' || mm.asset_id,
                        'media_url', '/api/v1/video/assets/' || mm.asset_id,
                        'duration_seconds', coalesce(a.metadata->'duration_seconds', '0'::jsonb)
                    ) order by mm.sort_order) from family_memory_media mm
                    join media_assets a on a.id = mm.asset_id where mm.memory_id = m.id), '[]'::jsonb) as media,
                    coalesce((select jsonb_agg(to_jsonb(c) order by c.created_at) from family_memory_comments c where c.memory_id = m.id), '[]'::jsonb) as comments,
                    (select count(*)::int from family_memory_favorites f where f.memory_id = m.id) as favorite_count,
                    exists(select 1 from family_memory_favorites f where f.memory_id = m.id and f.user_id = $2) as is_favorite
             from family_memories m
             join users u on u.id = m.author_user_id
             where m.family_id = $1 and m.status = 'published'
             order by m.happened_at desc, m.created_at desc
             limit $3`,
            [textId(familyId), textId(userId), limitValue(options.limit, 30, 50)],
        );
        return rows(result);
    }

    async createMemory(userId, familyId, input = {}) {
        const value = memoryInput(input);
        const client = typeof this.pool.connect === "function" ? await this.pool.connect() : this.pool;
        let transaction = false;
        try {
            await client.query("begin");
            transaction = true;
            await this.assertFamilyAccess(client, userId, familyId);
            if (value.asset_ids.length) {
                const assets = await client.query(
                    `select id, content_type from media_assets where family_id = $1 and id::text = any($2::text[]) for share`,
                    [textId(familyId), value.asset_ids],
                );
                if (assets.rowCount !== value.asset_ids.length) throw repositoryError("memory asset not found", 400);
                validateMemoryAssets(rows(assets));
            }
            const inserted = await client.query(
                `insert into family_memories
                    (family_id, author_user_id, body, happened_at, location_name, people, metadata)
                 values ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb)
                 returning id`,
                [textId(familyId), textId(userId), value.body, value.happened_at, value.location_name, JSON.stringify(value.people), JSON.stringify({ media_count: value.asset_ids.length })],
            );
            const memoryId = row(inserted).id;
            for (const [index, assetId] of value.asset_ids.entries()) {
                await client.query(
                    `insert into family_memory_media (family_id, memory_id, asset_id, sort_order) values ($1, $2, $3, $4)`,
                    [textId(familyId), memoryId, assetId, index],
                );
            }
            await client.query("commit");
            transaction = false;
            return await this.memoryById(this.pool, userId, familyId, memoryId);
        } catch (error) {
            if (transaction) await client.query("rollback");
            throw error;
        } finally {
            if (client !== this.pool && typeof client.release === "function") client.release();
        }
    }

    async updateMemory(userId, familyId, memoryId, input = {}) {
        const value = memoryInput(input, { partial: true });
        const client = typeof this.pool.connect === "function" ? await this.pool.connect() : this.pool;
        let transaction = false;
        try {
            await client.query("begin");
            transaction = true;
            await this.assertFamilyAccess(client, userId, familyId);
            const existing = await client.query(
                `select m.*, fm.role from family_memories m
                 join family_members fm on fm.family_id = m.family_id and fm.user_id = $2 and fm.status = 'active'
                 where m.family_id = $1 and m.id = $3 for update`,
                [textId(familyId), textId(userId), textId(memoryId)],
            );
            const memory = row(existing);
            if (!memory) throw repositoryError("memory not found", 404);
            if (textId(memory.author_user_id) !== textId(userId) && textId(memory.role) !== "creator") throw repositoryError("memory edit denied", 403);
            const updated = {
                body: value.body ?? memory.body,
                happened_at: value.happened_at ?? memory.happened_at,
                location_name: value.location_name ?? memory.location_name,
                people: value.people ?? memory.people,
            };
            let cleanupAssetIds = [];
            if (value.asset_ids !== undefined) {
                const previousMedia = rows(await client.query(
                    `select asset_id from family_memory_media where memory_id = $1 order by sort_order`,
                    [textId(memoryId)],
                ));
                const assets = value.asset_ids.length ? await client.query(
                    `select id, content_type from media_assets where family_id = $1 and id::text = any($2::text[]) for share`,
                    [textId(familyId), value.asset_ids],
                ) : { rowCount: 0 };
                if (assets.rowCount !== value.asset_ids.length) throw repositoryError("memory asset not found", 400);
                validateMemoryAssets(rows(assets));
                const retainedAssetIds = new Set(value.asset_ids.map(textId));
                cleanupAssetIds = previousMedia
                    .map((item) => textId(item.asset_id))
                    .filter((assetId) => !retainedAssetIds.has(assetId));
                await client.query(`delete from family_memory_media where memory_id = $1`, [textId(memoryId)]);
                for (const [index, assetId] of value.asset_ids.entries()) {
                    await client.query(
                        `insert into family_memory_media (family_id, memory_id, asset_id, sort_order) values ($1, $2, $3, $4)`,
                        [textId(familyId), textId(memoryId), assetId, index],
                    );
                }
            }
            const mediaCount = row(await client.query(`select count(*)::int as count from family_memory_media where memory_id = $1`, [textId(memoryId)]))?.count || 0;
            if (!String(updated.body || "").trim() && !mediaCount) throw repositoryError("memory content required", 400);
            await client.query(
                `update family_memories set body = $3, happened_at = $4, location_name = $5, people = $6::jsonb,
                    metadata = metadata || jsonb_build_object('media_count', $7::int), updated_at = now()
                 where family_id = $1 and id = $2 and author_user_id is not null`,
                [textId(familyId), textId(memoryId), updated.body, updated.happened_at, updated.location_name, JSON.stringify(updated.people), mediaCount],
            );
            await client.query("commit");
            transaction = false;
            return {
                memory: await this.memoryById(this.pool, userId, familyId, memoryId),
                cleanup_asset_ids: cleanupAssetIds,
            };
        } catch (error) {
            if (transaction) await client.query("rollback");
            throw error;
        } finally {
            if (client !== this.pool && typeof client.release === "function") client.release();
        }
    }

    async deleteMemory(userId, familyId, memoryId) {
        const client = typeof this.pool.connect === "function" ? await this.pool.connect() : this.pool;
        let transaction = false;
        try {
            await client.query("begin");
            transaction = true;
            await this.assertFamilyAccess(client, userId, familyId);
            const memory = row(await client.query(
                `select m.*, fm.role from family_memories m
                 join family_members fm on fm.family_id = m.family_id and fm.user_id = $3 and fm.status = 'active'
                 where m.family_id = $1 and m.id = $2 for update`,
                [textId(familyId), textId(memoryId), textId(userId)],
            ));
            if (!memory) throw repositoryError("memory not found", 404);
            if (textId(memory.author_user_id) !== textId(userId) && textId(memory.role) !== "creator") throw repositoryError("memory delete denied", 403);
            const media = await client.query(`select asset_id from family_memory_media where memory_id = $1`, [textId(memoryId)]);
            await client.query(`delete from family_memories where family_id = $1 and id = $2`, [textId(familyId), textId(memoryId)]);
            await client.query("commit");
            transaction = false;
            return { deleted: true, memory_id: textId(memoryId), cleanup_asset_ids: rows(media).map((item) => textId(item.asset_id)) };
        } catch (error) {
            if (transaction) await client.query("rollback");
            throw error;
        } finally {
            if (client !== this.pool && typeof client.release === "function") client.release();
        }
    }

    async addMemoryComment(userId, familyId, memoryId, input = {}) {
        const body = String(input.body || "").trim().slice(0, 500);
        if (!body) throw repositoryError("comment required", 400);
        const result = await this.pool.query(
            `insert into family_memory_comments (family_id, memory_id, author_user_id, body)
             select $1, m.id, $3, $4
             from family_memories m
             join family_members fm on fm.family_id = m.family_id and fm.user_id = $3 and fm.status = 'active'
             where m.family_id = $1 and m.id = $2 and m.status = 'published'
             returning id`,
            [textId(familyId), textId(memoryId), textId(userId), body],
        );
        if (!result.rowCount) {
            await this.assertFamilyAccess(this.pool, userId, familyId);
            throw repositoryError("memory not found", 404);
        }
        return await this.memoryById(this.pool, userId, familyId, memoryId);
    }

    async deleteMemoryComment(userId, familyId, memoryId, commentId) {
        const result = await this.pool.query(
            `delete from family_memory_comments c
             using family_members fm
             where c.family_id = $1 and c.memory_id = $2 and c.id = $3
               and fm.family_id = c.family_id and fm.user_id = $4 and fm.status = 'active'
               and (c.author_user_id = $4 or fm.role = 'creator')
             returning c.id`,
            [textId(familyId), textId(memoryId), textId(commentId), textId(userId)],
        );
        if (!result.rowCount) {
            await this.assertFamilyAccess(this.pool, userId, familyId);
            const comment = await this.pool.query(
                `select 1 from family_memory_comments where family_id = $1 and memory_id = $2 and id = $3`,
                [textId(familyId), textId(memoryId), textId(commentId)],
            );
            if (!comment.rowCount) throw repositoryError("comment not found", 404);
            throw repositoryError("comment delete denied", 403);
        }
        return await this.memoryById(this.pool, userId, familyId, memoryId);
    }

    async setMemoryFavorite(userId, familyId, memoryId, favorite) {
        await this.assertFamilyAccess(this.pool, userId, familyId);
        const memory = await this.pool.query(
            `select 1 from family_memories where family_id = $1 and id = $2 and status = 'published'`,
            [textId(familyId), textId(memoryId)],
        );
        if (!memory.rowCount) throw repositoryError("memory not found", 404);
        if (favorite) {
            await this.pool.query(
                `insert into family_memory_favorites (family_id, memory_id, user_id) values ($1, $2, $3)
                 on conflict (memory_id, user_id) do nothing`,
                [textId(familyId), textId(memoryId), textId(userId)],
            );
        } else {
            await this.pool.query(
                `delete from family_memory_favorites where family_id = $1 and memory_id = $2 and user_id = $3`,
                [textId(familyId), textId(memoryId), textId(userId)],
            );
        }
        return await this.memoryById(this.pool, userId, familyId, memoryId);
    }

    async activityTimelineForFamily(userId, familyId, options = {}) {
        await this.assertFamilyAccess(this.pool, userId, familyId);
        const date = /^\d{4}-\d{2}-\d{2}$/.test(String(options.date || "")) ? String(options.date) : dateKeyShanghai(this.clock());
        dayBoundsShanghai(date);
        return rows(await this.pool.query(
            `select * from activity_intervals
             where family_id = $1
               and ended_at > ($2::date::timestamp at time zone 'Asia/Shanghai')
               and started_at < (($2::date + 1)::timestamp at time zone 'Asia/Shanghai')
             order by started_at asc`,
            [textId(familyId), date],
        ));
    }

    async activityIntervalsForFamily(userId, familyId, options = {}) {
        await this.assertFamilyAccess(this.pool, userId, familyId);
        const startDate = String(options.start_date || "");
        const endDate = String(options.end_date || "");
        if (!/^\d{4}-\d{2}-\d{2}$/.test(startDate) || !/^\d{4}-\d{2}-\d{2}$/.test(endDate)) {
            throw repositoryError("invalid activity date range", 400);
        }
        const [rangeStart] = dayBoundsShanghai(startDate);
        const [, rangeEnd] = dayBoundsShanghai(endDate);
        if (rangeEnd <= rangeStart) throw repositoryError("invalid activity date range", 400);
        return rows(await this.pool.query(
            `select * from activity_intervals
             where family_id = $1
               and ended_at > ($2::date::timestamp at time zone 'Asia/Shanghai')
               and started_at < (($3::date + 1)::timestamp at time zone 'Asia/Shanghai')
             order by started_at asc`,
            [textId(familyId), startDate, endDate],
        ));
    }

    async activityIntervalsForScheduler(familyId, options = {}) {
        const startDate = String(options.start_date || "");
        const endDate = String(options.end_date || "");
        dayBoundsShanghai(startDate);
        dayBoundsShanghai(endDate);
        return rows(await this.pool.query(
            `select * from activity_intervals
             where family_id = $1
               and ended_at > ($2::date::timestamp at time zone 'Asia/Shanghai')
               and started_at < (($3::date + 1)::timestamp at time zone 'Asia/Shanghai')
             order by started_at asc`,
            [textId(familyId), startDate, endDate],
        ));
    }

    async deleteActivityHistory(userId, familyId) {
        const client = await this.pool.connect();
        try {
            await client.query("begin");
            await this.assertFamilyManager(client, userId, familyId);
            const result = await client.query(
                "delete from activity_intervals where family_id = $1",
                [textId(familyId)],
            );
            await client.query("commit");
            return { deleted: result.rowCount };
        } catch (error) {
            await client.query("rollback");
            throw error;
        } finally {
            client.release();
        }
    }

    async cleanupExpiredActivityIntervals() {
        const result = await this.pool.query(
            `delete from activity_intervals ai
             using families f
             left join care_preferences cp on cp.family_id = f.id
             where ai.family_id = f.id
               and ai.ended_at < now() - make_interval(days =>
                   case
                       when coalesce(cp.metadata->'activity_history'->>'retention_days', '') ~ '^\\d{1,3}$'
                           then greatest(7, least(365, (cp.metadata->'activity_history'->>'retention_days')::integer))
                       else 30
                   end
               )`,
        );
        return { deleted: result.rowCount };
    }

    async ingestActivityIntervals(familyId, deviceId, intervals = []) {
        const values = intervals.slice(0, 100).map((item) => activityIntervalInput(item, new Date(this.clock()).getTime()));
        const permission = row(await this.pool.query(
            `select coalesce(cp.metadata->'activity_history'->>'tracking_enabled', 'true') as tracking_enabled
             from devices d
             left join care_preferences cp on cp.family_id = d.family_id
             where d.device_id = $1 and d.family_id = $2
             limit 1`,
            [textId(deviceId), textId(familyId)],
        ));
        if (String(permission?.tracking_enabled || "true").toLowerCase() === "false") {
            return { accepted: 0, inserted: 0, skipped: values.length, reason: "activity_tracking_disabled" };
        }
        let inserted = 0;
        for (const value of values) {
            const result = await this.pool.query(
                `insert into activity_intervals
                    (family_id, device_id, camera_id, source_interval_id, room, started_at, ended_at, person_count_max, postures, confidence, metadata)
                 select $1, d.device_id, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11::jsonb
                 from devices d where d.device_id = $2 and d.family_id = $1
                 on conflict (device_id, source_interval_id) do nothing
                 returning id`,
                [textId(familyId), textId(deviceId), value.camera_id, value.source_interval_id, value.room, value.started_at, value.ended_at, value.person_count_max, JSON.stringify(value.postures), value.confidence, JSON.stringify(value.metadata)],
            );
            if (result.rowCount) inserted += 1;
        }
        return { accepted: values.length, inserted };
    }
}

module.exports = { PostgresNativeRepository };
