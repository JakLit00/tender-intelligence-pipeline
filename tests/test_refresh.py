from datetime import date
from unittest.mock import MagicMock

import psycopg
import pytest
from psycopg.pq import TransactionStatus

from tender_intelligence import refresh


@pytest.fixture
def connection():
    conn = MagicMock(spec=psycopg.Connection)
    conn.autocommit = True
    conn.info.transaction_status = TransactionStatus.IDLE
    conn.execute.return_value.fetchone.return_value = ("succeeded", None)
    return conn


@pytest.fixture
def stages(monkeypatch):
    incremental = MagicMock(return_value=10)
    history = MagicMock(return_value=11)
    missing = MagicMock(return_value=[])

    monkeypatch.setattr(refresh, "run_incremental", incremental)
    monkeypatch.setattr(refresh, "run_history", history)
    monkeypatch.setattr(
        refresh,
        "find_missing_predecessor_publications",
        missing,
    )

    return incremental, history, missing


def run_refresh(connection, **options):
    return refresh.refresh_ingestion(
        connection,
        initial_date=date(2026, 10, 20),
        today=date(2026, 11, 5),
        **options,
    )


def test_skips_history_when_no_predecessors_are_missing(connection, stages):
    incremental, history, _ = stages

    result = run_refresh(connection)

    assert result.incremental_run_id == 10
    assert result.history_run_ids == ()
    incremental.assert_called_once_with(
        connection,
        initial_date=date(2026, 10, 20),
        today=date(2026, 11, 5),
        overlap_days=3,
    )
    history.assert_not_called()


@pytest.mark.parametrize("status", ["partial", "failed"])
def test_stops_after_unsuccessful_incremental(connection, stages, status):
    _, history, missing = stages
    connection.execute.return_value.fetchone.return_value = (
        status,
        "Download failed",
    )

    with pytest.raises(RuntimeError, match=f"ended with {status}"):
        run_refresh(connection)

    history.assert_not_called()
    missing.assert_not_called()


def test_resolves_history_when_incremental_has_no_window(connection, stages):
    incremental, history, missing = stages
    incremental.return_value = None
    missing.side_effect = [["722762-2026"], []]

    result = run_refresh(connection)

    assert result.incremental_run_id is None
    assert result.history_run_ids == (11,)
    history.assert_called_once()


def test_continues_when_missing_count_is_unchanged_but_references_change(
    connection,
    stages,
):
    _, history, missing = stages
    history.side_effect = [11, 12]
    missing.side_effect = [
        ["722762-2026"],
        ["706539-2026"],
        [],
    ]

    result = run_refresh(connection)

    assert result.history_run_ids == (11, 12)
    assert history.call_count == 2


def test_stops_when_history_makes_no_progress(connection, stages):
    _, history, missing = stages
    missing.side_effect = [
        ["722762-2026"],
        ["722762-2026"],
    ]

    with pytest.raises(RuntimeError, match="resolved no previously missing"):
        run_refresh(connection)

    history.assert_called_once()


def test_stops_when_history_batch_limit_is_reached(connection, stages):
    _, history, missing = stages
    missing.side_effect = [
        ["722762-2026"],
        ["706539-2026"],
    ]

    with pytest.raises(RuntimeError, match="History batch limit reached"):
        run_refresh(connection, max_history_batches=1)

    history.assert_called_once()


def test_accepts_completion_in_the_last_allowed_batch(connection, stages):
    _, _, missing = stages
    missing.side_effect = [["722762-2026"], []]

    result = run_refresh(connection, max_history_batches=1)

    assert result.history_run_ids == (11,)


def test_stops_after_unsuccessful_history(connection, stages):
    _, history, missing = stages
    missing.return_value = ["722762-2026"]
    connection.execute.return_value.fetchone.side_effect = [
        ("succeeded", None),
        ("partial", "Predecessor download failed"),
    ]

    with pytest.raises(RuntimeError, match="Run 11 ended with partial"):
        run_refresh(connection)

    history.assert_called_once()
    missing.assert_called_once()


def test_rejects_missing_history_run(connection, stages):
    _, history, missing = stages
    missing.return_value = ["722762-2026"]
    history.return_value = None

    with pytest.raises(RuntimeError, match="History returned no run"):
        run_refresh(connection)


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        ("overlap_days", 0),
        ("history_batch_size", -1),
        ("max_history_batches", True),
    ],
)
def test_rejects_invalid_limits_before_ingestion(
    connection,
    stages,
    parameter,
    value,
):
    incremental, _, _ = stages

    with pytest.raises(ValueError, match=f"{parameter} must be"):
        run_refresh(connection, **{parameter: value})

    incremental.assert_not_called()


@pytest.mark.parametrize(
    ("autocommit", "transaction_status"),
    [
        (False, TransactionStatus.IDLE),
        (True, TransactionStatus.INTRANS),
    ],
)
def test_rejects_connection_with_invalid_transaction_state(
    connection,
    stages,
    autocommit,
    transaction_status,
):
    incremental, _, _ = stages
    connection.autocommit = autocommit
    connection.info.transaction_status = transaction_status

    with pytest.raises(ValueError, match="idle connection with autocommit"):
        run_refresh(connection)

    incremental.assert_not_called()
