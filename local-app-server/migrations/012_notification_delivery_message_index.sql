begin;

create index if not exists notification_deliveries_message_id_idx
    on notification_deliveries (message_id);

commit;
