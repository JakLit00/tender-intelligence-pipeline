from pathlib import Path

from dotenv import load_dotenv

from tender_intelligence.database import connect_database
from tender_intelligence.processing import process_notice
from tender_intelligence.storage import save_notice_xml
from tender_intelligence.ted_client import fetch_notice_xml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLICATION_NUMBER = "722762-2026"


def main() -> None:
    load_dotenv(
        PROJECT_ROOT / ".env",
        override=False,
        interpolate=False,
    )

    print(f"Downloading XML: {PUBLICATION_NUMBER}")
    xml_content = fetch_notice_xml(PUBLICATION_NUMBER)
    print(f"Downloaded bytes: {len(xml_content)}")

    with connect_database() as conn:
        identity = conn.execute(
            "SELECT current_database(), current_user"
        ).fetchone()

        if identity != ("tender_intelligence", "tender_app"):
            raise RuntimeError(
                "Expected the working database and application role"
            )

        requires_processing = save_notice_xml(
            conn,
            PUBLICATION_NUMBER,
            xml_content,
        )
        print(f"Requires processing: {requires_processing}")

        outcome = process_notice(conn, PUBLICATION_NUMBER)
        print(f"Processing outcome: {outcome}")

        status = conn.execute(
            """
            SELECT processing_status, processed_at, last_error
            FROM raw.notices
            WHERE publication_number = %s
            """,
            (PUBLICATION_NUMBER,),
        ).fetchone()
        print(f"Raw status: {status}")

        lots = conn.execute(
            """
            SELECT
                lot_id,
                submission_deadline_local_date,
                submission_deadline_at AT TIME ZONE 'UTC' AS deadline_utc
            FROM staging.notice_lots
            WHERE publication_number = %s
            ORDER BY lot_id
            """,
            (PUBLICATION_NUMBER,),
        ).fetchall()

        print("Stored lots (deadline in UTC):")
        for lot in lots:
            print(lot)

        if outcome == "failed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()