import argparse
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from tender_intelligence.database import connect_reporting_database
from tender_intelligence.reporting import (
    read_dashboard_snapshot,
    write_dashboard_snapshot,
)


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(
        description="Export analytical models for the public dashboard."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/dashboard.json"),
        help="Output path, relative to the project root unless absolute.",
    )
    args = parser.parse_args()

    load_dotenv(
        project_root / ".env",
        override=False,
        interpolate=False,
    )

    destination = args.output
    if not destination.is_absolute():
        destination = project_root / destination

    with connect_reporting_database() as connection:
        identity = connection.execute(
            "SELECT current_database(), current_user"
        ).fetchone()
        snapshot = read_dashboard_snapshot(connection)

    write_dashboard_snapshot(
        snapshot,
        destination,
        generated_at=datetime.now(UTC),
    )

    print(f"Database: {identity[0]}")
    print(f"User: {identity[1]}")
    print(f"Scope notices: {snapshot['scope']['notice_count']}")
    print(f"Lot observations: {len(snapshot['observations'])}")
    print(f"Exported: {destination}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
