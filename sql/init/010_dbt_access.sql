\set ON_ERROR_STOP on
\getenv dbt_password DBT_DB_PASSWORD

BEGIN;

CREATE ROLE tender_dbt
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION;

-- Quote the password as a SQL literal without printing it as a result.
SELECT format(
    'ALTER ROLE tender_dbt PASSWORD %L',
    :'dbt_password'
)
\gexec

CREATE SCHEMA analytics AUTHORIZATION CURRENT_USER;

GRANT USAGE ON SCHEMA raw, staging TO tender_dbt;

GRANT SELECT ON TABLE
    raw.notices,
    staging.notices,
    staging.notice_lots
TO tender_dbt;

GRANT USAGE, CREATE ON SCHEMA analytics TO tender_dbt;

COMMIT;