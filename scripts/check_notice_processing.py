from pathlib import Path
from unittest.mock import patch

import psycopg
from dotenv import load_dotenv

from tender_intelligence.database import connect_database
from tender_intelligence.models import PreparedNoticeBundle
from tender_intelligence.preparation import prepare_notice
from tender_intelligence.processing import process_notice
from tender_intelligence.storage import save_prepared_notice

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLICATION_NUMBER = "722762-2026"


def read_status(conn: psycopg.Connection) -> tuple:
    row = conn.execute(
        """
        SELECT processing_status, processed_at, last_error
        FROM raw.notices
        WHERE publication_number = %s
        """,
        (PUBLICATION_NUMBER,),
    ).fetchone()

    if row is None:
        raise AssertionError("Raw notice is missing")

    return row


def read_staging(conn: psycopg.Connection) -> tuple:
    notice_rows = conn.execute(
        """
        SELECT *
        FROM staging.notices
        WHERE publication_number = %s
        """,
        (PUBLICATION_NUMBER,),
    ).fetchall()

    lot_rows = conn.execute(
        """
        SELECT *
        FROM staging.notice_lots
        WHERE publication_number = %s
        ORDER BY lot_id
        """,
        (PUBLICATION_NUMBER,),
    ).fetchall()

    return notice_rows, lot_rows


def save_then_fail(
    conn: psycopg.Connection,
    bundle: PreparedNoticeBundle,
) -> None:
    save_prepared_notice(conn, bundle)

    # Fail after staging writes to verify the outer transaction rolls them back.
    conn.execute("SELECT 1 / 0")


def main() -> None:
    load_dotenv(
        PROJECT_ROOT / ".env",
        override=False,
        interpolate=False,
    )

    xml_path = PROJECT_ROOT / "data" / "inspection" / f"{PUBLICATION_NUMBER}.xml"
    xml_content = xml_path.read_bytes()
    prepared = prepare_notice(
        xml_content,
        expected_publication_number=PUBLICATION_NUMBER,
    )

    with connect_database() as conn:
        with conn.transaction(force_rollback=True):
            # Fail on an existing publication instead of replacing its raw data.
            conn.execute(
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
                    '{"source": "processing-check"}',
                    xml_content,
                ),
            )

            before_failure = (
                read_status(conn),
                read_staging(conn),
            )

            with patch(
                "tender_intelligence.processing.save_prepared_notice",
                side_effect=save_then_fail,
            ):
                try:
                    process_notice(conn, PUBLICATION_NUMBER)
                except psycopg.errors.DivisionByZero:
                    pass
                else:
                    raise AssertionError("Expected a database error")

            assert (
                read_status(conn),
                read_staging(conn),
            ) == before_failure
            print("PASS: database error rolls back staging and status")

            outcome = process_notice(conn, PUBLICATION_NUMBER)
            assert outcome == "processed"

            status, processed_at, last_error = read_status(conn)
            assert status == "succeeded"
            assert processed_at is not None
            assert last_error is None

            notice_rows, lot_rows = read_staging(conn)
            assert len(notice_rows) == 1
            assert len(lot_rows) == len(prepared.lots)
            print("PASS: real XML processed and success recorded")

            before_skip = (
                read_status(conn),
                read_staging(conn),
            )

            outcome = process_notice(conn, PUBLICATION_NUMBER)
            assert outcome == "skipped"
            assert (
                read_status(conn),
                read_staging(conn),
            ) == before_skip
            print("PASS: successful notice skipped without changes")

            outcome = process_notice(
                conn,
                PUBLICATION_NUMBER,
                force=True,
            )
            assert outcome == "processed"
            assert read_status(conn)[0] == "succeeded"
            print("PASS: forced reprocessing succeeds")

            previous_staging = read_staging(conn)

            # Simulate a damaged source to exercise the parsing failure path.
            conn.execute(
                """
                UPDATE raw.notices
                SET xml_content = %s
                WHERE publication_number = %s
                """,
                (b"<broken", PUBLICATION_NUMBER),
            )

            outcome = process_notice(
                conn,
                PUBLICATION_NUMBER,
                force=True,
            )
            assert outcome == "failed"

            status, processed_at, last_error = read_status(conn)
            assert status == "failed"
            assert processed_at is None
            assert last_error.startswith("ParseError:")
            assert read_staging(conn) == previous_staging
            print("PASS: parsing error recorded and previous staging preserved")

            conn.execute(
                """
                UPDATE raw.notices
                SET xml_content = %s
                WHERE publication_number = %s
                """,
                (xml_content, PUBLICATION_NUMBER),
            )

            outcome = process_notice(conn, PUBLICATION_NUMBER)
            assert outcome == "processed"

            status, processed_at, last_error = read_status(conn)
            assert status == "succeeded"
            assert processed_at is not None
            assert last_error is None

            notice_rows, lot_rows = read_staging(conn)
            assert len(notice_rows) == 1
            assert len(lot_rows) == len(prepared.lots)
            print("PASS: failed notice retried and error cleared")

        raw_count = conn.execute(
            """
            SELECT count(*)
            FROM raw.notices
            WHERE publication_number = %s
            """,
            (PUBLICATION_NUMBER,),
        ).fetchone()

        assert raw_count == (0,)
        assert read_staging(conn) == ([], [])
        print("PASS: all test data rolled back")


if __name__ == "__main__":
    main()
