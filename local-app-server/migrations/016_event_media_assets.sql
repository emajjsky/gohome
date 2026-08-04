begin;

create table if not exists event_media_assets (
    id text primary key,
    event_id text not null references events(id) on delete cascade,
    asset_id text not null references media_assets(id) on delete restrict,
    role text not null default 'evidence',
    canonical boolean not null default true,
    captured_at timestamptz,
    snapshot_id text,
    postures jsonb not null default '[]'::jsonb,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (event_id, asset_id),
    constraint event_media_assets_role_check
        check (role in ('before', 'transition', 'current', 'evidence')),
    constraint event_media_assets_postures_check
        check (jsonb_typeof(postures) = 'array')
);

with source as (
    select
        event.id as event_id,
        coalesce(item.value->>'asset_id', item.value->'asset'->>'id', item.value->>'id') as asset_id,
        case
            when item.value->>'role' in ('before', 'transition', 'current', 'evidence') then item.value->>'role'
            else 'evidence'
        end as role,
        nullif(item.value->>'captured_at', '')::timestamptz as captured_at,
        nullif(item.value->>'snapshot_id', '') as snapshot_id,
        case
            when jsonb_typeof(item.value->'postures') = 'array' then item.value->'postures'
            else '[]'::jsonb
        end as postures,
        item.ordinality
    from events as event
    cross join lateral jsonb_array_elements(
        case
            when jsonb_typeof(event.payload->'evidence_media_assets') = 'array'
                then event.payload->'evidence_media_assets'
            else '[]'::jsonb
        end
    ) with ordinality as item(value, ordinality)
), deduplicated as (
    select distinct on (source.event_id, source.asset_id)
        source.*
    from source
    join media_assets on media_assets.id = source.asset_id
    where source.asset_id is not null and source.asset_id <> ''
    order by source.event_id, source.asset_id, source.ordinality
), valid as (
    select
        deduplicated.*,
        row_number() over (
            partition by deduplicated.event_id, deduplicated.role
            order by deduplicated.ordinality, deduplicated.asset_id
        ) as role_rank
    from deduplicated
)
insert into event_media_assets (
    id,
    event_id,
    asset_id,
    role,
    canonical,
    captured_at,
    snapshot_id,
    postures,
    metadata,
    created_at,
    updated_at
)
select
    'event-media:' || valid.event_id || ':' || valid.asset_id,
    valid.event_id,
    valid.asset_id,
    valid.role,
    valid.role_rank = 1,
    valid.captured_at,
    valid.snapshot_id,
    valid.postures,
    jsonb_build_object('migrated_from_event_payload', true),
    now(),
    now()
from valid
on conflict (event_id, asset_id) do nothing;

create index if not exists event_media_assets_event_idx
    on event_media_assets (event_id, canonical desc, captured_at, created_at);

create index if not exists event_media_assets_asset_idx
    on event_media_assets (asset_id, event_id);

create unique index if not exists event_media_assets_canonical_role_unique_idx
    on event_media_assets (event_id, role)
    where canonical;

update events
set payload = payload - 'evidence_media_assets',
    updated_at = now()
where payload ? 'evidence_media_assets';

commit;
