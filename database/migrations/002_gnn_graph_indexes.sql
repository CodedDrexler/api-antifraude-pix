-- Additive migration for an existing Pix database. No history is modified.
BEGIN;
CREATE INDEX IF NOT EXISTS ix_pix_destination_time ON pix_analysis (destination_identity, transaction_date);
CREATE INDEX IF NOT EXISTS ix_pix_device_time ON pix_analysis (device_id, transaction_date);
COMMIT;
