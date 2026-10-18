-- Additive query index for the live v2 neighborhood. Existing decisions are preserved.
CREATE INDEX IF NOT EXISTS ix_pix_receiver_document_time
    ON pix_analysis ((payload -> 'destination_account' -> 'owner' ->> 'document_number'), transaction_date);
