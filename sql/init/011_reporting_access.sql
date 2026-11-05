\set ON_ERROR_STOP on
\getenv report_password REPORT_DB_PASSWORD

BEGIN;

SELECT 'CREATE ROLE tender_reporter LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION'
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = 'tender_reporter'
)
\gexec

SELECT FORMAT(
    'ALTER ROLE tender_reporter PASSWORD %L',
    :'report_password'
)
\gexec

GRANT USAGE ON SCHEMA analytics TO tender_reporter;

GRANT SELECT ON ALL TABLES IN SCHEMA analytics
TO tender_reporter;

-- dbt creates models as tender_dbt, so defaults must target that role.
ALTER DEFAULT PRIVILEGES FOR ROLE tender_dbt IN SCHEMA analytics
GRANT SELECT ON TABLES TO tender_reporter;

COMMIT;