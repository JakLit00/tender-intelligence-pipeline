from datetime import date
from unittest.mock import patch

import psycopg
import pytest

from tender_intelligence.ingestion import register_search_results
from tender_intelligence.storage import register_notice


@pytest.fixture
def search_results() -> list[dict]:
    return [
        {
            "publication-number": "00999998-2099",
            "publication-date": "2099-01-01Z",
            "notice-title": {"pol": "First notice"},
        },
        {
            "publication-number": "999999-2099",
            "publication-date": "2099-01-02Z",
            "notice-title": {"pol": "Second notice"},
        },
    ]


def read_registered_notices(conn: psycopg.Connection) -> list:
    return conn.execute(
        """
        SELECT
            publication_number,
            publication_date,
            search_metadata,
            processing_status
        FROM raw.notices
        WHERE publication_number IN (%s, %s)
        ORDER BY publication_number
        """,
        ("999998-2099", "999999-2099"),
    ).fetchall()


def test_registers_complete_search_batch(
    db_connection: psycopg.Connection,
    search_results: list[dict],
) -> None:
    count = register_search_results(db_connection, search_results)

    assert count == 2
    assert read_registered_notices(db_connection) == [
        (
            "999998-2099",
            date(2099, 1, 1),
            search_results[0],
            "pending",
        ),
        (
            "999999-2099",
            date(2099, 1, 2),
            search_results[1],
            "pending",
        ),
    ]


def test_repeated_batch_does_not_duplicate_publications(
    db_connection: psycopg.Connection,
    search_results: list[dict],
) -> None:
    assert register_search_results(db_connection, search_results) == 2
    assert register_search_results(db_connection, search_results) == 2

    assert len(read_registered_notices(db_connection)) == 2


def test_empty_batch_returns_zero(
    db_connection: psycopg.Connection,
) -> None:
    with patch(
        "tender_intelligence.ingestion.register_notice"
    ) as register:
        assert register_search_results(db_connection, []) == 0

    register.assert_not_called()


def test_invalid_batch_is_rejected_before_registration(
    db_connection: psycopg.Connection,
    search_results: list[dict],
) -> None:
    search_results[1]["publication-date"] = "2099-02-30"

    with patch(
        "tender_intelligence.ingestion.register_notice"
    ) as register:
        with pytest.raises(ValueError, match="Invalid XML date"):
            register_search_results(db_connection, search_results)

    register.assert_not_called()
    assert read_registered_notices(db_connection) == []


def test_second_record_failure_rolls_back_entire_batch(
    db_connection: psycopg.Connection,
    search_results: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registered_numbers = []

    def register_then_fail(
        conn: psycopg.Connection,
        *,
        publication_number: str,
        publication_date: date,
        search_metadata: dict,
    ) -> None:
        register_notice(
            conn,
            publication_number=publication_number,
            publication_date=publication_date,
            search_metadata=search_metadata,
        )
        registered_numbers.append(publication_number)

        if len(registered_numbers) == 2:
            # Fail after both writes to verify the batch transaction boundary.
            conn.execute("SELECT 1 / 0")

    monkeypatch.setattr(
        "tender_intelligence.ingestion.register_notice",
        register_then_fail,
    )

    with pytest.raises(psycopg.errors.DivisionByZero):
        register_search_results(db_connection, search_results)

    assert registered_numbers == ["999998-2099", "999999-2099"]
    assert read_registered_notices(db_connection) == []