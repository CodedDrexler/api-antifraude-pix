-- Additive: old analyses retain their original metadata and remain replayable.
BEGIN;
ALTER TABLE pix_analysis ADD COLUMN IF NOT EXISTS source_account_identity VARCHAR(64);
CREATE INDEX IF NOT EXISTS ix_pix_account_received
    ON pix_analysis (source_account_identity, created_at);
COMMIT;
