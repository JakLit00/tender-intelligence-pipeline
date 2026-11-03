\set ON_ERROR_STOP on
\pset pager off

BEGIN;

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

INSERT INTO staging.notices (
    publication_number,
    notice_id,
    notice_version,
    procedure_id,
    notice_type,
    publication_date,
    changed_notice_identifier_raw,
    reference_type,
    previous_publication_number,
    change_reason_code
)
VALUES (
    '722762-2026',
    '8ac273c6-7603-4ad1-b9a2-8ed027ed773f',
    '01',
    '4835bb55-6b3a-4579-81d8-b34df3e663ce',
    'cn-standard',
    DATE '2026-10-20',
    '706539-2026',
    'publication_number',
    '706539-2026',
    'cor-buy'
);

INSERT INTO staging.notice_lots (
    publication_number,
    lot_id,
    submission_deadline_date_raw,
    submission_deadline_time_raw,
    submission_deadline_local_date,
    submission_deadline_at
)
VALUES (
    '722762-2026',
    'LOT-0001',
    '2026-11-03+01:00',
    '09:00:00+01:00',
    DATE '2026-11-03',
    TIMESTAMPTZ '2026-11-03 09:00:00+01:00'
);

SELECT
    n.publication_number,
    n.reference_type,
    n.previous_publication_number,
    l.lot_id,
    l.submission_deadline_local_date,
    l.submission_deadline_at AT TIME ZONE 'UTC' AS deadline_utc
FROM staging.notices AS n
JOIN staging.notice_lots AS l USING (publication_number)
WHERE n.publication_number = '722762-2026';

DO $$
DECLARE
    violated_constraint text;
BEGIN
    BEGIN
        -- Changing the reference type without its identifying fields is invalid.
        UPDATE staging.notices
        SET reference_type = 'notice_version'
        WHERE publication_number = '722762-2026';

        RAISE EXCEPTION 'FAIL: inconsistent reference fields were accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS
                violated_constraint = CONSTRAINT_NAME;

            IF violated_constraint <> 'staging_notices_reference_fields_check' THEN
                RAISE;
            END IF;

            RAISE NOTICE 'PASS: inconsistent reference fields rejected';
    END;

    BEGIN
        INSERT INTO staging.notice_lots (publication_number, lot_id)
        VALUES ('missing-test-publication', 'LOT-0001');

        RAISE EXCEPTION 'FAIL: lot without a publication was accepted';
    EXCEPTION
        WHEN foreign_key_violation THEN
            GET STACKED DIAGNOSTICS
                violated_constraint = CONSTRAINT_NAME;

            IF violated_constraint <> 'notice_lots_notice_fk' THEN
                RAISE;
            END IF;

            RAISE NOTICE 'PASS: lot without a publication rejected';
    END;
END
$$;

ROLLBACK;

SELECT count(*) AS raw_notices FROM raw.notices;
SELECT count(*) AS staged_notices FROM staging.notices;
SELECT count(*) AS staged_lots FROM staging.notice_lots;