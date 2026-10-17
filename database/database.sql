BEGIN;

CREATE TABLE pix_analysis (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    analysis_key VARCHAR(36) NOT NULL UNIQUE,
    transaction_id VARCHAR(128) NOT NULL UNIQUE,
    payload_hash VARCHAR(64) NOT NULL,
    source_document VARCHAR(14) NOT NULL,
    source_account_identity VARCHAR(64),
    destination_identity VARCHAR(64) NOT NULL,
    device_id VARCHAR(128) NOT NULL,
    amount BIGINT NOT NULL CHECK (amount > 0),
    transaction_date TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    status VARCHAR(32) NOT NULL CHECK (status IN ('approved', 'rejected', 'two_factor_required')),
    decision_metadata JSONB NOT NULL CHECK (jsonb_typeof(decision_metadata) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(source_document) IN (11, 14))
);

CREATE INDEX ix_pix_payer_time ON pix_analysis (source_document, transaction_date);
CREATE INDEX ix_pix_destination_time ON pix_analysis (destination_identity, transaction_date);
CREATE INDEX ix_pix_device_time ON pix_analysis (device_id, transaction_date);
CREATE INDEX ix_pix_account_received ON pix_analysis (source_account_identity, created_at);
CREATE INDEX ix_pix_duplicate_payment
    ON pix_analysis (source_account_identity, destination_identity, amount, transaction_date DESC)
    WHERE status IN ('approved', 'two_factor_required');
CREATE INDEX ix_pix_approved_profile ON pix_analysis (source_document, transaction_date)
    INCLUDE (amount, destination_identity, device_id) WHERE status = 'approved';

-- Protect snapshots against UPDATE/DELETE. A schema owner/superuser can bypass
-- this control; use a separate runtime role with SELECT/INSERT only.
CREATE FUNCTION reject_pix_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Pix history is immutable' USING ERRCODE = '23514';
END;
$$;
CREATE TRIGGER pix_analysis_immutable BEFORE UPDATE OR DELETE ON pix_analysis
    FOR EACH ROW EXECUTE FUNCTION reject_pix_history_mutation();

COMMIT;
