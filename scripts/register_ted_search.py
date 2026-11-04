from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from tender_intelligence.database import connect_database
from tender_intelligence.ingestion import register_search_results
from tender_intelligence.ted_client import fetch_all_notices


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    load_dotenv(
        PROJECT_ROOT / ".env",
        override=False,
        interpolate=False,
    )

    date_from = date(2026, 10, 20)
    date_to = date(2026, 10, 29)

    query = (
        "buyer-country = POL "
        "AND classification-cpv = 72* "
        "AND notice-type = cn-standard "
        f"AND publication-date >= {date_from:%Y%m%d} "
        f"AND publication-date <= {date_to:%Y%m%d}"
    )

    print(f"Searching publications from {date_from} to {date_to}")
    notices = fetch_all_notices(query)
    print(f"Fetched publications: {len(notices)}")

    # Finish network requests before opening the database connection.
    with connect_database() as conn:
        identity = conn.execute(
            "SELECT current_database(), current_user"
        ).fetchone()

        if identity != ("tender_intelligence", "tender_app"):
            raise RuntimeError(
                "Expected the working database and application role"
            )

        registered_count = register_search_results(conn, notices)
        print(f"Registered publications: {registered_count}")

        sample = conn.execute(
            """
            SELECT
                publication_number,
                publication_date,
                processing_status,
                xml_content IS NOT NULL AS has_xml
            FROM raw.notices
            WHERE publication_number = %s
            """,
            ("722762-2026",),
        ).fetchone()

        print(f"Known publication: {sample}")


if __name__ == "__main__":
    main()