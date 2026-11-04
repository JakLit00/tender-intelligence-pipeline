import argparse
import logging
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from tender_intelligence.database import connect_database
from tender_intelligence.pipeline import run_backfill


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill Polish IT contract notices from TED."
    )
    parser.add_argument("--date-from", required=True, type=date.fromisoformat)
    parser.add_argument("--date-to", required=True, type=date.fromisoformat)
    args = parser.parse_args()

    if args.date_to < args.date_from:
        parser.error("--date-to must not be earlier than --date-from")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
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

        run_id = run_backfill(
            conn,
            date_from=args.date_from,
            date_to=args.date_to,
        )

        run = conn.execute(
            """
            SELECT status, started_at, finished_at, error_message
            FROM ops.pipeline_runs
            WHERE run_id = %s
            """,
            (run_id,),
        ).fetchone()

        if run is None:
            raise RuntimeError("Completed run is missing from the database")

        print(f"\nRun ID: {run_id}")
        print(f"Status: {run[0]}")
        print(f"Started: {run[1]}")
        print(f"Finished: {run[2]}")
        print(f"Error: {run[3]}")

        outcomes = conn.execute(
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

        if run[0] != "succeeded":
            raise SystemExit(1)


if __name__ == "__main__":
    main()