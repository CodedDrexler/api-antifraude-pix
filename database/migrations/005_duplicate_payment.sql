-- Additive index for the short-window duplicate-payment lookup.
BEGIN;
CREATE INDEX IF NOT EXISTS ix_pix_duplicate_payment
    ON pix_analysis (source_account_identity, destination_identity, amount, transaction_date DESC)
    WHERE status IN ('approved', 'two_factor_required');
COMMIT;
