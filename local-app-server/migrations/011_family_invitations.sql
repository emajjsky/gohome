begin;

create table if not exists family_invitations (
    id text primary key default gen_random_uuid()::text,
    family_id text not null references families(id) on delete cascade,
    code_hash text not null unique,
    code_hint text not null default '',
    created_by_user_id text references users(id) on delete set null,
    status text not null default 'active',
    expires_at timestamptz not null,
    used_by_user_id text references users(id) on delete set null,
    used_at timestamptz,
    revoked_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint family_invitations_status_check
        check (status in ('active', 'used', 'revoked', 'expired')),
    constraint family_invitations_lifecycle_check
        check (
            (status = 'used' and used_at is not null and used_by_user_id is not null)
            or (status = 'revoked' and revoked_at is not null)
            or status in ('active', 'expired')
        )
);

create index if not exists family_invitations_family_time_idx
    on family_invitations (family_id, created_at desc);

create index if not exists family_invitations_active_expiry_idx
    on family_invitations (family_id, expires_at)
    where status = 'active';

commit;
