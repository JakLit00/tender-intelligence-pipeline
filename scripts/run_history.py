import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv

from tender_intelligence.database import connect_database
from tender_intelligence.history import run_history
from tender_intelligence.predecessors import (
    find_missing_predecessor_publications,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve a bounded batch of missing TED predecessors."
    )
    parser.add_argument("--max-notices", type=int, default=20)
    args = parser.parse_args()

    if args.max_notices < 1:
        parser.error("--max-notices must be a positive integer")

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
            raise RuntimeError("Expected the working database and tender_app role")

        run_id = run_history(
            connection,
            max_notices=args.max_notices,
        )

        if run_id is None:
            print("No missing predecessors to resolve.")
            return 0

        run = connection.execute(
            """
            SELECT status, started_at, finished_at, error_message
            FROM ops.pipeline_runs
            WHERE run_id = %s
            """,
            (run_id,),
        ).fetchone()

        if run is None:
            raise RuntimeError("History run was not found")

        status, started_at, finished_at, error_message = run
        print(f"\nRun ID: {run_id}")
        print(f"Status: {status}")
        print(f"Started: {started_at}")
        print(f"Finished: {finished_at}")

        if error_message:
            print(f"Error: {error_message}")

        outcomes = connection.execute(
            """
            SELECT publication_number, outcome, error_message
            FROM ops.run_notices
            WHERE run_id = %s
            ORDER BY publication_number
            """,
            (run_id,),
        ).fetchall()

        for publication_number, outcome, error in outcomes:
            print(f"{publication_number}: {outcome}")
            if error:
                print(f"  {error}")

        remaining = find_missing_predecessor_publications(connection)
        print(f"Notices still missing a predecessor: {len(remaining)}")

    return 0 if status == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
