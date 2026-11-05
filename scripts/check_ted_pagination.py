import json
from pathlib import Path

from tender_intelligence.ted_client import fetch_all_notices

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    query = (
        "buyer-country = POL "
        "AND classification-cpv = 72* "
        "AND notice-type = cn-standard "
        "AND publication-date >= 20261020 "
        "AND publication-date <= 20261029"
    )

    notices = fetch_all_notices(query, page_size=100)

    publication_numbers = [notice["publication-number"] for notice in notices]

    output_path = PROJECT_ROOT / "data" / "inspection" / "search_notices.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(notices, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Collected notices: {len(notices)}")
    print(f"Unique publication numbers: {len(set(publication_numbers))}")
    print(
        "Known publication present:",
        "722762-2026" in publication_numbers,
    )
    print(f"Saved results: {output_path}")


if __name__ == "__main__":
    main()
