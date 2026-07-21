-- Native iOS app contracts for message actions and product discovery.

begin;

create table if not exists app_message_actions (
    id text primary key default gen_random_uuid()::text,
    family_id text not null references families(id) on delete cascade,
    message_id text not null references app_messages(message_id) on delete cascade,
    user_id text references users(id) on delete set null,
    action_type text not null check (action_type in ('opened', 'shared', 'contacted', 'snoozed', 'dismissed', 'returned_home')),
    payload jsonb not null default '{}'::jsonb,
    idempotency_key text not null unique,
    created_at timestamptz not null default now()
);

create index if not exists app_message_actions_family_time_idx
    on app_message_actions (family_id, created_at desc);

create index if not exists app_message_actions_message_type_idx
    on app_message_actions (message_id, action_type, created_at desc);

create table if not exists product_catalog (
    id text primary key default gen_random_uuid()::text,
    category text not null,
    brand text not null default '',
    name text not null,
    summary text not null default '',
    image_url text not null default '',
    source_name text not null default '',
    source_url text not null default '',
    suitability jsonb not null default '{}'::jsonb,
    disclosure text not null default '',
    status text not null default 'active',
    verified_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists product_catalog_status_category_idx
    on product_catalog (status, category, verified_at desc);

create table if not exists product_preferences (
    family_id text primary key references families(id) on delete cascade,
    categories jsonb not null default '[]'::jsonb,
    needs jsonb not null default '[]'::jsonb,
    updated_by text references users(id) on delete set null,
    updated_at timestamptz not null default now()
);

create index if not exists product_preferences_updated_at_idx
    on product_preferences (updated_at desc);

commit;
