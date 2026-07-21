"use strict";

const { NativeRepository, actionInput } = require("./repository");

const USER_COLUMNS = "id, email, display_name, phone, status, created_at, updated_at";
const FAMILY_COLUMNS = "f.id, f.name, f.status, f.timezone, f.metadata, f.created_at, f.updated_at, fm.role";

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

function accessDenied() {
    return new Error("family access denied");
}

class PostgresNativeRepository extends NativeRepository {
    constructor(pool, { clock = () => new Date() } = {}) {
        super();
        if (!pool || typeof pool.query !== "function") throw new Error("postgres pool required");
        this.pool = pool;
        this.clock = clock;
    }

    async assertFamilyAccess(client, userId, familyId) {
        const result = await client.query(
            `select 1 from family_members where family_id = $1 and user_id = $2 and status = 'active' limit 1 for share`,
            [textId(familyId), textId(userId)],
        );
        if (!result.rowCount) throw accessDenied();
    }

    async bootstrapForUser(userId) {
        const userResult = await this.pool.query(
            `select ${USER_COLUMNS} from users where id = $1 and status = 'active'`,
            [textId(userId)],
        );
        const user = row(userResult);
        if (!user) throw new Error("user not found");
        const familiesResult = await this.pool.query(
            `select ${FAMILY_COLUMNS}
             from family_members fm
             join families f on f.id = fm.family_id
             where fm.user_id = $1 and fm.status = 'active' and f.status = 'active'
             order by f.created_at asc`,
            [textId(userId)],
        );
        const families = rows(familiesResult);
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

    async onboardingForFamily(userId, familyId) {
        await this.assertFamilyAccess(this.pool, userId, familyId);
        const result = await this.pool.query(
            `select
                exists(select 1 from elder_profiles where family_id = $1) as has_profile,
                exists(select 1 from devices where family_id = $1 and status <> 'revoked') as has_device,
                exists(select 1 from cameras where family_id = $1 and status <> 'deleted') as has_camera`,
            [textId(familyId)],
        );
        const state = row(result) || {};
        const nextStep = !state.has_profile ? "profile" : !state.has_device ? "device" : !state.has_camera ? "camera" : "complete";
        return { next_step: nextStep, complete: nextStep === "complete" };
    }

    async homeForFamily(userId, familyId) {
        await this.assertFamilyAccess(this.pool, userId, familyId);
        const id = textId(familyId);
        const [familyResult, elderResult, camerasResult, calendarResult, eventsResult, articleResult] = await Promise.all([
            this.pool.query(`select ${FAMILY_COLUMNS} from family_members fm join families f on f.id = fm.family_id where fm.user_id = $1 and fm.family_id = $2 and fm.status = 'active'`, [textId(userId), id]),
            this.pool.query(`select * from elder_profiles where family_id = $1 order by created_at asc limit 1`, [id]),
            this.pool.query(`select * from cameras where family_id = $1 order by created_at asc`, [id]),
            this.pool.query(`select * from calendar_events where family_id = $1 order by starts_at asc limit 20`, [id]),
            this.pool.query(`select * from events where family_id = $1 and acknowledged = false order by occurred_at desc limit 20`, [id]),
            this.pool.query(`select * from content_recommendations where (family_id = $1 or family_id is null) and status = 'published' order by created_at desc limit 30`, [id]),
        ]);
        const events = rows(eventsResult);
        return {
            family: row(familyResult),
            elder: row(elderResult),
            cameras: rows(camerasResult),
            calendar: rows(calendarResult),
            critical_alert: events.find((event) => ["critical", "emergency"].includes(event.level)) || null,
            articles: rows(articleResult),
            weather: null,
            distance: null,
        };
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
        if (!message) throw new Error("message not found");
        return message;
    }

    async recordMessageAction(userId, familyId, messageId, action) {
        const input = actionInput(action);
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
            if (!messageResult.rowCount) throw new Error("message not found");
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
            if (!persisted || textId(persisted.family_id) !== textId(familyId)) throw new Error("idempotency key conflict");
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
        const categories = arrayValue(options.categories || preferences.categories);
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
        if (!product) throw new Error("product not found");
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
}

module.exports = { PostgresNativeRepository };
