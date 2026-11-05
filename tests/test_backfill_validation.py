from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import pytest

from tender_intelligence.pipeline import run_backfill


@pytest.mark.parametrize("end", [date(2026, 11, 5), date(2026, 11, 30)])
def test_rejects_incomplete_utc_days_before_creating_run(end):
    connection = MagicMock()
    with patch("tender_intelligence.pipeline.datetime") as clock:
        clock.now.return_value = datetime(2026, 11, 5, 0, 1, tzinfo=UTC)
        with pytest.raises(ValueError, match="before today in UTC"):
            run_backfill(connection, date_from=date(2026, 11, 1), date_to=end)
        clock.now.assert_called_once_with(UTC)
    assert connection.mock_calls == []


def test_accepts_yesterday_and_rejects_inverted_range():
    with (
        patch("tender_intelligence.pipeline.datetime") as clock,
        patch("tender_intelligence.pipeline._run_date_range", return_value=42) as run,
    ):
        clock.now.return_value = datetime(2026, 11, 5, tzinfo=UTC)
        assert (
            run_backfill(
                MagicMock(), date_from=date(2026, 11, 1), date_to=date(2026, 11, 4)
            )
            == 42
        )
        with pytest.raises(ValueError, match="earlier"):
            run_backfill(
                MagicMock(), date_from=date(2026, 11, 4), date_to=date(2026, 11, 1)
            )
    run.assert_called_once()
