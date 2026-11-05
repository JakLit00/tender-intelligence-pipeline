from datetime import date

import pytest

from tender_intelligence.incremental import calculate_incremental_window


def test_first_run_starts_at_initial_date():
    assert calculate_incremental_window(
        initial_date=date(2026, 10, 20),
        last_successful_date=None,
        today=date(2026, 11, 4),
    ) == (date(2026, 10, 20), date(2026, 11, 3))


def test_resumes_with_three_day_overlap():
    assert calculate_incremental_window(
        initial_date=date(2026, 10, 20),
        last_successful_date=date(2026, 10, 29),
        today=date(2026, 11, 4),
    ) == (date(2026, 10, 27), date(2026, 11, 3))


def test_overlap_does_not_precede_initial_date():
    assert calculate_incremental_window(
        initial_date=date(2026, 10, 20),
        last_successful_date=date(2026, 10, 21),
        today=date(2026, 10, 23),
    ) == (date(2026, 10, 20), date(2026, 10, 22))


def test_rechecks_overlap_when_already_caught_up():
    assert calculate_incremental_window(
        initial_date=date(2026, 10, 20),
        last_successful_date=date(2026, 11, 3),
        today=date(2026, 11, 4),
    ) == (date(2026, 11, 1), date(2026, 11, 3))


def test_returns_none_when_no_complete_day_is_available():
    assert (
        calculate_incremental_window(
            initial_date=date(2026, 11, 4),
            last_successful_date=None,
            today=date(2026, 11, 4),
        )
        is None
    )


@pytest.mark.parametrize("overlap_days", [0, -1, True])
def test_rejects_invalid_overlap(overlap_days):
    with pytest.raises(ValueError, match="positive integer"):
        calculate_incremental_window(
            initial_date=date(2026, 10, 20),
            last_successful_date=None,
            today=date(2026, 11, 4),
            overlap_days=overlap_days,
        )


def test_rejects_checkpoint_before_initial_date():
    with pytest.raises(ValueError, match="precedes"):
        calculate_incremental_window(
            initial_date=date(2026, 10, 20),
            last_successful_date=date(2026, 10, 19),
            today=date(2026, 11, 4),
        )


def test_rejects_checkpoint_after_yesterday():
    with pytest.raises(ValueError, match="later than yesterday"):
        calculate_incremental_window(
            initial_date=date(2026, 10, 20),
            last_successful_date=date(2026, 11, 4),
            today=date(2026, 11, 4),
        )
