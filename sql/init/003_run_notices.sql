\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE ops.run_notices (
    run_id bigint NOT NULL,
    publication_number text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    outcome text NOT NULL DEFAULT 'pending',
    error_message text,

    PRIMARY KEY (run_id, publication_number),

    CONSTRAINT run_notices_run_fk
        FOREIGN KEY (run_id)
        REFERENCES ops.pipeline_runs (run_id),

    CONSTRAINT run_notices_publication_fk
        FOREIGN KEY (publication_number)
        REFERENCES raw.notices (publication_number),

    CONSTRAINT run_notices_outcome_check
        CHECK (
            outcome IN ('pending', 'processed', 'skipped', 'failed')
        ),

    CONSTRAINT run_notices_error_check
        CHECK (
            (
                outcome = 'failed'
                AND NULLIF(btrim(error_message), '') IS NOT NULL
            )
            OR
            (
                outcome <> 'failed'
                AND error_message IS NULL
            )
        )
);

-- The primary key supports run lookups; this index supports publication history.
CREATE INDEX run_notices_publication_idx
    ON ops.run_notices (publication_number);

GRANT SELECT, INSERT, UPDATE
    ON ops.run_notices
    TO tender_app;

COMMIT;