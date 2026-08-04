begin;

create unique index if not exists media_assets_storage_object_unique_idx
    on media_assets (storage_provider, storage_key)
    where storage_key <> '';

create unique index if not exists media_assets_device_upload_idempotency_unique_idx
    on media_assets (device_id, (metadata ->> 'device_upload_idempotency_key'))
    where coalesce(metadata ->> 'device_upload_idempotency_key', '') <> '';

commit;
