from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from tender_intelligence.database import connect_database
from tender_intelligence.models import (
    PreparedLot,
    PreparedNotice,
    PreparedNoticeBundle,
)
from tender_intelligence.storage import save_prepared_notice

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLICATION_NUMBER = "999999-2099"


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


def main() -> None:
    load_dotenv(
        PROJECT_ROOT / ".env",
        override=False,
        interpolate=False,
    )

    notice = PreparedNotice(
        publication_number=PUBLICATION_NUMBER,
        notice_id="8ac273c6-7603-4ad1-b9a2-8ed027ed773f",
        notice_version="01",
        procedure_id="4835bb55-6b3a-4579-81d8-b34df3e663ce",
        notice_type="cn-standard",
        publication_date=date(2099, 1, 1),
        changed_notice_identifier_raw=None,
        reference_type="missing",
        previous_publication_number=None,
        previous_notice_id=None,
        previous_notice_version=None,
        change_reason_code=None,
    )

    first_lot = PreparedLot(
        publication_number=PUBLICATION_NUMBER,
        lot_id="LOT-0001",
        submission_deadline_date_raw="2099-02-01Z",
        submission_deadline_time_raw="09:00:00Z",
        submission_deadline_local_date=date(2099, 2, 1),
        submission_deadline_at=datetime(2099, 2, 1, 9, 0, tzinfo=timezone.utc),
    )
    second_lot = replace(first_lot, lot_id="LOT-0002")
    bundle = PreparedNoticeBundle(
        notice=notice,
        lots=(first_lot, second_lot),
    )

    with connect_database() as conn:
        with conn.transaction(force_rollback=True):
            # A collision must fail rather than overwrite existing raw data.
            conn.execute(
                """
                INSERT INTO raw.notices (
                    publication_number,
                    publication_date,
                    search_metadata
                )
                VALUES (%s, %s, %s::jsonb)
                """,
                (
                    PUBLICATION_NUMBER,
                    notice.publication_date,
                    '{"source": "storage-check"}',
                ),
            )

            save_prepared_notice(conn, bundle)
            notice_rows, lot_rows = read_staging(conn)
            assert len(notice_rows) == 1
            assert len(lot_rows) == 2
            print("PASS: notice and two lots saved")

            save_prepared_notice(conn, bundle)
            notice_rows, lot_rows = read_staging(conn)
            assert len(notice_rows) == 1
            assert len(lot_rows) == 2
            print("PASS: repeated save creates no duplicates")

            updated_notice = replace(
                notice,
                change_reason_code="cor-buy",
            )
            reduced_bundle = PreparedNoticeBundle(
                notice=updated_notice,
                lots=(first_lot,),
            )

            save_prepared_notice(conn, reduced_bundle)

            lot_ids = conn.execute(
                """
                SELECT lot_id
                FROM staging.notice_lots
                WHERE publication_number = %s
                ORDER BY lot_id
                """,
                (PUBLICATION_NUMBER,),
            ).fetchall()
            assert lot_ids == [("LOT-0001",)]

            reason = conn.execute(
                """
                SELECT change_reason_code
                FROM staging.notices
                WHERE publication_number = %s
                """,
                (PUBLICATION_NUMBER,),
            ).fetchone()
            assert reason == ("cor-buy",)
            print("PASS: notice updated and obsolete lot removed")

            before_failure = read_staging(conn)

            # Bypass preparation to trigger a database constraint after DELETE.
            invalid_lot = replace(first_lot, lot_id="")
            invalid_bundle = PreparedNoticeBundle(
                notice=replace(
                    updated_notice,
                    change_reason_code="update-add",
                ),
                lots=(second_lot, invalid_lot),
            )

            try:
                save_prepared_notice(conn, invalid_bundle)
            except psycopg.errors.CheckViolation:
                pass
            else:
                raise AssertionError("The database accepted an empty lot ID")

            assert read_staging(conn) == before_failure
            print("PASS: failed save restores notice and previous lots")

            save_prepared_notice(
                conn,
                PreparedNoticeBundle(
                    notice=updated_notice,
                    lots=(),
                ),
            )
            notice_rows, lot_rows = read_staging(conn)
            assert len(notice_rows) == 1
            assert lot_rows == []
            print("PASS: empty lot set removes all previous lots")

        for table in ("raw.notices", "staging.notices", "staging.notice_lots"):
            query = psycopg.sql.SQL(
                "SELECT count(*) FROM {} WHERE publication_number = %s"
            ).format(psycopg.sql.Identifier(*table.split(".")))

            assert conn.execute(
                query,
                (PUBLICATION_NUMBER,),
            ).fetchone() == (0,)

        print("PASS: all test data rolled back")


if __name__ == "__main__":
    main()
