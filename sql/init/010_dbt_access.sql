BEGIN;

CREATE ROLE tender_dbt
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION;

CREATE SCHEMA analytics AUTHORIZATION CURRENT_USER;

GRANT USAGE ON SCHEMA raw, staging TO tender_dbt;

GRANT SELECT ON TABLE
    raw.notices,
    staging.notices,
    staging.notice_lots
TO tender_dbt;

GRANT USAGE, CREATE ON SCHEMA analytics TO tender_dbt;

COMMIT;