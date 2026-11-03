\set ON_ERROR_STOP on
\pset pager off

BEGIN;

INSERT INTO ops.pipeline_runs (run_mode, date_from, date_to)
VALUES ('backfill', DATE '2026-10-20', DATE '2026-10-20')
RETURNING run_id AS first_run_id
\gset

INSERT INTO ops.pipeline_runs (run_mode, date_from, date_to)
VALUES ('incremental', DATE '2026-10-20', DATE '2026-10-20')
RETURNING run_id AS second_run_id
\gset

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

INSERT INTO ops.run_notices (run_id, publication_number)
VALUES
    (:first_run_id, '722762-2026'),
    (:second_run_id, '722762-2026');

SELECT
    rn.run_id,
    r.run_mode,
    rn.publication_number,
    rn.outcome
FROM ops.run_notices AS rn
JOIN ops.pipeline_runs AS r USING (run_id)
WHERE rn.publication_number = '722762-2026'
ORDER BY rn.run_id;

DO $$
DECLARE
    existing_run_id bigint;
    violated_constraint text;
BEGIN
    SELECT run_id INTO STRICT existing_run_id
    FROM ops.run_notices
    WHERE publication_number = '722762-2026'
    ORDER BY run_id
    LIMIT 1;

    BEGIN
        INSERT INTO ops.run_notices (run_id, publication_number)
        VALUES (existing_run_id, '722762-2026');

        RAISE EXCEPTION 'FAIL: duplicate run-publication link was accepted';
    EXCEPTION
        WHEN unique_violation THEN
            GET STACKED DIAGNOSTICS
                violated_constraint = CONSTRAINT_NAME;

            IF violated_constraint <> 'run_notices_pkey' THEN
                RAISE;
            END IF;

            RAISE NOTICE 'PASS: duplicate run-publication link rejected';
    END;

    BEGIN
        -- This deliberately absent value tests the publication foreign key.
        INSERT INTO ops.run_notices (run_id, publication_number)
        VALUES (existing_run_id, 'missing-test-publication');

        RAISE EXCEPTION 'FAIL: link to a missing publication was accepted';
    EXCEPTION
        WHEN foreign_key_violation THEN
            GET STACKED DIAGNOSTICS
                violated_constraint = CONSTRAINT_NAME;

            IF violated_constraint <> 'run_notices_publication_fk' THEN
                RAISE;
            END IF;

            RAISE NOTICE 'PASS: link to a missing publication rejected';
    END;
END
$$;

ROLLBACK;

SELECT count(*) AS run_notices FROM ops.run_notices;