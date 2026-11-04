from datetime import date

import psycopg

from tender_intelligence.processing import process_notice
from tender_intelligence.storage import (
    register_notice,
    save_notice_xml,
)


def test_registers_new_notice(
    db_connection: psycopg.Connection,
) -> None:
    register_notice(
        db_connection,
        publication_number="00722762-2026",
        publication_date=date(2026, 10, 20),
        search_metadata={"title": "Initial title"},
    )

    row = db_connection.execute(
        """
        SELECT
            publication_number,
            publication_date,
            search_metadata,
            processing_status,
            xml_content,
            xml_downloaded_at,
            processed_at,
            last_error,
            first_seen_at,
            last_seen_at
        FROM raw.notices
        WHERE publication_number = %s
        """,
        ("722762-2026",),
    ).fetchone()

    assert row is not None
    assert row[:8] == (
        "722762-2026",
        date(2026, 10, 20),
        {"title": "Initial title"},
        "pending",
        None,
        None,
        None,
        None,
    )
    assert row[8] is not None
    assert row[9] >= row[8]


def test_rediscovery_updates_metadata_and_preserves_processing(
    db_connection: psycopg.Connection,
    notice_xml: bytes,
) -> None:
    publication_number = "722762-2026"

    register_notice(
        db_connection,
        publication_number=publication_number,
        publication_date=date(2026, 10, 20),
        search_metadata={"title": "Initial title"},
    )
    save_notice_xml(db_connection, publication_number, notice_xml)
    assert process_notice(
        db_connection, publication_number
    ) == "processed"

    # Fixed timestamps make the refresh check independent of execution speed.
    db_connection.execute(
        """
        UPDATE raw.notices
        SET first_seen_at = TIMESTAMPTZ '2000-01-01 00:00:00+00',
            last_seen_at = TIMESTAMPTZ '2000-01-02 00:00:00+00'
        WHERE publication_number = %s
        """,
        (publication_number,),
    )

    before = db_connection.execute(
        """
        SELECT
            first_seen_at,
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

    register_notice(
        db_connection,
        publication_number="00722762-2026",
        publication_date=date(2026, 10, 20),
        search_metadata={"title": "Updated title", "language": "POL"},
    )

    after = db_connection.execute(
        """
        SELECT
            first_seen_at,
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

    assert after == before

    metadata = db_connection.execute(
        """
        SELECT search_metadata
        FROM raw.notices
        WHERE publication_number = %s
        """,
        (publication_number,),
    ).fetchone()

    assert metadata == (
        {"title": "Updated title", "language": "POL"},
    )

    refreshed = db_connection.execute(
        """
        SELECT last_seen_at > TIMESTAMPTZ '2000-01-02 00:00:00+00'
        FROM raw.notices
        WHERE publication_number = %s
        """,
        (publication_number,),
    ).fetchone()

    assert refreshed == (True,)

    count = db_connection.execute(
        """
        SELECT count(*)
        FROM raw.notices
        WHERE publication_number = %s
        """,
        (publication_number,),
    ).fetchone()

    assert count == (1,)