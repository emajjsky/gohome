begin;

create table if not exists family_memories (
    id text primary key default gen_random_uuid()::text,
    family_id text not null references families(id) on delete cascade,
    author_user_id text not null references users(id) on delete restrict,
    body text not null default '',
    happened_at timestamptz not null default now(),
    location_name text not null default '',
    people jsonb not null default '[]'::jsonb,
    visibility text not null default 'family',
    status text not null default 'published',
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint family_memories_people_array_check check (jsonb_typeof(people) = 'array'),
    constraint family_memories_visibility_check check (visibility in ('family')),
    constraint family_memories_status_check check (status in ('draft', 'published'))
);

create table if not exists family_memory_media (
    id text primary key default gen_random_uuid()::text,
    family_id text not null references families(id) on delete cascade,
    memory_id text not null references family_memories(id) on delete cascade,
    asset_id text not null references media_assets(id) on delete restrict,
    sort_order integer not null default 0 check (sort_order >= 0),
    alt_text text not null default '',
    created_at timestamptz not null default now(),
    unique (memory_id, asset_id),
    unique (memory_id, sort_order)
);

create table if not exists family_memory_comments (
    id text primary key default gen_random_uuid()::text,
    family_id text not null references families(id) on delete cascade,
    memory_id text not null references family_memories(id) on delete cascade,
    author_user_id text not null references users(id) on delete restrict,
    body text not null check (btrim(body) <> '' and char_length(body) <= 500),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists family_memory_favorites (
    family_id text not null references families(id) on delete cascade,
    memory_id text not null references family_memories(id) on delete cascade,
    user_id text not null references users(id) on delete cascade,
    created_at timestamptz not null default now(),
    primary key (memory_id, user_id)
);

create index if not exists family_memories_family_time_idx
    on family_memories (family_id, happened_at desc, created_at desc);
create index if not exists family_memory_media_memory_order_idx
    on family_memory_media (memory_id, sort_order asc);
create index if not exists family_memory_comments_memory_time_idx
    on family_memory_comments (memory_id, created_at asc);
create index if not exists family_memory_favorites_family_time_idx
    on family_memory_favorites (family_id, created_at desc);

commit;
