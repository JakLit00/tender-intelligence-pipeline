\set ON_ERROR_STOP on
\getenv app_password APP_DB_PASSWORD

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = 'tender_app'
    ) THEN
        CREATE ROLE tender_app LOGIN
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
    END IF;
END
$$;

ALTER ROLE tender_app
    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;

-- Quote the password as a SQL literal instead of interpolating it into SQL.
SELECT format(
    'ALTER ROLE tender_app PASSWORD %L',
    :'app_password'
)
\gexec

CREATE SCHEMA IF NOT EXISTS ops AUTHORIZATION CURRENT_USER;
CREATE SCHEMA IF NOT EXISTS raw AUTHORIZATION CURRENT_USER;
CREATE SCHEMA IF NOT EXISTS staging AUTHORIZATION CURRENT_USER;

-- Use the connected database name rather than hard-coding an environment.
SELECT format(
    'GRANT CONNECT ON DATABASE %I TO tender_app',
    current_database()
)
\gexec

GRANT USAGE ON SCHEMA ops, raw, staging TO tender_app;

COMMIT;