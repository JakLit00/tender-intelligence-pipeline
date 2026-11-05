import json
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from tender_intelligence.reporting import serialize_dashboard_snapshot


def test_serializes_dates_numbers_and_missing_values():
    snapshot = {
        "scope": {"first_publication_date": date(2026, 10, 20)},
        "summary": {"extension_rate_pct": Decimal("98.20")},
        "observations": [
            {
                "buyer_names": "Centralna Komisja Egzaminacyjna",
                "deadline_change_hours": Decimal("1.5"),
                "current_deadline_at": None,
            }
        ],
    }

    result = json.loads(
        serialize_dashboard_snapshot(
            snapshot,
            generated_at=datetime(2026, 11, 5, 12, tzinfo=UTC),
        )
    )

    assert result["schema_version"] == 1
    assert result["generated_at"] == "2026-11-05T12:00:00Z"
    assert result["scope"]["first_publication_date"] == "2026-10-20"
    assert result["summary"]["extension_rate_pct"] == 98.2
    assert result["observations"][0]["deadline_change_hours"] == 1.5
    assert result["observations"][0]["current_deadline_at"] is None


def test_converts_timestamp_to_utc():
    local_time = datetime(
        2026,
        11,
        3,
        9,
        tzinfo=timezone(timedelta(hours=1)),
    )

    result = json.loads(
        serialize_dashboard_snapshot(
            {"observations": [{"current_deadline_at": local_time}]},
            generated_at=datetime(2026, 11, 5, tzinfo=UTC),
        )
    )

    assert result["observations"][0]["current_deadline_at"] == "2026-11-03T08:00:00Z"


def test_rejects_timestamp_without_timezone():
    with pytest.raises(ValueError, match="include a timezone"):
        serialize_dashboard_snapshot(
            {},
            generated_at=datetime(2026, 11, 5),
        )


@pytest.mark.parametrize(
    "value",
    [Decimal("NaN"), Decimal("Infinity"), float("nan")],
)
def test_rejects_non_finite_numbers(value):
    with pytest.raises(ValueError):
        serialize_dashboard_snapshot(
            {"summary": {"median_extension_hours": value}},
            generated_at=datetime(2026, 11, 5, tzinfo=UTC),
        )


def test_preserves_polish_characters():
    result = serialize_dashboard_snapshot(
        {"observations": [{"buyer_names": "Urząd Łódź"}]},
        generated_at=datetime(2026, 11, 5, tzinfo=UTC),
    )

    assert "Urząd Łódź" in result


def test_serializes_uuid_as_text():
    procedure_id = "4835bb55-6b3a-4579-81d8-b34df3e663ce"

    result = json.loads(
        serialize_dashboard_snapshot(
            {"observations": [{"procedure_id": UUID(procedure_id)}]},
            generated_at=datetime(2026, 11, 5, tzinfo=UTC),
        )
    )

    assert result["observations"][0]["procedure_id"] == procedure_id
