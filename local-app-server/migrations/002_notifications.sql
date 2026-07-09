-- GoHome notification scheduler and in-app message tables.

begin;

create table if not exists app_messages (
    id text primary key default gen_random_uuid()::text,
    message_id text not null unique,
    family_id text not null references families(id) on delete cascade,
    user_id text references users(id) on delete set null,
    care_card_id text,
    event_id text references events(id) on delete set null,
    message_type text not null default 'care',
    title text not null default '',
    subtitle text not null default '',
    body text not null default '',
    facts jsonb not null default '[]'::jsonb,
    actions jsonb not null default '[]'::jsonb,
    source jsonb not null default '[]'::jsonb,
    source_event_ids jsonb not null default '[]'::jsonb,
    priority text not null default 'normal',
    status text not null default 'open',
    generated_by text not null default '',
    idempotency_key text not null unique,
    metadata jsonb not null default '{}'::jsonb,
    scheduled_for timestamptz,
    delivered_at timestamptz,
    read_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists app_messages_family_time_idx
    on app_messages (family_id, created_at desc);

create index if not exists app_messages_family_status_idx
    on app_messages (family_id, status, created_at desc);

create table if not exists app_push_tokens (
    id text primary key default gen_random_uuid()::text,
    family_id text not null references families(id) on delete cascade,
    user_id text references users(id) on delete set null,
    app_install_id text not null,
    platform text not null default 'ios',
    push_token_hash text not null,
    token_preview text not null default '',
    status text not null default 'active',
    device_name text not null default '',
    app_version text not null default '',
    metadata jsonb not null default '{}'::jsonb,
    last_seen_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (user_id, app_install_id)
);

create index if not exists app_push_tokens_family_status_idx
    on app_push_tokens (family_id, status);

create table if not exists notification_deliveries (
    id text primary key default gen_random_uuid()::text,
    family_id text not null references families(id) on delete cascade,
    user_id text references users(id) on delete set null,
    message_id text references app_messages(message_id) on delete set null,
    channel text not null default 'app_push',
    provider text not null default 'app_message',
    target_type text not null default 'family',
    target_id text not null default '',
    status text not null default 'queued',
    title text not null default '',
    body text not null default '',
    error_message text not null default '',
    request_payload jsonb not null default '{}'::jsonb,
    response_payload jsonb not null default '{}'::jsonb,
    idempotency_key text not null unique,
    scheduled_for timestamptz,
    sent_at timestamptz,
    delivered_at timestamptz,
    clicked_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists notification_deliveries_family_time_idx
    on notification_deliveries (family_id, created_at desc);

create table if not exists scheduler_runs (
    id text primary key default gen_random_uuid()::text,
    family_id text references families(id) on delete set null,
    job_type text not null default 'care_notification',
    status text not null default 'running',
    scope jsonb not null default '{}'::jsonb,
    result jsonb not null default '{}'::jsonb,
    error_message text not null default '',
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists scheduler_runs_family_time_idx
    on scheduler_runs (family_id, started_at desc);

commit;
