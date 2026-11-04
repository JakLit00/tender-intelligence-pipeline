from datetime import date
from unittest.mock import patch
from urllib.error import URLError

import psycopg
import pytest

from tender_intelligence.pipeline import run_backfill


SEARCH_RESULTS = [
    {
        "publication-number": "722762-2026",
        "publication-date": "2026-10-20+02:00",
    }
]


def test_backfill_processes_notice_and_skips_it_on_next_run(
    pipeline_connection: psycopg.Connection,
    notice_xml: bytes,
) -> None:
    conn = pipeline_connection

    with (
        patch(
            "tender_intelligence.pipeline.fetch_all_notices",
            return_value=SEARCH_RESULTS,
        ),
        patch(
            "tender_intelligence.pipeline.fetch_notice_xml",
            return_value=notice_xml,
        ) as download,
    ):
        first_run = run_backfill(
            conn,
            date_from=date(2026, 10, 20),
            date_to=date(2026, 10, 29),
        )
        second_run = run_backfill(
            conn,
            date_from=date(2026, 10, 20),
            date_to=date(2026, 10, 29),
        )

    assert first_run != second_run
    assert download.call_count == 2

    outcomes = conn.execute(
        """
        SELECT r.run_id, r.status, n.outcome
        FROM ops.pipeline_runs AS r
        JOIN ops.run_notices AS n USING (run_id)
        ORDER BY r.run_id
        """
    ).fetchall()

    assert outcomes == [
        (first_run, "succeeded", "processed"),
        (second_run, "succeeded", "skipped"),
    ]

    raw = conn.execute(
        """
        SELECT processing_status, last_error
        FROM raw.notices
        WHERE publication_number = '722762-2026'
        """
    ).fetchone()
    assert raw == ("succeeded", None)

    lots = conn.execute(
        """
        SELECT lot_id, submission_deadline_local_date
        FROM staging.notice_lots
        WHERE publication_number = '722762-2026'
        """
    ).fetchall()
    assert lots == [("LOT-0001", date(2026, 11, 3))]


def test_search_failure_marks_run_failed_and_propagates_error(
    pipeline_connection: psycopg.Connection,
) -> None:
    conn = pipeline_connection

    with patch(
        "tender_intelligence.pipeline.fetch_all_notices",
        side_effect=URLError("Search unavailable"),
    ):
        with pytest.raises(URLError, match="Search unavailable"):
            run_backfill(
                conn,
                date_from=date(2026, 10, 20),
                date_to=date(2026, 10, 29),
            )

    runs = conn.execute(
        """
        SELECT status, finished_at IS NOT NULL, error_message
        FROM ops.pipeline_runs
        """
    ).fetchall()

    assert len(runs) == 1
    assert runs[0][:2] == ("failed", True)
    assert "Search unavailable" in runs[0][2]

    assert conn.execute(
        "SELECT count(*) FROM ops.run_notices"
    ).fetchone() == (0,)


def test_download_failure_is_recorded_for_publication(
    pipeline_connection: psycopg.Connection,
) -> None:
    conn = pipeline_connection

    with (
        patch(
            "tender_intelligence.pipeline.fetch_all_notices",
            return_value=SEARCH_RESULTS,
        ),
        patch(
            "tender_intelligence.pipeline.fetch_notice_xml",
            side_effect=URLError("Download unavailable"),
        ),
    ):
        run_id = run_backfill(
            conn,
            date_from=date(2026, 10, 20),
            date_to=date(2026, 10, 29),
        )

    row = conn.execute(
        """
        SELECT r.status, n.outcome, n.error_message
        FROM ops.pipeline_runs AS r
        JOIN ops.run_notices AS n USING (run_id)
        WHERE r.run_id = %s
        """,
        (run_id,),
    ).fetchone()

    assert row is not None
    assert row[:2] == ("failed", "failed")
    assert "Download unavailable" in row[2]

    raw = conn.execute(
        """
        SELECT processing_status, xml_content
        FROM raw.notices
        WHERE publication_number = '722762-2026'
        """
    ).fetchone()
    assert raw == ("pending", None)

def test_download_failure_does_not_stop_remaining_publications(
    pipeline_connection: psycopg.Connection,
    notice_xml: bytes,
) -> None:
    conn = pipeline_connection
    search_results = [
        {
            "publication-number": "999997-2026",
            "publication-date": "2026-10-20+02:00",
        },
        {
            "publication-number": "722762-2026",
            "publication-date": "2026-10-20+02:00",
        },
    ]

    with (
        patch(
            "tender_intelligence.pipeline.fetch_all_notices",
            return_value=search_results,
        ),
        patch(
            "tender_intelligence.pipeline.fetch_notice_xml",
            side_effect=[
                URLError("First download failed"),
                notice_xml,
            ],
        ) as download,
    ):
        run_id = run_backfill(
            conn,
            date_from=date(2026, 10, 20),
            date_to=date(2026, 10, 29),
        )

    assert [
        invocation.args[0]
        for invocation in download.call_args_list
    ] == ["999997-2026", "722762-2026"]

    run = conn.execute(
        """
        SELECT status, error_message
        FROM ops.pipeline_runs
        WHERE run_id = %s
        """,
        (run_id,),
    ).fetchone()
    assert run == ("partial", "1 of 2 publications failed")

    outcomes = conn.execute(
        """
        SELECT publication_number, outcome
        FROM ops.run_notices
        WHERE run_id = %s
        ORDER BY publication_number
        """,
        (run_id,),
    ).fetchall()
    assert outcomes == [
        ("722762-2026", "processed"),
        ("999997-2026", "failed"),
    ]

    staged = conn.execute(
        """
        SELECT publication_number
        FROM staging.notices
        ORDER BY publication_number
        """
    ).fetchall()
    assert staged == [("722762-2026",)]