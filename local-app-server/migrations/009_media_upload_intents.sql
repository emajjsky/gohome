begin;

create table if not exists media_upload_intents (
    asset_id text primary key,
    family_id text not null references families(id) on delete cascade,
    user_id text not null references users(id) on delete cascade,
    object_key text not null unique,
    content_type text not null,
    size_bytes bigint not null check (size_bytes > 0),
    pixel_width integer not null default 0 check (pixel_width >= 0),
    pixel_height integer not null default 0 check (pixel_height >= 0),
    duration_seconds double precision not null default 0 check (duration_seconds >= 0),
    expires_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint media_upload_intents_content_type_check check (
        content_type in ('image/jpeg', 'image/png', 'image/webp', 'video/mp4')
    ),
    constraint media_upload_intents_object_key_check check (
        object_key like 'memory-media/%'
    )
);

create index if not exists media_upload_intents_expiry_idx
    on media_upload_intents (expires_at asc);
create index if not exists media_upload_intents_family_idx
    on media_upload_intents (family_id, created_at desc);

commit;
