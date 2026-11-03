\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE staging.notice_lots (
    publication_number text NOT NULL,
    lot_id text NOT NULL,
    submission_deadline_date_raw text,
    submission_deadline_time_raw text,
    submission_deadline_local_date date,
    submission_deadline_at timestamptz,

    PRIMARY KEY (publication_number, lot_id),

    CONSTRAINT notice_lots_notice_fk
        FOREIGN KEY (publication_number)
        REFERENCES staging.notices (publication_number),

    CONSTRAINT notice_lots_id_check
        CHECK (btrim(lot_id) <> ''),

    CONSTRAINT notice_lots_local_date_source_check
        CHECK (
            submission_deadline_local_date IS NULL
            OR (
                submission_deadline_date_raw IS NOT NULL
                AND btrim(submission_deadline_date_raw) <> ''
            )
        ),

    -- A precise instant requires both source components and a parsed date.
    CONSTRAINT notice_lots_timestamp_source_check
        CHECK (
            submission_deadline_at IS NULL
            OR (
                submission_deadline_local_date IS NOT NULL
                AND submission_deadline_date_raw IS NOT NULL
                AND btrim(submission_deadline_date_raw) <> ''
                AND submission_deadline_time_raw IS NOT NULL
                AND btrim(submission_deadline_time_raw) <> ''
            )
        )
);

GRANT SELECT, INSERT, UPDATE
    ON staging.notice_lots
    TO tender_app;

COMMIT;