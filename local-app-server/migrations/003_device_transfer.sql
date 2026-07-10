-- Keep the box cloud identity active while it is not assigned to a family.

begin;

alter table device_tokens
    alter column family_id drop not null;

alter table device_tokens
    drop constraint if exists device_tokens_family_id_fkey;

alter table device_tokens
    add constraint device_tokens_family_id_fkey
    foreign key (family_id) references families(id) on delete set null;

commit;
