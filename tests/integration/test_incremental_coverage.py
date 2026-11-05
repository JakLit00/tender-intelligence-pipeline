from datetime import date

import pytest

from tender_intelligence.incremental import get_last_successful_date
from tender_intelligence.run_tracking import (
    fail_run,
    finish_run,
    start_run,
)


@pytest.mark.parametrize(
    ("windows", "expected"),
    [
        ([], None),
        (
            [("backfill", 20, 25)],
            date(2026, 10, 25),
        ),
        (
            [("backfill", 20, 25), ("incremental", 26, 29)],
            date(2026, 10, 29),
        ),
        (
            [("backfill", 20, 25), ("incremental", 23, 29)],
            date(2026, 10, 29),
        ),
        (
            [("backfill", 20, 25), ("backfill", 28, 30)],
            date(2026, 10, 25),
        ),
        (
            [("backfill", 23, 29)],
            None,
        ),
        (
            [
                ("backfill", 20, 25),
                ("history", 20, 30),
                ("retry", 20, 30),
            ],
            date(2026, 10, 25),
        ),
    ],
)
def test_reads_contiguous_successful_coverage(
    db_connection,
    windows,
    expected,
):
    for mode, first_day, last_day in windows:
        run_id = start_run(
            db_connection,
            run_mode=mode,
            date_from=date(2026, 10, first_day),
            date_to=date(2026, 10, last_day),
        )
        finish_run(db_connection, run_id=run_id)

    result = get_last_successful_date(
        db_connection,
        initial_date=date(2026, 10, 20),
    )

    assert result == expected


@pytest.mark.parametrize("status", ["running", "failed"])
def test_ignores_unfinished_or_failed_runs(db_connection, status):
    run_id = start_run(
        db_connection,
        run_mode="incremental",
        date_from=date(2026, 10, 20),
        date_to=date(2026, 10, 29),
    )

    if status == "failed":
        fail_run(
            db_connection,
            run_id=run_id,
            error_message="Simulated failure",
        )

    assert (
        get_last_successful_date(
            db_connection,
            initial_date=date(2026, 10, 20),
        )
        is None
    )
