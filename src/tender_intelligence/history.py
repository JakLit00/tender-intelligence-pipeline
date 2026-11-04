import logging
from urllib.error import URLError
from xml.etree.ElementTree import ParseError

from psycopg import Connection
from psycopg.pq import TransactionStatus

from tender_intelligence.predecessors import (
    download_predecessor,
    find_missing_predecessor_publications,
    persist_predecessor,
)
from tender_intelligence.preparation import prepare_notice
from tender_intelligence.run_tracking import (
    fail_run,
    finish_run,
    link_run_notice,
    record_notice_outcome,
    start_run,
)


logger = logging.getLogger(__name__)


def run_history(
    connection: Connection,
    *,
    max_notices: int = 20,
) -> int | None:
    """Resolve one bounded batch of missing predecessor references."""
    if type(max_notices) is not int or max_notices < 1:
        raise ValueError("max_notices must be a positive integer")

    if (
        not connection.autocommit
        or connection.info.transaction_status != TransactionStatus.IDLE
    ):
        raise ValueError(
            "History requires an idle connection with autocommit enabled"
        )

    missing = find_missing_predecessor_publications(connection)
    if not missing:
        logger.info("No missing predecessors to resolve")
        return None

    # Prefer notices not attempted before, then the least recently attempted.
    candidates = connection.execute(
        """
        SELECT
            notice.publication_number,
            notice.publication_date
        FROM staging.notices AS notice
        LEFT JOIN (
            SELECT
                item.publication_number,
                max(run.started_at) AS last_attempt_at
            FROM ops.run_notices AS item
            JOIN ops.pipeline_runs AS run USING (run_id)
            WHERE run.run_mode = 'history'
            GROUP BY item.publication_number
        ) AS history USING (publication_number)
        WHERE notice.publication_number = ANY(%s)
        ORDER BY
            history.last_attempt_at ASC NULLS FIRST,
            notice.publication_number
        LIMIT %s
        """,
        (missing, max_notices),
    ).fetchall()

    if not candidates:
        return None

    dates = [row[1] for row in candidates]
    run_id = start_run(
        connection,
        run_mode="history",
        date_from=min(dates),
        date_to=max(dates),
    )
    logger.info(
        "Started history run %s for %s notices",
        run_id,
        len(candidates),
    )

    try:
        with connection.transaction():
            for publication_number, _ in candidates:
                link_run_notice(
                    connection,
                    run_id=run_id,
                    publication_number=publication_number,
                )

        for publication_number, _ in candidates:
            try:
                row = connection.execute(
                    """
                    SELECT xml_content, processing_status
                    FROM raw.notices
                    WHERE publication_number = %s
                    """,
                    (publication_number,),
                ).fetchone()

                if row is None or row[0] is None or row[1] != "succeeded":
                    raise ValueError(
                        "Current notice requires successfully processed XML"
                    )

                current = prepare_notice(
                    row[0],
                    expected_publication_number=publication_number,
                ).notice

                # Network requests run outside database transactions.
                predecessor = download_predecessor(current)
                if predecessor is None:
                    raise ValueError("Predecessor was not found in TED")

            except (URLError, TimeoutError, ValueError, ParseError) as exc:
                record_notice_outcome(
                    connection,
                    run_id=run_id,
                    publication_number=publication_number,
                    outcome="failed",
                    error_message=f"{type(exc).__name__}: {exc}",
                )
                logger.warning(
                    "History run %s: %s failed: %s",
                    run_id,
                    publication_number,
                    exc,
                )
                continue

            with connection.transaction():
                outcome = persist_predecessor(connection, predecessor)
                error_message = None

                if outcome == "failed":
                    error_row = connection.execute(
                        """
                        SELECT last_error
                        FROM raw.notices
                        WHERE publication_number = %s
                        """,
                        (predecessor.bundle.notice.publication_number,),
                    ).fetchone()

                    if error_row is None or not error_row[0]:
                        raise RuntimeError(
                            "Failed predecessor has no recorded error"
                        )
                    error_message = error_row[0]

                record_notice_outcome(
                    connection,
                    run_id=run_id,
                    publication_number=publication_number,
                    outcome=outcome,
                    error_message=error_message,
                )

            logger.info(
                "History run %s: %s -> %s: %s",
                run_id,
                publication_number,
                predecessor.bundle.notice.publication_number,
                outcome,
            )

        status = finish_run(connection, run_id=run_id)

    except Exception as exc:
        try:
            fail_run(
                connection,
                run_id=run_id,
                error_message=f"{type(exc).__name__}: {exc}",
            )
        except Exception:
            logger.exception("Could not mark history run %s as failed", run_id)
        raise

    logger.info("Finished history run %s with status %s", run_id, status)
    return run_id