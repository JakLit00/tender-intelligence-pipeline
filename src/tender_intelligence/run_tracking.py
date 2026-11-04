from datetime import date
from typing import Literal
from tender_intelligence.normalization import normalize_publication_number

import psycopg


RunMode = Literal["backfill", "incremental", "retry", "history"]


def start_run(
    conn: psycopg.Connection,
    *,
    run_mode: RunMode,
    date_from: date,
    date_to: date,
) -> int:
    """Register a pipeline run and return its generated identifier."""
    if run_mode not in ("backfill", "incremental", "retry", "history"):
        raise ValueError(f"Unsupported run mode: {run_mode!r}")

    if date_to < date_from:
        raise ValueError("date_to must not be earlier than date_from")

    with conn.transaction():
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO ops.pipeline_runs (
                    run_mode,
                    date_from,
                    date_to
                )
                VALUES (%s, %s, %s)
                RETURNING run_id
                """,
                (run_mode, date_from, date_to),
            )
            row = cursor.fetchone()

            if row is None:
                raise RuntimeError("Database did not return a run ID")

            run_id = row[0]

    return run_id

def link_run_notice(
    conn: psycopg.Connection,
    *,
    run_id: int,
    publication_number: str,
) -> None:
    """Link a publication to a running pipeline without resetting its outcome."""
    publication_number = normalize_publication_number(publication_number)

    with conn.transaction():
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT status
                FROM ops.pipeline_runs
                WHERE run_id = %s
                FOR UPDATE
                """,
                (run_id,),
            )
            row = cursor.fetchone()

            if row is None:
                raise ValueError(f"Pipeline run not found: {run_id}")

            if row[0] != "running":
                raise ValueError(f"Pipeline run is already finished: {run_id}")

            # Relinking must preserve any outcome already recorded for this run.
            cursor.execute(
                """
                INSERT INTO ops.run_notices (
                    run_id,
                    publication_number
                )
                VALUES (%s, %s)
                ON CONFLICT (run_id, publication_number) DO NOTHING
                """,
                (run_id, publication_number),
            )

NoticeOutcome = Literal["processed", "skipped", "failed"]


def record_notice_outcome(
    conn: psycopg.Connection,
    *,
    run_id: int,
    publication_number: str,
    outcome: NoticeOutcome,
    error_message: str | None = None,
) -> None:
    """Record a publication outcome within a running pipeline."""
    publication_number = normalize_publication_number(publication_number)

    if outcome not in ("processed", "skipped", "failed"):
        raise ValueError(f"Unsupported notice outcome: {outcome!r}")

    if outcome == "failed":
        if error_message is None or not error_message.strip():
            raise ValueError("Failed outcome requires an error message")
        error_message = error_message.strip().replace("\x00", "\\x00")
    elif error_message is not None:
        raise ValueError("Only a failed outcome may contain an error message")

    with conn.transaction():
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT status
                FROM ops.pipeline_runs
                WHERE run_id = %s
                FOR UPDATE
                """,
                (run_id,),
            )
            row = cursor.fetchone()

            if row is None:
                raise ValueError(f"Pipeline run not found: {run_id}")

            if row[0] != "running":
                raise ValueError(f"Pipeline run is already finished: {run_id}")

            cursor.execute(
                """
                UPDATE ops.run_notices
                SET outcome = %s,
                    error_message = %s
                WHERE run_id = %s AND publication_number = %s
                """,
                (
                    outcome,
                    error_message,
                    run_id,
                    publication_number,
                ),
            )

            if cursor.rowcount != 1:
                raise ValueError(
                    f"Publication {publication_number} is not linked "
                    f"to pipeline run {run_id}"
                )

RunStatus = Literal["succeeded", "partial", "failed"]


def finish_run(
    conn: psycopg.Connection,
    *,
    run_id: int,
) -> RunStatus:
    """Finish a run after all linked publications have been handled."""
    with conn.transaction():
        with conn.cursor() as cursor:
            # Linking and outcome updates lock the same run before changing it.
            cursor.execute(
                """
                SELECT status
                FROM ops.pipeline_runs
                WHERE run_id = %s
                FOR UPDATE
                """,
                (run_id,),
            )
            row = cursor.fetchone()

            if row is None:
                raise ValueError(f"Pipeline run not found: {run_id}")

            if row[0] != "running":
                raise ValueError(f"Pipeline run is already finished: {run_id}")

            cursor.execute(
                """
                SELECT
                    count(*),
                    count(*) FILTER (WHERE outcome = 'pending'),
                    count(*) FILTER (WHERE outcome = 'failed')
                FROM ops.run_notices
                WHERE run_id = %s
                """,
                (run_id,),
            )
            counts = cursor.fetchone()

            if counts is None:
                raise RuntimeError("Database did not return outcome counts")

            total_count, pending_count, failed_count = counts

            if pending_count:
                raise ValueError(
                    f"Pipeline run {run_id} has pending publications"
                )

            status: RunStatus
            error_message = None

            if failed_count == 0:
                status = "succeeded"
            elif failed_count == total_count:
                status = "failed"
            else:
                status = "partial"

            if failed_count:
                error_message = (
                    f"{failed_count} of {total_count} publications failed"
                )

            cursor.execute(
                """
                UPDATE ops.pipeline_runs
                SET status = %s,
                    finished_at = clock_timestamp(),
                    error_message = %s
                WHERE run_id = %s
                """,
                (status, error_message, run_id),
            )

    return status

def fail_run(
    conn: psycopg.Connection,
    *,
    run_id: int,
    error_message: str,
) -> None:
    """Mark an interrupted run as failed, preserving publication outcomes."""
    if not error_message.strip():
        raise ValueError("Failed run requires an error message")

    error_message = error_message.strip().replace("\x00", "\\x00")

    with conn.transaction():
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT status
                FROM ops.pipeline_runs
                WHERE run_id = %s
                FOR UPDATE
                """,
                (run_id,),
            )
            row = cursor.fetchone()

            if row is None:
                raise ValueError(f"Pipeline run not found: {run_id}")

            if row[0] != "running":
                raise ValueError(f"Pipeline run is already finished: {run_id}")

            cursor.execute(
                """
                UPDATE ops.pipeline_runs
                SET status = 'failed',
                    finished_at = clock_timestamp(),
                    error_message = %s
                WHERE run_id = %s
                """,
                (error_message, run_id),
            )