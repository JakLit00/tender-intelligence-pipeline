\set ON_ERROR_STOP on
\pset pager off

BEGIN;

INSERT INTO ops.pipeline_runs (
    run_mode,
    date_from,
    date_to
)
VALUES (
    'backfill',
    DATE '2026-10-20',
    DATE '2026-10-29'
)
RETURNING run_id, status;

INSERT INTO raw.notices (
    publication_number,
    publication_date,
    search_metadata
)
VALUES (
    '722762-2026',
    DATE '2026-10-20',
    '{"publication-number": "722762-2026"}'::jsonb
)
RETURNING publication_number, processing_status;

DO $$
DECLARE
    violated_constraint text;
BEGIN
    -- Catch only the expected failure; unexpected errors abort the test.
    BEGIN
        INSERT INTO raw.notices (
            publication_number,
            publication_date,
            search_metadata
        )
        VALUES (
            '722762-2026',
            DATE '2026-10-20',
            '{}'::jsonb
        );

        RAISE EXCEPTION 'FAIL: duplicate publication was accepted';
    EXCEPTION
        WHEN unique_violation THEN
            GET STACKED DIAGNOSTICS
                violated_constraint = CONSTRAINT_NAME;

            IF violated_constraint <> 'notices_pkey' THEN
                RAISE;
            END IF;

            RAISE NOTICE 'PASS: duplicate publication rejected';
    END;

    BEGIN
        INSERT INTO ops.pipeline_runs (
            run_mode,
            date_from,
            date_to
        )
        VALUES (
            'backfill',
            DATE '2026-10-29',
            DATE '2026-10-20'
        );

        RAISE EXCEPTION 'FAIL: inverted date range was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS
                violated_constraint = CONSTRAINT_NAME;

            IF violated_constraint <> 'pipeline_runs_date_range_check' THEN
                RAISE;
            END IF;

            RAISE NOTICE 'PASS: inverted date range rejected';
    END;
END
$$;

ROLLBACK;

SELECT count(*) AS runs FROM ops.pipeline_runs;
SELECT count(*) AS notices FROM raw.notices;