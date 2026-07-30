begin;

create table if not exists activity_intervals (
    id text primary key default gen_random_uuid()::text,
    family_id text not null references families(id) on delete cascade,
    device_id text not null references devices(device_id) on delete cascade,
    camera_id text,
    source_interval_id text not null,
    room text not null default '',
    started_at timestamptz not null,
    ended_at timestamptz not null,
    person_count_max integer not null default 1 check (person_count_max between 0 and 20),
    postures jsonb not null default '[]'::jsonb,
    confidence double precision,
    metadata jsonb not null default '{}'::jsonb,
    received_at timestamptz not null default now(),
    constraint activity_intervals_time_check check (ended_at > started_at and ended_at <= started_at + interval '6 hours'),
    constraint activity_intervals_postures_check check (jsonb_typeof(postures) = 'array'),
    constraint activity_intervals_confidence_check check (confidence is null or (confidence >= 0 and confidence <= 1)),
    unique (device_id, source_interval_id)
);

create index if not exists activity_intervals_family_time_idx
    on activity_intervals (family_id, started_at desc);
create index if not exists activity_intervals_device_time_idx
    on activity_intervals (device_id, started_at desc);

commit;
