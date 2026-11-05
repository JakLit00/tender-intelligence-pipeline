import json
import math
import os
import tempfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row


def read_dashboard_snapshot(
    connection: psycopg.Connection,
) -> dict[str, Any]:
    """Read dashboard data from one consistent database snapshot."""
    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise ValueError("Dashboard export requires an idle connection")

    with connection.transaction():
        with connection.cursor(row_factory=dict_row) as cursor:
            # Keep all queries on the same snapshot, even during concurrent writes.
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")

            cursor.execute(
                """
                SELECT
                    publication_number,
                    lot_id,
                    procedure_id,
                    publication_date,
                    notice_title,
                    buyer_names,
                    notice_url,
                    predecessor_publication_number,
                    predecessor_match_status,
                    predecessor_lot_found,
                    previous_deadline_date,
                    current_deadline_date,
                    previous_deadline_at,
                    current_deadline_at,
                    previous_quality_issue,
                    current_quality_issue,
                    deadline_change_status,
                    deadline_change_hours
                FROM analytics.mart_lot_deadline_changes
                ORDER BY publication_date, publication_number, lot_id
                """
            )
            observations = cursor.fetchall()

            cursor.execute(
                """
                SELECT
                    total_lot_observations,
                    matched_lot_observations,
                    comparable_lot_observations,
                    extended_lot_observations,
                    shortened_lot_observations,
                    unchanged_lot_observations,
                    quality_issue_lot_observations,
                    missing_deadline_lot_observations,
                    comparison_coverage_pct,
                    extension_rate_pct,
                    median_extension_hours
                FROM analytics.mart_deadline_change_summary
                """
            )
            summary_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT
                    COUNT(*) AS notice_count,
                    MIN(publication_date) AS first_publication_date,
                    MAX(publication_date) AS last_publication_date
                FROM analytics.int_scope_notices
                """
            )
            scope = cursor.fetchone()

    if len(summary_rows) != 1:
        raise ValueError("Expected exactly one dashboard summary row")

    summary = summary_rows[0]

    if summary["total_lot_observations"] != len(observations):
        raise ValueError("Dashboard summary and observation counts differ")

    if scope is None:
        raise ValueError("Dashboard scope query returned no row")

    return {
        "scope": scope,
        "summary": summary,
        "observations": observations,
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError("Dashboard timestamps must include a timezone")

        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, Decimal):
        number = float(value)

        if not math.isfinite(number):
            raise ValueError("Dashboard numbers must be finite")

        return number

    if isinstance(value, UUID):
        return str(value)

    raise TypeError(f"Unsupported dashboard value type: {type(value).__name__}")


def serialize_dashboard_snapshot(
    snapshot: dict[str, Any],
    *,
    generated_at: datetime,
) -> str:
    """Serialize dashboard data with an explicit format version."""
    payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        **snapshot,
    }

    return (
        json.dumps(
            payload,
            default=_json_default,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        + "\n"
    )


def write_dashboard_snapshot(
    snapshot: dict[str, Any],
    destination: Path,
    *,
    generated_at: datetime,
) -> None:
    """Replace the dashboard file only after serialization and writing succeed."""
    content = serialize_dashboard_snapshot(
        snapshot,
        generated_at=generated_at,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = None

    try:
        # Keep the temporary file on the same filesystem for atomic replacement.
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
