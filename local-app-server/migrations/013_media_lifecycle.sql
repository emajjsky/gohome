begin;

alter table media_assets
    add column if not exists retention_class text not null default '',
    add column if not exists retention_status text not null default 'active',
    add column if not exists retention_reason text not null default '',
    add column if not exists retain_until timestamptz,
    add column if not exists deletion_attempts integer not null default 0,
    add column if not exists deletion_error text not null default '',
    add column if not exists next_deletion_at timestamptz,
    add column if not exists deleted_at timestamptz;

alter table media_assets
    drop constraint if exists media_assets_retention_status_check,
    add constraint media_assets_retention_status_check
        check (retention_status in ('active', 'deleting', 'failed', 'deleted')),
    drop constraint if exists media_assets_deletion_attempts_check,
    add constraint media_assets_deletion_attempts_check
        check (deletion_attempts >= 0);

create index if not exists media_assets_retention_due_idx
    on media_assets (retention_status, retain_until, next_deletion_at, created_at);

create index if not exists media_assets_storage_key_idx
    on media_assets (storage_provider, storage_key)
    where storage_key <> '';

commit;
