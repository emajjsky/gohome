begin;

create table if not exists home_visits (
    id text primary key default gen_random_uuid()::text,
    family_id text not null references families(id) on delete cascade,
    user_id text not null references users(id) on delete cascade,
    visit_date date not null,
    verified_at timestamptz not null,
    verification_method text not null check (verification_method = 'public_network_match'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (family_id, user_id, visit_date)
);

create index if not exists home_visits_family_verified_idx
    on home_visits (family_id, verified_at desc);

create table if not exists home_return_plans (
    id text primary key default gen_random_uuid()::text,
    family_id text not null references families(id) on delete cascade,
    user_id text not null references users(id) on delete cascade,
    starts_at timestamptz not null,
    note text not null default '',
    status text not null default 'planned' check (status in ('planned', 'cancelled', 'completed')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (family_id, user_id)
);

create index if not exists home_return_plans_family_time_idx
    on home_return_plans (family_id, status, starts_at);

commit;
