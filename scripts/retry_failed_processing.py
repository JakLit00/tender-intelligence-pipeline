import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv

from tender_intelligence.database import connect_database
from tender_intelligence.retry import retry_processing


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Retry failed publications using stored XML only. "
            "For downloads rerun backfill/incremental; for history use run_history.py."
        )
    )
    parser.add_argument("--source-run-id", required=True, type=int)
    args = parser.parse_args()
    if args.source_run_id < 1:
        parser.error("--source-run-id must be positive")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    load_dotenv(
        Path(__file__).resolve().parents[1] / ".env",
        override=False,
        interpolate=False,
    )
    with connect_database() as connection:
        identity = connection.execute(
            "SELECT current_database(), current_user"
        ).fetchone()
        if identity != ("tender_intelligence", "tender_app"):
            raise RuntimeError("Expected the working database and application role")
        run_id = retry_processing(connection, source_run_id=args.source_run_id)
        if run_id is None:
            print("No failed publications to retry")
            return 0
        row = connection.execute(
            "SELECT status FROM ops.pipeline_runs WHERE run_id = %s", (run_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError("Retry run was not found")
        print(
            f"Retry run: {run_id}; source run: {args.source_run_id}; status: {row[0]}"
        )
        return 0 if row[0] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
