-- Persist App login sessions across service restarts without storing raw tokens.

begin;

create table if not exists app_sessions (
    id text primary key default gen_random_uuid()::text,
    user_id text not null references users(id) on delete cascade,
    token_hash text not null unique,
    status text not null default 'active',
    last_seen_at timestamptz,
    expires_at timestamptz not null,
    revoked_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists app_sessions_user_status_idx
    on app_sessions (user_id, status, expires_at desc);

commit;
