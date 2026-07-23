"use strict";

const { NativeRepository, actionInput, activityIntervalInput, articlesFromCareCards, memoryInput, repositoryError } = require("./repository");

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
        const [familyResult, elderResult, camerasResult, calendarResult, eventsResult, articleResult, careCardResult, careMessageResult] = await Promise.all([
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
                   and message_type in ('return_home', 'care_card')
                   and status = 'open'
                   and (
                       nullif(metadata->>'snoozed_until', '') is null
                       or (metadata->>'snoozed_until')::timestamptz <= now()
                   )
                 order by case when message_type = 'return_home' then 0 else 1 end, created_at desc
                 limit 1`,
                [id],
            ),
        ]);
        const events = rows(eventsResult);
        const publishedArticles = rows(articleResult);
        return {
            family: row(familyResult),
            elder: row(elderResult),
            cameras: rows(camerasResult),
            calendar: rows(calendarResult),
            critical_alert: events.find((event) => ["critical", "emergency"].includes(event.level)) || null,
            care_message: row(careMessageResult),
            articles: publishedArticles.length ? publishedArticles : articlesFromCareCards(rows(careCardResult), id),
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
                        'alt_text', mm.alt_text, 'image_url', '/api/v1/video/assets/' || mm.asset_id
                    ) order by mm.sort_order) from family_memory_media mm where mm.memory_id = m.id), '[]'::jsonb) as media,
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
                        'alt_text', mm.alt_text, 'image_url', '/api/v1/video/assets/' || mm.asset_id
                    ) order by mm.sort_order) from family_memory_media mm where mm.memory_id = m.id), '[]'::jsonb) as media,
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
                    `select id from media_assets where family_id = $1 and id::text = any($2::text[]) for share`,
                    [textId(familyId), value.asset_ids],
                );
                if (assets.rowCount !== value.asset_ids.length) throw repositoryError("memory asset not found", 400);
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
                    `select id from media_assets where family_id = $1 and id::text = any($2::text[]) for share`,
                    [textId(familyId), value.asset_ids],
                ) : { rowCount: 0 };
                if (assets.rowCount !== value.asset_ids.length) throw repositoryError("memory asset not found", 400);
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
        return rows(await this.pool.query(
            `select * from activity_intervals
             where family_id = $1 and (started_at at time zone 'Asia/Shanghai')::date = $2::date
             order by started_at asc`,
            [textId(familyId), date],
        ));
    }

    async ingestActivityIntervals(familyId, deviceId, intervals = []) {
        const values = intervals.slice(0, 100).map((item) => activityIntervalInput(item, new Date(this.clock()).getTime()));
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
