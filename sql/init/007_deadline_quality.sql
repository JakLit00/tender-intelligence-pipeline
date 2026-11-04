\set ON_ERROR_STOP on

BEGIN;

ALTER TABLE staging.notice_lots
    ADD COLUMN submission_deadline_quality_issue text;

ALTER TABLE staging.notice_lots
    ADD CONSTRAINT notice_lots_deadline_quality_issue_check
    CHECK (
        submission_deadline_quality_issue IS NULL
        OR submission_deadline_quality_issue = 'conflicting_timezone_offsets'
    );

ALTER TABLE staging.notice_lots
    ADD CONSTRAINT notice_lots_conflicting_deadline_check
    CHECK (
        submission_deadline_quality_issue IS DISTINCT FROM
            'conflicting_timezone_offsets'
        OR (
            submission_deadline_at IS NULL
            AND submission_deadline_local_date IS NOT NULL
            AND NULLIF(btrim(submission_deadline_date_raw), '') IS NOT NULL
            AND NULLIF(btrim(submission_deadline_time_raw), '') IS NOT NULL
        )
    );

COMMIT;