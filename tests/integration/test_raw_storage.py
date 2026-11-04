from datetime import date

import psycopg
import pytest

from tender_intelligence.processing import process_notice
from tender_intelligence.storage import save_notice_xml


@pytest.fixture
def pending_notice(db_connection: psycopg.Connection) -> str:
    publication_number = "722762-2026"

    db_connection.execute(
        """
        INSERT INTO raw.notices (
            publication_number,
            publication_date,
            search_metadata
        )
        VALUES (%s, %s, %s::jsonb)
        """,
        (
            publication_number,
            date(2026, 10, 20),
            '{"source": "integration-test"}',
        ),
    )

    return publication_number


def read_raw(conn: psycopg.Connection, publication_number: str) -> tuple:
    row = conn.execute(
        """
        SELECT
            xml_content,
            xml_downloaded_at,
            processing_status,
            processed_at,
            last_error
        FROM raw.notices
        WHERE publication_number = %s
        """,
        (publication_number,),
    ).fetchone()

    assert row is not None
    return row


def test_stores_first_xml(
    db_connection: psycopg.Connection,
    pending_notice: str,
    notice_xml: bytes,
) -> None:
    assert save_notice_xml(
        db_connection, pending_notice, notice_xml
    ) is True

    xml, downloaded_at, status, processed_at, error = read_raw(
        db_connection, pending_notice
    )
    assert xml == notice_xml
    assert downloaded_at is not None
    assert status == "pending"
    assert processed_at is None
    assert error is None


def test_identical_xml_preserves_successful_result(
    db_connection: psycopg.Connection,
    pending_notice: str,
    notice_xml: bytes,
) -> None:
    save_notice_xml(db_connection, pending_notice, notice_xml)
    assert process_notice(db_connection, pending_notice) == "processed"
    before = read_raw(db_connection, pending_notice)

    assert save_notice_xml(
        db_connection, pending_notice, notice_xml
    ) is False

    assert read_raw(db_connection, pending_notice) == before


def test_changed_xml_requires_processing_after_success(
    db_connection: psycopg.Connection,
    pending_notice: str,
    notice_xml: bytes,
) -> None:
    save_notice_xml(db_connection, pending_notice, notice_xml)
    assert process_notice(db_connection, pending_notice) == "processed"

    changed_xml = notice_xml.replace(
        b"2026-11-03+01:00",
        b"2026-11-04+01:00",
    )
    assert changed_xml != notice_xml

    assert save_notice_xml(
        db_connection, pending_notice, changed_xml
    ) is True

    xml, downloaded_at, status, processed_at, error = read_raw(
        db_connection, pending_notice
    )
    assert xml == changed_xml
    assert downloaded_at is not None
    assert status == "pending"
    assert processed_at is None
    assert error is None

    assert process_notice(db_connection, pending_notice) == "processed"

    deadline = db_connection.execute(
        """
        SELECT submission_deadline_local_date
        FROM staging.notice_lots
        WHERE publication_number = %s AND lot_id = %s
        """,
        (pending_notice, "LOT-0001"),
    ).fetchone()

    assert deadline == (date(2026, 11, 4),)


def test_identical_failed_xml_still_requires_processing(
    db_connection: psycopg.Connection,
    pending_notice: str,
) -> None:
    invalid_xml = b"<broken"
    save_notice_xml(db_connection, pending_notice, invalid_xml)
    assert process_notice(db_connection, pending_notice) == "failed"
    before = read_raw(db_connection, pending_notice)

    assert save_notice_xml(
        db_connection, pending_notice, invalid_xml
    ) is True

    assert read_raw(db_connection, pending_notice) == before


def test_changed_xml_clears_previous_error(
    db_connection: psycopg.Connection,
    pending_notice: str,
    notice_xml: bytes,
) -> None:
    save_notice_xml(db_connection, pending_notice, b"<broken")
    assert process_notice(db_connection, pending_notice) == "failed"

    assert save_notice_xml(
        db_connection, pending_notice, notice_xml
    ) is True

    xml, _, status, processed_at, error = read_raw(
        db_connection, pending_notice
    )
    assert xml == notice_xml
    assert status == "pending"
    assert processed_at is None
    assert error is None


def test_rejects_empty_xml_without_changing_record(
    db_connection: psycopg.Connection,
    pending_notice: str,
) -> None:
    before = read_raw(db_connection, pending_notice)

    with pytest.raises(ValueError, match="XML content must not be empty"):
        save_notice_xml(db_connection, pending_notice, b"")

    assert read_raw(db_connection, pending_notice) == before


def test_rejects_xml_for_missing_publication(
    db_connection: psycopg.Connection,
    notice_xml: bytes,
) -> None:
    with pytest.raises(ValueError, match="Publication not found"):
        save_notice_xml(db_connection, "999998-2099", notice_xml)