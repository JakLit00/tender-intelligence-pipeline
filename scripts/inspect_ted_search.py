import json
from pathlib import Path
from pprint import pprint
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"


def main() -> None:
    payload = {
        "query": (
            "buyer-country = POL "
            "AND classification-cpv = 72* "
            "AND notice-type = cn-standard "
            "AND publication-date >= 20261020 "
            "AND publication-date <= 20261029"
        ),
        "fields": [
            "publication-number",
            "publication-date",
            "notice-type",
            "notice-title",
            "buyer-name",
            "classification-cpv",
        ],
        "scope": "ALL",
        "paginationMode": "ITERATION",
        "limit": 5,
    }

    request = Request(
        SEARCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "tender-intelligence-pipeline/0.1",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
    except HTTPError as exc:
        print(f"HTTP error: {exc.code}")
        print(f"Retry-After: {exc.headers.get('Retry-After')}")
        print(exc.read().decode("utf-8", errors="replace")[:2000])
        raise SystemExit(1) from exc

    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object from TED")

    output_path = PROJECT_ROOT / "data" / "inspection" / "search_sample.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Response keys: {list(result)}")
    print(f"Total notice count: {result.get('totalNoticeCount')}")

    notices = result.get("notices")
    if not isinstance(notices, list):
        raise ValueError("Expected a notices list in the response")

    print(f"Returned notices: {len(notices)}")
    print(
        "Next iteration token present:",
        bool(result.get("iterationNextToken")),
    )

    if notices:
        print("\nFirst notice:")
        pprint(notices[0], sort_dicts=False)

    print(f"\nSaved response: {output_path}")


if __name__ == "__main__":
    main()
