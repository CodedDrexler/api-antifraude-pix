-- Additive index only; no history or decisions are rewritten.
CREATE INDEX IF NOT EXISTS ix_pix_document_received
    ON pix_analysis (source_document, created_at);
CREATE INDEX IF NOT EXISTS ix_pix_receiver_document_received
    ON pix_analysis ((payload -> 'destination_account' -> 'owner' ->> 'document_number'), created_at);
