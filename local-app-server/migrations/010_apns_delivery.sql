begin;

alter table app_push_tokens
    add column if not exists provider text not null default 'apns',
    add column if not exists environment text not null default 'production',
    add column if not exists token_ciphertext text not null default '';

alter table app_push_tokens
    drop constraint if exists app_push_tokens_provider_check,
    add constraint app_push_tokens_provider_check check (provider in ('apns')),
    drop constraint if exists app_push_tokens_environment_check,
    add constraint app_push_tokens_environment_check check (environment in ('sandbox', 'production'));

commit;
