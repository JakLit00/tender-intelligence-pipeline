\set ON_ERROR_STOP on

BEGIN;

-- Reprocessing replaces the complete lot set within one transaction.
GRANT DELETE ON TABLE staging.notice_lots TO tender_app;

COMMIT;