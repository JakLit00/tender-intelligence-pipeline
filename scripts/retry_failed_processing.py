from pathlib import Path

from dotenv import load_dotenv

from tender_intelligence.database import connect_database
from tender_intelligence.processing import process_notice
from tender_intelligence.run_tracking import (
    fail_run,
    finish_run,
    link_run_notice,
    record_notice_outcome,
    start_run,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_RUN_ID = 5


def main() -> None:
    load_dotenv(
        PROJECT_ROOT / ".env",
        override=False,
        interpolate=False,
    )

    with connect_database() as conn:
        identity = conn.execute(
            "SELECT current_database(), current_user"
        ).fetchone()

        if identity != ("tender_intelligence", "tender_app"):
            raise RuntimeError(
                "Expected the working database and application role"
            )

        source_run = conn.execute(
            """
            SELECT date_from, date_to, status
            FROM ops.pipeline_runs
            WHERE run_id = %s
            """,
            (SOURCE_RUN_ID,),
        ).fetchone()

        if source_run is None:
            raise ValueError(f"Source run not found: {SOURCE_RUN_ID}")

        if source_run[2] == "running":
            raise ValueError("Source run has not finished")

        publications = conn.execute(
            """
            SELECT r.publication_number, n.xml_content IS NOT NULL
            FROM ops.run_notices AS r
            JOIN raw.notices AS n USING (publication_number)
            WHERE r.run_id = %s AND r.outcome = 'failed'
            ORDER BY r.publication_number
            """,
            (SOURCE_RUN_ID,),
        ).fetchall()

        if not publications:
            print("No failed publications to retry")
            return

        missing_xml = [
            number for number, has_xml in publications if not has_xml
        ]
        if missing_xml:
            raise ValueError(
                "Cannot retry without stored XML: "
                + ", ".join(missing_xml)
            )

        run_id = start_run(
            conn,
            run_mode="retry",
            date_from=source_run[0],
            date_to=source_run[1],
        )
        print(f"Retry run: {run_id}; source run: {SOURCE_RUN_ID}")

        try:
            with conn.transaction():
                for number, _ in publications:
                    link_run_notice(
                        conn,
                        run_id=run_id,
                        publication_number=number,
                    )

            for number, _ in publications:
                with conn.transaction():
                    outcome = process_notice(conn, number)
                    error_message = None

                    if outcome == "failed":
                        row = conn.execute(
                            """
                            SELECT last_error
                            FROM raw.notices
                            WHERE publication_number = %s
                            """,
                            (number,),
                        ).fetchone()

                        if row is None:
                            raise RuntimeError(
                                f"Raw publication disappeared: {number}"
                            )

                        error_message = row[0]

                    record_notice_outcome(
                        conn,
                        run_id=run_id,
                        publication_number=number,
                        outcome=outcome,
                        error_message=error_message,
                    )

                print(f"{number}: {outcome}")

            status = finish_run(conn, run_id=run_id)

        except Exception as exc:
            try:
                fail_run(
                    conn,
                    run_id=run_id,
                    error_message=f"{type(exc).__name__}: {exc}",
                )
            except Exception as tracking_error:
                print(f"Could not record run failure: {tracking_error}")
            raise

        flagged_lots = conn.execute(
            """
            SELECT count(*)
            FROM staging.notice_lots AS l
            JOIN ops.run_notices AS r
                ON r.publication_number = l.publication_number
            WHERE r.run_id = %s
              AND l.submission_deadline_quality_issue =
                  'conflicting_timezone_offsets'
              AND l.submission_deadline_at IS NULL
            """,
            (run_id,),
        ).fetchone()

        print(f"Status: {status}")
        print(f"Lots with conflicting offsets and no exact deadline: {flagged_lots[0]}")

        if status != "succeeded":
            raise SystemExit(1)


if __name__ == "__main__":
    main()