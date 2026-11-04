BEGIN;

ALTER TABLE ops.pipeline_runs
    DROP CONSTRAINT pipeline_runs_mode_check;

ALTER TABLE ops.pipeline_runs
    ADD CONSTRAINT pipeline_runs_mode_check
    CHECK (run_mode IN ('backfill', 'incremental', 'retry', 'history'));

COMMIT;