from pathlib import Path
from pprint import pprint

from dotenv import load_dotenv

from tender_intelligence.database import connect_database
from tender_intelligence.xml_parser import parse_notice_lots


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = 5


def main() -> None:
    load_dotenv(
        PROJECT_ROOT / ".env",
        override=False,
        interpolate=False,
    )

    with connect_database() as conn:
        rows = conn.execute(
            """
            SELECT n.publication_number, n.xml_content
            FROM raw.notices AS n
            JOIN ops.run_notices AS r
                ON r.publication_number = n.publication_number
            WHERE r.run_id = %s
              AND r.outcome = 'failed'
            ORDER BY n.publication_number
            """,
            (RUN_ID,),
        ).fetchall()

    for publication_number, xml_content in rows:
        print(f"\nPublication: {publication_number}")

        if xml_content is None:
            print("XML is missing")
            continue

        for lot in parse_notice_lots(bytes(xml_content)):
            pprint(lot, sort_dicts=False)


if __name__ == "__main__":
    main()