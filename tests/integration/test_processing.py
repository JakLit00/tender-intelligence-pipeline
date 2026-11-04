import psycopg
import pytest

from tender_intelligence.models import PreparedNoticeBundle
from tender_intelligence.preparation import prepare_notice
from tender_intelligence.processing import process_notice
from tender_intelligence.storage import save_prepared_notice


PUBLICATION_NUMBER = "722762-2026"


@pytest.fixture
def raw_notice(
    db_connection: psycopg.Connection,
    notice_xml: bytes,
) -> str:
    prepared = prepare_notice(
        notice_xml,
        expected_publication_number=PUBLICATION_NUMBER,
    )

    db_connection.execute(
        """
        INSERT INTO raw.notices (
            publication_number,
            publication_date,
            search_metadata,
            xml_content,
            xml_downloaded_at
        )
        VALUES (%s, %s, %s::jsonb, %s, CURRENT_TIMESTAMP)
        """,
        (
            PUBLICATION_NUMBER,
            prepared.notice.publication_date,
            '{"source": "integration-test"}',
            notice_xml,
        ),
    )

    return PUBLICATION_NUMBER


def read_status(
    conn: psycopg.Connection,
    publication_number: str,
) -> tuple:
    row = conn.execute(
        """
        SELECT processing_status, processed_at, last_error
        FROM raw.notices
        WHERE publication_number = %s
        """,
        (publication_number,),
    ).fetchone()

    assert row is not None
    return row


def read_staging(
    conn: psycopg.Connection,
    publication_number: str,
) -> tuple:
    notices = conn.execute(
        """
        SELECT *
        FROM staging.notices
        WHERE publication_number = %s
        """,
        (publication_number,),
    ).fetchall()

    lots = conn.execute(
        """
        SELECT *
        FROM staging.notice_lots
        WHERE publication_number = %s
        ORDER BY lot_id
        """,
        (publication_number,),
    ).fetchall()

    return notices, lots


def test_processes_notice_and_records_success(
    db_connection: psycopg.Connection,
    raw_notice: str,
) -> None:
    assert process_notice(db_connection, raw_notice) == "processed"

    status, processed_at, last_error = read_status(
        db_connection, raw_notice
    )
    assert status == "succeeded"
    assert processed_at is not None
    assert last_error is None

    notices, lots = read_staging(db_connection, raw_notice)
    assert len(notices) == 1
    assert len(lots) == 1


def test_skips_successful_notice_without_changes(
    db_connection: psycopg.Connection,
    raw_notice: str,
) -> None:
    process_notice(db_connection, raw_notice)
    before = (
        read_status(db_connection, raw_notice),
        read_staging(db_connection, raw_notice),
    )

    assert process_notice(db_connection, raw_notice) == "skipped"

    assert (
        read_status(db_connection, raw_notice),
        read_staging(db_connection, raw_notice),
    ) == before


def test_force_reprocesses_successful_notice(
    db_connection: psycopg.Connection,
    raw_notice: str,
) -> None:
    process_notice(db_connection, raw_notice)

    outcome = process_notice(
        db_connection,
        raw_notice,
        force=True,
    )
    assert outcome == "processed"
    assert read_status(db_connection, raw_notice)[0] == "succeeded"

    notices, lots = read_staging(db_connection, raw_notice)
    assert len(notices) == 1
    assert len(lots) == 1


def test_failed_reprocessing_preserves_previous_staging(
    db_connection: psycopg.Connection,
    raw_notice: str,
) -> None:
    process_notice(db_connection, raw_notice)
    before = read_staging(db_connection, raw_notice)

    db_connection.execute(
        """
        UPDATE raw.notices
        SET xml_content = %s
        WHERE publication_number = %s
        """,
        (b"<broken", raw_notice),
    )

    outcome = process_notice(
        db_connection,
        raw_notice,
        force=True,
    )
    assert outcome == "failed"

    status, processed_at, last_error = read_status(
        db_connection, raw_notice
    )
    assert status == "failed"
    assert processed_at is None
    assert last_error.startswith("ParseError:")
    assert read_staging(db_connection, raw_notice) == before


def test_retries_failed_notice_and_clears_error(
    db_connection: psycopg.Connection,
    raw_notice: str,
    notice_xml: bytes,
) -> None:
    db_connection.execute(
        """
        UPDATE raw.notices
        SET xml_content = %s
        WHERE publication_number = %s
        """,
        (b"<broken", raw_notice),
    )

    assert process_notice(db_connection, raw_notice) == "failed"
    assert read_staging(db_connection, raw_notice) == ([], [])

    db_connection.execute(
        """
        UPDATE raw.notices
        SET xml_content = %s
        WHERE publication_number = %s
        """,
        (notice_xml, raw_notice),
    )

    assert process_notice(db_connection, raw_notice) == "processed"

    status, processed_at, last_error = read_status(
        db_connection, raw_notice
    )
    assert status == "succeeded"
    assert processed_at is not None
    assert last_error is None

    notices, lots = read_staging(db_connection, raw_notice)
    assert len(notices) == 1
    assert len(lots) == 1


def test_database_failure_rolls_back_staging_and_status(
    db_connection: psycopg.Connection,
    raw_notice: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = (
        read_status(db_connection, raw_notice),
        read_staging(db_connection, raw_notice),
    )

    def save_then_fail(
        conn: psycopg.Connection,
        bundle: PreparedNoticeBundle,
    ) -> None:
        save_prepared_notice(conn, bundle)
        # Trigger a database error after staging writes but before success.
        conn.execute("SELECT 1 / 0")

    monkeypatch.setattr(
        "tender_intelligence.processing.save_prepared_notice",
        save_then_fail,
    )

    with pytest.raises(psycopg.errors.DivisionByZero):
        process_notice(db_connection, raw_notice)

    assert (
        read_status(db_connection, raw_notice),
        read_staging(db_connection, raw_notice),
    ) == before