import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from tender_intelligence.predecessors import find_missing_predecessor_publications
from tender_intelligence.preparation import prepare_notice
from tender_intelligence.processing import process_notice
from tender_intelligence.reporting import (
    read_dashboard_snapshot,
    write_dashboard_snapshot,
)
from tender_intelligence.storage import register_notice, save_notice_xml

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = b"<efbc:ChangedNoticeIdentifier>706539-2026</efbc:ChangedNoticeIdentifier>"
NOTICE_ID = b"8ac273c6-7603-4ad1-b9a2-8ed027ed773f"


def seed(connection, content, number, source="scope_search"):
    bundle = prepare_notice(content, expected_publication_number=number)
    register_notice(
        connection,
        publication_number=number,
        publication_date=bundle.notice.publication_date,
        search_metadata={
            "publication-number": number,
            "notice-title": {"pol": "Synthetic procurement"},
            "buyer-name": {"pol": ["Test buyer"]},
        },
        discovery_source=source,
    )
    save_notice_xml(connection, number, content)
    assert process_notice(connection, number) == "processed"


def reporter():
    connection = psycopg.connect(
        host="127.0.0.1",
        port=5435,
        dbname="tender_intelligence_test",
        user="tender_reporter",
        password="local_test_report_password",
        connect_timeout=5,
        autocommit=True,
    )
    if connection.execute("SELECT current_database(),current_user").fetchone() != (
        "tender_intelligence_test",
        "tender_reporter",
    ):
        connection.close()
        raise RuntimeError("Unexpected reporting test database")
    return connection


def test_nonempty_sql_export_passes_real_javascript_validator(
    dbt_models, pipeline_connection, notice_xml, tmp_path
):
    cases = [
        "extended",
        "fractional",
        "shortened",
        "unchanged",
        "no_reference",
        "unresolved_predecessor",
        "missing_predecessor_lot",
        "quality_issue",
        "missing_exact_deadline",
    ]
    for i, case in enumerate(cases):
        current = f"{800001 + i}-2026"
        previous = f"{700001 + i}-2026"
        current_xml = (
            notice_xml.replace(b"722762-2026", current.encode())
            .replace(b"706539-2026", previous.encode())
            .replace(NOTICE_ID, str(uuid4()).encode())
        )
        previous_xml = (
            notice_xml.replace(REFERENCE, b"")
            .replace(b"722762-2026", previous.encode())
            .replace(NOTICE_ID, str(uuid4()).encode())
        )
        if case == "extended":
            current_xml = current_xml.replace(b"2026-11-03", b"2026-11-04")
        if case == "fractional":
            current_xml = current_xml.replace(b"09:00:00", b"09:30:00")
        if case == "shortened":
            current_xml = current_xml.replace(b"2026-11-03", b"2026-11-02")
        if case == "no_reference":
            current_xml = current_xml.replace(
                REFERENCE.replace(b"706539-2026", previous.encode()), b""
            )
        if case == "missing_predecessor_lot":
            previous_xml = previous_xml.replace(b"LOT-0001", b"LOT-0002")
        if case == "quality_issue":
            current_xml = current_xml.replace(b"2026-11-03+01:00", b"2026-11-03Z")
        if case == "missing_exact_deadline":
            current_xml = current_xml.replace(
                b"<cbc:EndTime>09:00:00+01:00</cbc:EndTime>", b""
            )
        if case not in ("no_reference", "unresolved_predecessor"):
            seed(pipeline_connection, previous_xml, previous, "predecessor")
        seed(pipeline_connection, current_xml, current)

    with reporter() as connection:
        snapshot = read_dashboard_snapshot(connection)
    assert snapshot["scope"]["notice_count"] == 9
    summary = snapshot["summary"]
    assert summary["comparable_lot_observations"] == 4
    assert summary["matched_lot_observations"] == 6
    assert summary["extension_rate_pct"] == 50
    assert float(summary["comparison_coverage_pct"]) == 66.67
    assert summary["median_extension_hours"] == 12.25
    assert [row["deadline_change_status"] for row in snapshot["observations"]] == [
        "extended" if case == "fractional" else case for case in cases
    ]
    destination = tmp_path / "dashboard.json"
    write_dashboard_snapshot(
        snapshot, destination, generated_at=datetime(2026, 11, 5, tzinfo=UTC)
    )
    result = subprocess.run(
        ["node", str(ROOT / "scripts/check_dashboard_metrics.mjs"), str(destination)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "metrics match" in result.stdout


@pytest.mark.parametrize("status", ["pending", "failed"])
def test_history_and_dbt_agree_on_stale_predecessor_and_current(
    dbt_models, pipeline_connection, notice_xml, status
):
    c = pipeline_connection
    previous = (
        notice_xml.replace(REFERENCE, b"")
        .replace(b"722762-2026", b"706539-2026")
        .replace(NOTICE_ID, str(uuid4()).encode())
    )
    seed(c, notice_xml, "722762-2026")
    seed(c, previous, "706539-2026", "predecessor")
    save_notice_xml(c, "706539-2026", b"<broken>")
    if status == "failed":
        assert process_notice(c, "706539-2026") == "failed"
    assert find_missing_predecessor_publications(c) == ["722762-2026"]
    with reporter() as connection:
        assert connection.execute(
            "SELECT match_status FROM analytics.int_notice_predecessors"
        ).fetchall() == [("not_found",)]
    save_notice_xml(c, "722762-2026", b"<broken>")
    if status == "failed":
        assert process_notice(c, "722762-2026") == "failed"
    assert find_missing_predecessor_publications(c) == []
    with reporter() as connection:
        assert connection.execute(
            "SELECT count(*) FROM analytics.int_scope_notices"
        ).fetchone() == (0,)


@pytest.mark.parametrize("reference_type", ["publication_number", "notice_version"])
def test_dbt_build_fails_on_cycles(
    dbt_models, dbt_runner, pipeline_connection, notice_xml, reference_type
):
    previous_id = str(uuid4()).encode()
    current = notice_xml
    previous = notice_xml.replace(b"722762-2026", b"706539-2026").replace(
        NOTICE_ID, previous_id
    )
    previous = previous.replace(
        REFERENCE, REFERENCE.replace(b"706539-2026", b"722762-2026")
    )
    if reference_type == "notice_version":
        current = current.replace(
            REFERENCE, REFERENCE.replace(b"706539-2026", previous_id + b"-01")
        )
        previous = previous.replace(
            REFERENCE.replace(b"706539-2026", b"722762-2026"),
            REFERENCE.replace(b"706539-2026", NOTICE_ID + b"-01"),
        )
    seed(pipeline_connection, current, "722762-2026")
    seed(pipeline_connection, previous, "706539-2026", "predecessor")
    run, target = dbt_runner
    result = run("build")
    assert result.returncode != 0
    results = json.loads((target / "run_results.json").read_text(encoding="utf-8"))[
        "results"
    ]
    cycle_results = [
        item for item in results if "no_predecessor_cycles" in item["unique_id"]
    ]
    assert len(cycle_results) == 1
    assert cycle_results[0]["status"] == "fail"
    assert cycle_results[0]["failures"] > 0
