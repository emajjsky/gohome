-- GoHome cloud application schema, V1 seed baseline.
-- Target: PostgreSQL 14+.
-- The local JSON app server remains the development substitute until these
-- tables are connected to the runtime through a database adapter.

begin;

create extension if not exists pgcrypto;

create table if not exists users (
    id text primary key default gen_random_uuid()::text,
    email text not null,
    display_name text not null default '',
    phone text not null default '',
    password_hash text,
    status text not null default 'active',
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists users_email_unique_idx
    on users (lower(email));

create table if not exists families (
    id text primary key default gen_random_uuid()::text,
    name text not null,
    status text not null default 'active',
    timezone text not null default 'Asia/Shanghai',
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists family_members (
    id text primary key default gen_random_uuid()::text,
    family_id text not null references families(id) on delete cascade,
    user_id text not null references users(id) on delete cascade,
    role text not null default 'member',
    status text not null default 'active',
    invited_by text references users(id) on delete set null,
    joined_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (family_id, user_id)
);

create table if not exists elder_profiles (
    id text primary key default gen_random_uuid()::text,
    family_id text not null references families(id) on delete cascade,
    elder_id text not null default 'elder_primary',
    display_name text not null default '',
    relationship text not null default '',
    age integer,
    city text not null default '',
    health_notes text not null default '',
    care_preferences jsonb not null default '{}'::jsonb,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (family_id, elder_id)
);

create table if not exists devices (
    device_id text primary key,
    family_id text references families(id) on delete set null,
    name text not null default '回家盒子',
    device_type text not null default 'edge-agent',
    status text not null default 'active',
    worker_running boolean,
    detector_backend text not null default '',
    yolo_model text not null default '',
    yolo_imgsz integer,
    lan_url text not null default '',
    service_url text not null default '',
    reported_config_version text not null default '',
    app_version text not null default '',
    model_version text not null default '',
    sync_status text not null default '',
    last_error text not null default '',
    runtime jsonb not null default '{}'::jsonb,
    metadata jsonb not null default '{}'::jsonb,
    last_seen_at timestamptz,
    last_sync_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists device_bindings (
    id text primary key default gen_random_uuid()::text,
    family_id text not null references families(id) on delete cascade,
    device_id text not null references devices(device_id) on delete cascade,
    device_name text not null default '回家盒子',
    device_type text not null default 'edge-agent',
    status text not null default 'active',
    note text not null default '',
    bound_at timestamptz not null default now(),
    last_seen_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (family_id, device_id)
);

create table if not exists binding_codes (
    id text primary key default gen_random_uuid()::text,
    family_id text not null references families(id) on delete cascade,
    code text not null unique,
    status text not null default 'active',
    note text not null default '',
    expires_at timestamptz not null,
    used_at timestamptz,
    device_id text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists device_tokens (
    id text primary key default gen_random_uuid()::text,
    family_id text not null references families(id) on delete cascade,
    device_id text not null references devices(device_id) on delete cascade,
    token_hash text not null,
    status text not null default 'active',
    note text not null default '',
    last_heartbeat_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists device_tokens_active_device_idx
    on device_tokens (device_id)
    where status = 'active';

create table if not exists cameras (
    id text primary key default gen_random_uuid()::text,
    family_id text not null references families(id) on delete cascade,
    device_id text references devices(device_id) on delete set null,
    name text not null default '',
    room text not null default '',
    enabled boolean not null default true,
    status text not null default 'pending_edge_sync',
    sync_status text not null default 'pending_edge_sync',
    source text not null default 'app_server_config',
    has_stream_config boolean not null default false,
    local_camera_id text,
    edge_camera_id text,
    last_error text not null default '',
    last_seen_at timestamptz,
    edge_reported_at timestamptz,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists cameras_family_device_idx
    on cameras (family_id, device_id);

create table if not exists camera_secrets (
    camera_id text primary key references cameras(id) on delete cascade,
    stream_url text not null default '',
    username text not null default '',
    password_secret text not null default '',
    secret_ref text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists care_rules (
    id text primary key default gen_random_uuid()::text,
    family_id text not null references families(id) on delete cascade,
    camera_id text references cameras(id) on delete cascade,
    rule_type text not null,
    enabled boolean not null default true,
    config jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists care_preferences (
    family_id text primary key references families(id) on delete cascade,
    elder_id text not null default 'elder_primary',
    frequency text not null default 'daily',
    quiet_hours jsonb not null default '{}'::jsonb,
    interests jsonb not null default '[]'::jsonb,
    text_model_enabled boolean not null default false,
    image_generation_enabled boolean not null default false,
    image_provider text not null default '',
    image_model text not null default '',
    content_recommendations_enabled boolean not null default false,
    content_sources_enabled boolean not null default false,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists model_providers (
    provider_id text primary key,
    provider text not null default '',
    model text not null default '',
    purpose text not null default 'care_text',
    enabled boolean not null default false,
    configured boolean not null default false,
    api_key_secret_ref text not null default '',
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists content_sources (
    id text primary key default gen_random_uuid()::text,
    family_id text references families(id) on delete cascade,
    source_type text not null default 'link',
    title text not null default '',
    source_name text not null default '',
    url text not null default '',
    provider text not null default '',
    enabled boolean not null default true,
    whitelist_status text not null default 'manual',
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists content_sources_family_idx
    on content_sources (family_id);

create table if not exists media_assets (
    id text primary key default gen_random_uuid()::text,
    family_id text references families(id) on delete set null,
    device_id text references devices(device_id) on delete set null,
    camera_id text references cameras(id) on delete set null,
    file_name text not null default '',
    content_type text not null default 'image/jpeg',
    snapshot_path text not null default '',
    relative_path text not null default '',
    storage_provider text not null default 'local',
    storage_key text not null default '',
    edge_event_id text not null default '',
    size_bytes bigint not null default 0,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists media_assets_snapshot_path_idx
    on media_assets (snapshot_path);

create table if not exists events (
    id text primary key default gen_random_uuid()::text,
    family_id text references families(id) on delete set null,
    device_id text references devices(device_id) on delete set null,
    camera_id text references cameras(id) on delete set null,
    media_asset_id text references media_assets(id) on delete set null,
    idempotency_key text not null unique,
    edge_event_id text,
    event_type text not null default 'event',
    level text not null default 'warning',
    summary text not null default '',
    room text not null default '',
    camera_name text not null default '',
    snapshot_path text not null default '',
    acknowledged boolean not null default false,
    resolution text not null default '',
    payload jsonb not null default '{}'::jsonb,
    occurred_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists events_family_time_idx
    on events (family_id, occurred_at desc);

create index if not exists events_camera_time_idx
    on events (camera_id, occurred_at desc);

create table if not exists device_heartbeats (
    id text primary key default gen_random_uuid()::text,
    device_id text not null references devices(device_id) on delete cascade,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists device_heartbeats_device_time_idx
    on device_heartbeats (device_id, created_at desc);

create table if not exists calendar_events (
    id text primary key default gen_random_uuid()::text,
    family_id text not null references families(id) on delete cascade,
    elder_id text not null default 'elder_primary',
    title text not null default '',
    starts_at timestamptz not null,
    note text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists care_cards (
    id text primary key default gen_random_uuid()::text,
    card_id text not null unique,
    family_id text not null references families(id) on delete cascade,
    elder_id text not null default 'elder_primary',
    card_date date not null,
    card_type text not null default 'daily',
    title text not null default '',
    body text not null default '',
    facts jsonb not null default '[]'::jsonb,
    source_message_ids jsonb not null default '[]'::jsonb,
    image_mode text not null default 'none',
    image_url text not null default '',
    actions jsonb not null default '[]'::jsonb,
    status text not null default 'open',
    generated_by text not null default '',
    source_summary jsonb not null default '[]'::jsonb,
    content_recommendations jsonb not null default '[]'::jsonb,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (family_id, elder_id, card_date, card_type)
);

create index if not exists care_cards_family_date_idx
    on care_cards (family_id, card_date desc);

create table if not exists model_generation_jobs (
    id text primary key default gen_random_uuid()::text,
    family_id text references families(id) on delete cascade,
    provider_id text references model_providers(provider_id) on delete set null,
    purpose text not null default 'care_text',
    model text not null default '',
    prompt_version text not null default '',
    input_hash text not null default '',
    output_status text not null default 'pending',
    request_payload jsonb not null default '{}'::jsonb,
    response_payload jsonb not null default '{}'::jsonb,
    error_message text not null default '',
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists model_generation_jobs_family_time_idx
    on model_generation_jobs (family_id, created_at desc);

create table if not exists content_recommendations (
    id text primary key default gen_random_uuid()::text,
    family_id text references families(id) on delete cascade,
    elder_id text not null default 'elder_primary',
    source_id text references content_sources(id) on delete set null,
    content_type text not null default 'article',
    title text not null default '',
    source_name text not null default '',
    url text not null default '',
    summary text not null default '',
    reason text not null default '',
    status text not null default 'candidate',
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists content_recommendations_family_time_idx
    on content_recommendations (family_id, created_at desc);

create table if not exists device_config_versions (
    id text primary key default gen_random_uuid()::text,
    family_id text references families(id) on delete set null,
    device_id text references devices(device_id) on delete cascade,
    config_type text not null default 'camera',
    config_version text not null,
    payload jsonb not null default '{}'::jsonb,
    applied_at timestamptz,
    created_at timestamptz not null default now(),
    unique (device_id, config_type, config_version)
);

create table if not exists audit_logs (
    id text primary key default gen_random_uuid()::text,
    family_id text references families(id) on delete set null,
    actor_user_id text references users(id) on delete set null,
    actor_device_id text references devices(device_id) on delete set null,
    action text not null,
    target_type text not null default '',
    target_id text not null default '',
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists audit_logs_family_time_idx
    on audit_logs (family_id, created_at desc);

commit;
