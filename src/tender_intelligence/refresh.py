import logging
from dataclasses import dataclass
from datetime import date

import psycopg
from psycopg.pq import TransactionStatus

from tender_intelligence.history import run_history
from tender_intelligence.pipeline import run_incremental
from tender_intelligence.predecessors import find_missing_predecessor_publications


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionRefreshResult:
    incremental_run_id: int | None
    history_run_ids: tuple[int, ...]


def _require_successful_run(
    connection: psycopg.Connection,
    run_id: int,
) -> None:
    row = connection.execute(
        """
        SELECT status, error_message
        FROM ops.pipeline_runs
        WHERE run_id = %s
        """,
        (run_id,),
    ).fetchone()

    if row is None:
        raise RuntimeError(f"Run {run_id} was not found")

    status, error_message = row

    if status != "succeeded":
        detail = error_message or "No error details recorded"
        raise RuntimeError(f"Run {run_id} ended with {status}: {detail}")


def refresh_ingestion(
    connection: psycopg.Connection,
    *,
    initial_date: date,
    today: date,
    overlap_days: int = 3,
    history_batch_size: int = 20,
    max_history_batches: int = 30,
) -> IngestionRefreshResult:
    """Refresh scope publications and resolve missing predecessor references."""
    for name, value in (
        ("overlap_days", overlap_days),
        ("history_batch_size", history_batch_size),
        ("max_history_batches", max_history_batches),
    ):
        if type(value) is not int or value < 1:
            raise ValueError(f"{name} must be a positive integer")

    if (
        not connection.autocommit
        or connection.info.transaction_status != TransactionStatus.IDLE
    ):
        raise ValueError(
            "Refresh requires an idle connection with autocommit enabled"
        )

    incremental_run_id = run_incremental(
        connection,
        initial_date=initial_date,
        today=today,
        overlap_days=overlap_days,
    )

    if incremental_run_id is not None:
        _require_successful_run(connection, incremental_run_id)

    missing = set(find_missing_predecessor_publications(connection))
    history_run_ids = []

    for batch_number in range(1, max_history_batches + 1):
        if not missing:
            break

        logger.info(
            "History batch %s/%s; missing predecessors: %s",
            batch_number,
            max_history_batches,
            len(missing),
        )

        run_id = run_history(
            connection,
            max_notices=history_batch_size,
        )

        if run_id is None:
            raise RuntimeError(
                "History returned no run despite missing predecessors"
            )

        _require_successful_run(connection, run_id)
        history_run_ids.append(run_id)

        remaining = set(find_missing_predecessor_publications(connection))

        # Resolving a reference may reveal another one deeper in the chain.
        if not missing.difference(remaining):
            raise RuntimeError(
                f"History run {run_id} resolved no previously missing references"
            )

        missing = remaining

    if missing:
        raise RuntimeError(
            f"History batch limit reached; "
            f"{len(missing)} publications still require a predecessor"
        )

    return IngestionRefreshResult(
        incremental_run_id=incremental_run_id,
        history_run_ids=tuple(history_run_ids),
    )