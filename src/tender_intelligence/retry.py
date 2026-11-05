import logging

from psycopg import Connection
from psycopg.pq import TransactionStatus

from tender_intelligence.processing import process_notice
from tender_intelligence.run_tracking import (
    fail_run,
    finish_run,
    link_run_notice,
    record_notice_outcome,
    start_run,
)

logger = logging.getLogger(__name__)


def retry_processing(connection: Connection, *, source_run_id: int) -> int | None:
    """Retry failed publications using stored XML only; never download data."""
    if type(source_run_id) is not int or source_run_id < 1:
        raise ValueError("source_run_id must be a positive integer")
    if (
        not connection.autocommit
        or connection.info.transaction_status != TransactionStatus.IDLE
    ):
        raise ValueError("Retry requires an idle connection with autocommit enabled")

    source = connection.execute(
        """
        SELECT date_from, date_to, status, run_mode
        FROM ops.pipeline_runs WHERE run_id = %s
        """,
        (source_run_id,),
    ).fetchone()
    if source is None:
        raise ValueError(f"Source run not found: {source_run_id}")
    if source[2] == "running":
        raise ValueError("Source run has not finished")
    if source[3] == "history":
        # History outcomes identify the referring notice, not the failed predecessor.
        raise ValueError("Use run_history.py to retry predecessor retrieval")

    publications = connection.execute(
        """
        SELECT item.publication_number, notice.xml_content IS NOT NULL
        FROM ops.run_notices AS item
        JOIN raw.notices AS notice USING (publication_number)
        WHERE item.run_id = %s AND item.outcome = 'failed'
        ORDER BY item.publication_number
        """,
        (source_run_id,),
    ).fetchall()
    if not publications:
        return None

    run_id = start_run(
        connection, run_mode="retry", date_from=source[0], date_to=source[1]
    )
    try:
        with connection.transaction():
            for number, _ in publications:
                link_run_notice(connection, run_id=run_id, publication_number=number)

        for number, has_xml in publications:
            with connection.transaction():
                if not has_xml:
                    outcome = "failed"
                    error = (
                        "No stored XML; rerun backfill or incremental to download it"
                    )
                else:
                    outcome = process_notice(connection, number)
                    error = None
                    if outcome == "failed":
                        row = connection.execute(
                            "SELECT last_error FROM raw.notices "
                            "WHERE publication_number = %s",
                            (number,),
                        ).fetchone()
                        if row is None or not row[0]:
                            raise RuntimeError(
                                "Failed publication has no recorded error"
                            )
                        error = row[0]
                record_notice_outcome(
                    connection,
                    run_id=run_id,
                    publication_number=number,
                    outcome=outcome,
                    error_message=error,
                )
            logger.info("Retry run %s: %s -> %s", run_id, number, outcome)

        finish_run(connection, run_id=run_id)
    except Exception as exc:
        try:
            fail_run(
                connection, run_id=run_id, error_message=f"{type(exc).__name__}: {exc}"
            )
        except Exception:
            logger.exception("Could not mark retry run %s as failed", run_id)
        raise
    return run_id
