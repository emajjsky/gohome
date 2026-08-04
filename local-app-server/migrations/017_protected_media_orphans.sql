begin;

alter table media_orphan_cleanup
    add column if not exists protection_reason text not null default '',
    add column if not exists metadata jsonb not null default '{}'::jsonb;

alter table media_orphan_cleanup
    drop constraint if exists media_orphan_cleanup_status_check,
    add constraint media_orphan_cleanup_status_check
        check (status in ('pending', 'protected', 'deleting', 'failed', 'deleted', 'resolved')),
    drop constraint if exists media_orphan_cleanup_metadata_check,
    add constraint media_orphan_cleanup_metadata_check
        check (jsonb_typeof(metadata) = 'object');

create index if not exists media_orphan_cleanup_protected_idx
    on media_orphan_cleanup (storage_provider, protection_reason, updated_at desc)
    where status = 'protected';

commit;
