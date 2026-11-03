\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE ops.pipeline_runs (
    run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_mode text NOT NULL,
    date_from date NOT NULL,
    date_to date NOT NULL,
    started_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at timestamptz,
    status text NOT NULL DEFAULT 'running',
    error_message text,

    CONSTRAINT pipeline_runs_mode_check
        CHECK (run_mode IN ('backfill', 'incremental', 'retry')),

    CONSTRAINT pipeline_runs_date_range_check
        CHECK (date_to >= date_from),

    CONSTRAINT pipeline_runs_status_check
        CHECK (status IN ('running', 'succeeded', 'partial', 'failed')),

    CONSTRAINT pipeline_runs_completion_check
        CHECK (
            (status = 'running' AND finished_at IS NULL)
            OR
            (status <> 'running' AND finished_at IS NOT NULL)
        ),

    CONSTRAINT pipeline_runs_time_order_check
        CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE TABLE raw.notices (
    publication_number text PRIMARY KEY,
    publication_date date NOT NULL,
    search_metadata jsonb NOT NULL,
    first_seen_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Preserve downloaded bytes, including the original XML encoding.
    xml_content bytea,
    xml_downloaded_at timestamptz,

    processing_status text NOT NULL DEFAULT 'pending',
    processed_at timestamptz,
    last_error text,

    CONSTRAINT notices_metadata_object_check
        CHECK (jsonb_typeof(search_metadata) = 'object'),

    CONSTRAINT notices_seen_order_check
        CHECK (last_seen_at >= first_seen_at),

    CONSTRAINT notices_xml_presence_check
        CHECK (
            (xml_content IS NULL AND xml_downloaded_at IS NULL)
            OR
            (xml_content IS NOT NULL AND xml_downloaded_at IS NOT NULL)
        ),

    CONSTRAINT notices_processing_status_check
        CHECK (processing_status IN ('pending', 'succeeded', 'failed')),

    CONSTRAINT notices_processing_completion_check
        CHECK (
            (
                processing_status = 'succeeded'
                AND xml_content IS NOT NULL
                AND processed_at IS NOT NULL
                AND last_error IS NULL
            )
            OR
            (
                processing_status IN ('pending', 'failed')
                AND processed_at IS NULL
            )
        ),

    CONSTRAINT notices_failure_message_check
        CHECK (
            processing_status <> 'failed'
            OR NULLIF(btrim(last_error), '') IS NOT NULL
        )
);

GRANT SELECT, INSERT, UPDATE
    ON ops.pipeline_runs, raw.notices
    TO tender_app;

GRANT USAGE
    ON SEQUENCE ops.pipeline_runs_run_id_seq
    TO tender_app;

COMMIT;