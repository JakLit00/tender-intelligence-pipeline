import json
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from tender_intelligence.reporting import write_dashboard_snapshot

GENERATED_AT = datetime(2026, 11, 5, 12, tzinfo=UTC)


def test_creates_dashboard_file_and_parent_directory(tmp_path):
    destination = tmp_path / "data" / "dashboard.json"

    write_dashboard_snapshot(
        {"observations": [], "summary": {}, "scope": {}},
        destination,
        generated_at=GENERATED_AT,
    )

    result = json.loads(destination.read_text(encoding="utf-8"))

    assert result["schema_version"] == 1
    assert result["generated_at"] == "2026-11-05T12:00:00Z"
    assert result["observations"] == []
    assert list(destination.parent.iterdir()) == [destination]


def test_replaces_existing_file(tmp_path):
    destination = tmp_path / "dashboard.json"
    destination.write_text('{"old": true}', encoding="utf-8")

    write_dashboard_snapshot(
        {"observations": [{"buyer_names": "Urząd Łódź"}]},
        destination,
        generated_at=GENERATED_AT,
    )

    result = json.loads(destination.read_text(encoding="utf-8"))

    assert "old" not in result
    assert result["observations"][0]["buyer_names"] == "Urząd Łódź"


def test_preserves_existing_file_when_serialization_fails(tmp_path):
    destination = tmp_path / "dashboard.json"
    original = '{"old": true}\n'
    destination.write_text(original, encoding="utf-8")

    with pytest.raises(TypeError, match="Unsupported dashboard value type"):
        write_dashboard_snapshot(
            {"unsupported": object()},
            destination,
            generated_at=GENERATED_AT,
        )

    assert destination.read_text(encoding="utf-8") == original
    assert list(tmp_path.iterdir()) == [destination]


def test_preserves_existing_file_and_cleans_up_when_replace_fails(tmp_path):
    destination = tmp_path / "dashboard.json"
    original = '{"old": true}\n'
    destination.write_text(original, encoding="utf-8")

    with patch(
        "tender_intelligence.reporting.os.replace",
        side_effect=PermissionError("File replacement blocked"),
    ):
        with pytest.raises(PermissionError, match="replacement blocked"):
            write_dashboard_snapshot(
                {"observations": []},
                destination,
                generated_at=GENERATED_AT,
            )

    assert destination.read_text(encoding="utf-8") == original
    assert list(tmp_path.iterdir()) == [destination]
