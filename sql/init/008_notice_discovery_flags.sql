BEGIN;

-- Existing notices were registered from the original scope search.
ALTER TABLE raw.notices
    ADD COLUMN discovered_by_scope_search boolean NOT NULL DEFAULT true,
    ADD COLUMN discovered_as_predecessor boolean NOT NULL DEFAULT false;

COMMIT;