from datetime import date
from unittest.mock import patch

from tender_intelligence.pipeline import run_incremental

from urllib.error import URLError

import pytest


def test_incremental_records_first_range_and_then_uses_overlap(
    pipeline_connection,
):
    with patch(
        "tender_intelligence.pipeline.fetch_all_notices",
        return_value=[],
    ) as search:
        first_run_id = run_incremental(
            pipeline_connection,
            initial_date=date(2026, 10, 20),
            today=date(2026, 11, 4),
        )

    assert first_run_id is not None
    first_query = search.call_args.args[0]
    assert "publication-date >= 20261020" in first_query
    assert "publication-date <= 20261103" in first_query

    with patch(
        "tender_intelligence.pipeline.fetch_all_notices",
        return_value=[],
    ) as search:
        second_run_id = run_incremental(
            pipeline_connection,
            initial_date=date(2026, 10, 20),
            today=date(2026, 11, 5),
        )

    assert second_run_id is not None
    second_query = search.call_args.args[0]
    assert "publication-date >= 20261101" in second_query
    assert "publication-date <= 20261104" in second_query

    runs = pipeline_connection.execute(
        """
        SELECT run_mode, date_from, date_to, status
        FROM ops.pipeline_runs
        ORDER BY run_id
        """
    ).fetchall()

    assert runs == [
        (
            "incremental",
            date(2026, 10, 20),
            date(2026, 11, 3),
            "succeeded",
        ),
        (
            "incremental",
            date(2026, 11, 1),
            date(2026, 11, 4),
            "succeeded",
        ),
    ]


def test_incremental_creates_no_run_when_no_complete_day_is_available(
    pipeline_connection,
):
    with patch(
        "tender_intelligence.pipeline.fetch_all_notices",
    ) as search:
        result = run_incremental(
            pipeline_connection,
            initial_date=date(2026, 11, 4),
            today=date(2026, 11, 4),
        )

    assert result is None
    search.assert_not_called()

    row = pipeline_connection.execute(
        "SELECT count(*) FROM ops.pipeline_runs"
    ).fetchone()
    assert row == (0,)

def test_incremental_retries_range_after_search_failure(
    pipeline_connection,
):
    with patch(
        "tender_intelligence.pipeline.fetch_all_notices",
        side_effect=URLError("Simulated search failure"),
    ) as failed_search:
        with pytest.raises(URLError):
            run_incremental(
                pipeline_connection,
                initial_date=date(2026, 10, 20),
                today=date(2026, 11, 4),
            )

    failed_query = failed_search.call_args.args[0]

    with patch(
        "tender_intelligence.pipeline.fetch_all_notices",
        return_value=[],
    ) as successful_search:
        run_incremental(
            pipeline_connection,
            initial_date=date(2026, 10, 20),
            today=date(2026, 11, 4),
        )

    assert successful_search.call_args.args[0] == failed_query

    runs = pipeline_connection.execute(
        """
        SELECT date_from, date_to, status
        FROM ops.pipeline_runs
        ORDER BY run_id
        """
    ).fetchall()

    assert runs == [
        (
            date(2026, 10, 20),
            date(2026, 11, 3),
            "failed",
        ),
        (
            date(2026, 10, 20),
            date(2026, 11, 3),
            "succeeded",
        ),
    ]