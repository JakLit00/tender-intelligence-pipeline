import logging
from datetime import date
from urllib.error import URLError

import psycopg
from psycopg.pq import TransactionStatus

from tender_intelligence.ingestion import register_search_results
from tender_intelligence.normalization import normalize_publication_number
from tender_intelligence.processing import process_notice
from tender_intelligence.run_tracking import (
    fail_run,
    finish_run,
    link_run_notice,
    record_notice_outcome,
    start_run,
)
from tender_intelligence.storage import save_notice_xml
from tender_intelligence.ted_client import (
    fetch_all_notices,
    fetch_notice_xml,
)


logger = logging.getLogger(__name__)


def run_backfill(
    conn: psycopg.Connection,
    *,
    date_from: date,
    date_to: date,
) -> int:
    """Run a historical search and process its publications."""
    if (
        not conn.autocommit
        or conn.info.transaction_status != TransactionStatus.IDLE
    ):
        raise ValueError(
            "Backfill requires an idle connection with autocommit enabled"
        )

    run_id = start_run(
        conn,
        run_mode="backfill",
        date_from=date_from,
        date_to=date_to,
    )
    logger.info("Started backfill run %s", run_id)

    try:
        query = (
            "buyer-country = POL "
            "AND classification-cpv = 72* "
            "AND notice-type = cn-standard "
            f"AND publication-date >= {date_from:%Y%m%d} "
            f"AND publication-date <= {date_to:%Y%m%d}"
        )
        notices = fetch_all_notices(query)

        # Register the complete work list before processing individual notices.
        with conn.transaction():
            register_search_results(conn, notices)

            for notice in notices:
                link_run_notice(
                    conn,
                    run_id=run_id,
                    publication_number=notice["publication-number"],
                )

        for notice in notices:
            publication_number = normalize_publication_number(
                notice["publication-number"]
            )

            try:
                xml_content = fetch_notice_xml(publication_number)
            except (URLError, TimeoutError, ValueError) as exc:
                record_notice_outcome(
                    conn,
                    run_id=run_id,
                    publication_number=publication_number,
                    outcome="failed",
                    error_message=f"{type(exc).__name__}: {exc}",
                )
                logger.warning(
                    "Run %s: download failed for %s: %s",
                    run_id,
                    publication_number,
                    exc,
                )
                continue

            # Preserve downloaded XML even if later processing fails.
            save_notice_xml(conn, publication_number, xml_content)

            with conn.transaction():
                outcome = process_notice(conn, publication_number)
                error_message = None

                if outcome == "failed":
                    row = conn.execute(
                        """
                        SELECT last_error
                        FROM raw.notices
                        WHERE publication_number = %s
                        """,
                        (publication_number,),
                    ).fetchone()

                    if row is None:
                        raise RuntimeError(
                            "Processed publication is missing from raw.notices"
                        )

                    error_message = row[0]

                record_notice_outcome(
                    conn,
                    run_id=run_id,
                    publication_number=publication_number,
                    outcome=outcome,
                    error_message=error_message,
                )

            logger.info(
                "Run %s: %s -> %s",
                run_id,
                publication_number,
                outcome,
            )

        status = finish_run(conn, run_id=run_id)

    except Exception as exc:
        # Tracking failure must not replace the original pipeline exception.
        try:
            fail_run(
                conn,
                run_id=run_id,
                error_message=f"{type(exc).__name__}: {exc}",
            )
        except Exception:
            logger.exception("Could not mark run %s as failed", run_id)
        raise

    logger.info("Finished run %s with status %s", run_id, status)
    return run_id