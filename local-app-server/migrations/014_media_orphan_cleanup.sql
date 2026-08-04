begin;

create table if not exists media_orphan_cleanup (
    storage_provider text not null,
    storage_key text not null,
    size_bytes bigint not null default 0,
    source_modified_at timestamptz,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    status text not null default 'pending',
    deletion_attempts integer not null default 0,
    deletion_error text not null default '',
    next_deletion_at timestamptz,
    deleted_at timestamptz,
    resolved_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (storage_provider, storage_key),
    constraint media_orphan_cleanup_provider_check
        check (storage_provider in ('cos', 'local')),
    constraint media_orphan_cleanup_status_check
        check (status in ('pending', 'deleting', 'failed', 'deleted', 'resolved')),
    constraint media_orphan_cleanup_size_check
        check (size_bytes >= 0),
    constraint media_orphan_cleanup_attempts_check
        check (deletion_attempts >= 0),
    constraint media_orphan_cleanup_key_check
        check (storage_key <> '' and storage_key !~ '(^|/)\.\.(/|$)')
);

create index if not exists media_orphan_cleanup_due_idx
    on media_orphan_cleanup (storage_provider, status, next_deletion_at, first_seen_at);

create index if not exists media_orphan_cleanup_last_seen_idx
    on media_orphan_cleanup (last_seen_at desc);

commit;
