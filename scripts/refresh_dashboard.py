import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

from dotenv import load_dotenv

from tender_intelligence.database import (
    connect_database,
    connect_reporting_database,
)
from tender_intelligence.refresh import refresh_ingestion
from tender_intelligence.reporting import (
    read_dashboard_snapshot,
    write_dashboard_snapshot,
)

logger = logging.getLogger(__name__)


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(
        description="Refresh TED data and rebuild the local dashboard snapshot."
    )
    parser.add_argument(
        "--initial-date",
        type=date.fromisoformat,
        default=date(2026, 10, 20),
    )
    parser.add_argument("--overlap-days", type=int, default=3)
    parser.add_argument("--history-batch-size", type=int, default=20)
    parser.add_argument("--max-history-batches", type=int, default=30)
    args = parser.parse_args()

    for name in (
        "overlap_days",
        "history_batch_size",
        "max_history_batches",
    ):
        if getattr(args, name) < 1:
            parser.error(f"--{name.replace('_', '-')} must be positive")

    today = datetime.now(UTC).date()
    if args.initial_date >= today:
        parser.error("--initial-date must be earlier than today in UTC")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    load_dotenv(
        project_root / ".env",
        override=False,
        interpolate=False,
    )

    stage = "configuration checks"

    try:
        node = shutil.which("node")
        if node is None:
            raise RuntimeError("Node.js was not found in PATH")

        dbt_executable = (
            project_root
            / ".venv-dbt"
            / ("Scripts/dbt.exe" if os.name == "nt" else "bin/dbt")
        )
        if not dbt_executable.is_file():
            raise FileNotFoundError("dbt executable not found in .venv-dbt")

        subprocess.run(
            [node, "--version"],
            cwd=project_root,
            check=True,
            timeout=30,
        )

        # Validate reporting credentials before starting network ingestion.
        with connect_reporting_database() as connection:
            identity = connection.execute(
                "SELECT current_database(), current_user"
            ).fetchone()

            if identity != ("tender_intelligence", "tender_reporter"):
                raise RuntimeError(
                    "Expected the working database and tender_reporter role"
                )

        subprocess.run(
            [
                sys.executable,
                str(project_root / "scripts/run_dbt.py"),
                "debug",
                "--target",
                "dev",
            ],
            cwd=project_root,
            check=True,
            timeout=120,
        )

        stage = "incremental ingestion and predecessor history"
        logger.info("Starting %s", stage)

        with connect_database() as connection:
            identity = connection.execute(
                "SELECT current_database(), current_user"
            ).fetchone()

            if identity != ("tender_intelligence", "tender_app"):
                raise RuntimeError("Expected the working database and tender_app role")

            result = refresh_ingestion(
                connection,
                initial_date=args.initial_date,
                today=today,
                overlap_days=args.overlap_days,
                history_batch_size=args.history_batch_size,
                max_history_batches=args.max_history_batches,
            )

        stage = "dbt build and tests"
        logger.info("Starting %s", stage)

        subprocess.run(
            [
                sys.executable,
                str(project_root / "scripts/run_dbt.py"),
                "build",
                "--target",
                "dev",
            ],
            cwd=project_root,
            check=True,
            timeout=600,
        )

        destination = project_root / "dashboard/data/dashboard.json"
        destination.parent.mkdir(parents=True, exist_ok=True)

        # The candidate stays on the same filesystem as the final snapshot.
        with tempfile.TemporaryDirectory(
            prefix=".refresh-",
            dir=destination.parent,
        ) as temporary_directory:
            candidate = Path(temporary_directory) / "dashboard.json"

            stage = "dashboard export"
            logger.info("Starting %s", stage)

            with connect_reporting_database() as connection:
                snapshot = read_dashboard_snapshot(connection)

            write_dashboard_snapshot(
                snapshot,
                candidate,
                generated_at=datetime.now(UTC),
            )

            stage = "dashboard metric validation"
            logger.info("Starting %s", stage)

            subprocess.run(
                [
                    node,
                    str(project_root / "scripts/check_dashboard_metrics.mjs"),
                    str(candidate),
                ],
                cwd=project_root,
                check=True,
                timeout=60,
            )

            stage = "dashboard snapshot replacement"
            os.replace(candidate, destination)

        print("\nLocal dashboard refreshed successfully")
        print(f"Incremental run: {result.incremental_run_id}")
        print(f"History runs: {list(result.history_run_ids)}")
        print(f"Scope notices: {snapshot['scope']['notice_count']}")
        print(f"Lot observations: {len(snapshot['observations'])}")
        print(f"Output: {destination}")

        return 0

    except Exception:
        logger.exception("Dashboard refresh failed during: %s", stage)
        logger.error("The dashboard snapshot was not replaced.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
