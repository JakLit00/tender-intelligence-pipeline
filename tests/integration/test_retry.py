from datetime import date
from unittest.mock import patch

import pytest

from tender_intelligence.retry import retry_processing
from tender_intelligence.run_tracking import (
    finish_run,
    link_run_notice,
    record_notice_outcome,
    start_run,
)
from tender_intelligence.storage import register_notice, save_notice_xml


def failed_source(connection, numbers, mode="backfill"):
    run_id = start_run(
        connection,
        run_mode=mode,
        date_from=date(2026, 10, 20),
        date_to=date(2026, 10, 20),
    )
    for number in numbers:
        register_notice(
            connection,
            publication_number=number,
            publication_date=date(2026, 10, 20),
            search_metadata={},
        )
        link_run_notice(connection, run_id=run_id, publication_number=number)
        record_notice_outcome(
            connection,
            run_id=run_id,
            publication_number=number,
            outcome="failed",
            error_message="synthetic failure",
        )
    finish_run(connection, run_id=run_id)
    return run_id


def test_retry_continues_after_missing_xml_and_preserves_source_run(
    pipeline_connection, notice_xml
):
    c = pipeline_connection
    source = failed_source(c, ["100000-2026", "722762-2026", "999999-2026"])
    save_notice_xml(c, "722762-2026", notice_xml)
    save_notice_xml(c, "999999-2026", b"<broken>")
    with patch(
        "tender_intelligence.ted_client.urlopen",
        side_effect=AssertionError("retry must not download"),
    ):
        run_id = retry_processing(c, source_run_id=source)
    assert c.execute(
        "SELECT status FROM ops.pipeline_runs WHERE run_id=%s", (run_id,)
    ).fetchone() == ("partial",)
    assert c.execute(
        "SELECT publication_number,outcome FROM ops.run_notices WHERE run_id=%s ORDER BY publication_number",
        (run_id,),
    ).fetchall() == [
        ("100000-2026", "failed"),
        ("722762-2026", "processed"),
        ("999999-2026", "failed"),
    ]
    error = c.execute(
        "SELECT error_message FROM ops.run_notices WHERE run_id=%s AND publication_number='100000-2026'",
        (run_id,),
    ).fetchone()[0]
    assert "download" in error
    assert c.execute(
        "SELECT count(*) FROM ops.run_notices WHERE run_id=%s AND outcome='failed'",
        (source,),
    ).fetchone() == (3,)


def test_retry_can_succeed_for_arbitrary_source_id(pipeline_connection, notice_xml):
    c = pipeline_connection
    source = failed_source(c, ["722762-2026"])
    save_notice_xml(c, "722762-2026", notice_xml)
    run_id = retry_processing(c, source_run_id=source)
    assert c.execute(
        "SELECT run_mode,status FROM ops.pipeline_runs WHERE run_id=%s", (run_id,)
    ).fetchone() == ("retry", "succeeded")


@pytest.mark.parametrize("mode", ["running", "history", "missing"])
def test_retry_rejects_invalid_source_without_creating_run(pipeline_connection, mode):
    c = pipeline_connection
    source = failed_source(
        c, ["722762-2026"], mode="history" if mode == "history" else "backfill"
    )
    if mode == "running":
        c.execute(
            "UPDATE ops.pipeline_runs SET status='running',finished_at=NULL WHERE run_id=%s",
            (source,),
        )
    before = c.execute("SELECT count(*) FROM ops.pipeline_runs").fetchone()
    with pytest.raises(ValueError):
        retry_processing(
            c, source_run_id=source if mode != "missing" else source + 1000000
        )
    assert c.execute("SELECT count(*) FROM ops.pipeline_runs").fetchone() == before


def test_retry_failure_rolls_back_processing_and_records_run_failure(
    pipeline_connection, notice_xml
):
    c = pipeline_connection
    source = failed_source(c, ["722762-2026"])
    save_notice_xml(c, "722762-2026", notice_xml)
    with patch(
        "tender_intelligence.retry.record_notice_outcome",
        side_effect=RuntimeError("outcome failure"),
    ):
        with pytest.raises(RuntimeError, match="outcome failure"):
            retry_processing(c, source_run_id=source)
    assert c.execute("SELECT count(*) FROM staging.notices").fetchone() == (0,)
    assert c.execute("SELECT processing_status FROM raw.notices").fetchone() == (
        "pending",
    )
    assert c.execute(
        "SELECT status FROM ops.pipeline_runs WHERE run_mode='retry'"
    ).fetchone() == ("failed",)
