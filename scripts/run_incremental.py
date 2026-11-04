import argparse
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from tender_intelligence.database import connect_database
from tender_intelligence.pipeline import run_incremental


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest TED publications with an overlapping date window."
    )
    parser.add_argument(
        "--initial-date",
        type=date.fromisoformat,
        required=True,
    )
    parser.add_argument("--overlap-days", type=int, default=3)
    args = parser.parse_args()

    if args.overlap_days < 1:
        parser.error("--overlap-days must be a positive integer")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(
        project_root / ".env",
        override=False,
        interpolate=False,
    )

    with connect_database() as connection:
        identity = connection.execute(
            "SELECT current_database(), current_user"
        ).fetchone()

        if identity != ("tender_intelligence", "tender_app"):
            raise RuntimeError(
                "Expected the working database and tender_app role"
            )

        run_id = run_incremental(
            connection,
            initial_date=args.initial_date,
            today=datetime.now(timezone.utc).date(),
            overlap_days=args.overlap_days,
        )

        if run_id is None:
            print("No complete days available for incremental ingestion.")
            return 0

        run = connection.execute(
            """
            SELECT
                status,
                date_from,
                date_to,
                started_at,
                finished_at,
                error_message
            FROM ops.pipeline_runs
            WHERE run_id = %s
            """,
            (run_id,),
        ).fetchone()

        if run is None:
            raise RuntimeError("Incremental run was not found")

        status, date_from, date_to, started_at, finished_at, error = run

        print(f"\nRun ID: {run_id}")
        print(f"Status: {status}")
        print(f"Range: {date_from} to {date_to}")
        print(f"Started: {started_at}")
        print(f"Finished: {finished_at}")

        if error:
            print(f"Error: {error}")

        outcomes = connection.execute(
            """
            SELECT outcome, count(*)
            FROM ops.run_notices
            WHERE run_id = %s
            GROUP BY outcome
            ORDER BY outcome
            """,
            (run_id,),
        ).fetchall()

        for outcome, count in outcomes:
            print(f"{outcome}: {count}")

    return 0 if status == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())