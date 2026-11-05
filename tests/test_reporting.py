from unittest.mock import MagicMock

import psycopg
import pytest
from psycopg.pq import TransactionStatus

from tender_intelligence.reporting import read_dashboard_snapshot


def make_connection(observations, summary_rows, scope):
    connection = MagicMock(spec=psycopg.Connection)
    connection.info.transaction_status = TransactionStatus.IDLE

    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.side_effect = [observations, summary_rows]
    cursor.fetchone.return_value = scope

    return connection


def test_returns_consistent_snapshot():
    observations = [
        {
            "publication_number": "722762-2026",
            "lot_id": "LOT-0001",
            "deadline_change_hours": 289,
        }
    ]
    summary = {"total_lot_observations": 1}
    scope = {"notice_count": 1}

    connection = make_connection(observations, [summary], scope)

    result = read_dashboard_snapshot(connection)

    assert result == {
        "scope": scope,
        "summary": summary,
        "observations": observations,
    }


def test_rejects_mismatched_observation_count():
    connection = make_connection(
        observations=[],
        summary_rows=[{"total_lot_observations": 1}],
        scope={"notice_count": 1},
    )

    with pytest.raises(ValueError, match="observation counts differ"):
        read_dashboard_snapshot(connection)


@pytest.mark.parametrize(
    "summary_rows",
    [
        [],
        [
            {"total_lot_observations": 0},
            {"total_lot_observations": 0},
        ],
    ],
)
def test_rejects_invalid_summary_row_count(summary_rows):
    connection = make_connection(
        observations=[],
        summary_rows=summary_rows,
        scope={"notice_count": 0},
    )

    with pytest.raises(ValueError, match="exactly one dashboard summary row"):
        read_dashboard_snapshot(connection)


def test_accepts_empty_dataset():
    summary = {"total_lot_observations": 0}
    scope = {
        "notice_count": 0,
        "first_publication_date": None,
        "last_publication_date": None,
    }
    connection = make_connection([], [summary], scope)

    result = read_dashboard_snapshot(connection)

    assert result["observations"] == []
    assert result["summary"] == summary
    assert result["scope"] == scope


def test_rejects_active_transaction_before_querying():
    connection = MagicMock(spec=psycopg.Connection)
    connection.info.transaction_status = TransactionStatus.INTRANS

    with pytest.raises(ValueError, match="idle connection"):
        read_dashboard_snapshot(connection)

    connection.transaction.assert_not_called()
    connection.cursor.assert_not_called()