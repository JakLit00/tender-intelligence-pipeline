import json
from typing import Any
from urllib.request import Request, urlopen


SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"

SEARCH_FIELDS = (
    "publication-number",
    "publication-date",
    "notice-type",
    "notice-title",
    "buyer-name",
    "classification-cpv",
)


def fetch_search_page(
    query: str,
    *,
    iteration_token: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Fetch and validate one page of TED search results."""
    if not query.strip():
        raise ValueError("Search query must not be empty")

    if not 1 <= limit <= 250:
        raise ValueError("Search limit must be between 1 and 250")

    if iteration_token is not None and not iteration_token.strip():
        raise ValueError("Iteration token must not be empty")

    payload = {
        "query": query,
        "fields": list(SEARCH_FIELDS),
        "scope": "ALL",
        "paginationMode": "ITERATION",
        "limit": limit,
    }

    if iteration_token is not None:
        payload["iterationNextToken"] = iteration_token

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

    with urlopen(request, timeout=30) as response:
        result = json.load(response)

    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object from TED")

    # A successful HTTP response may still contain incomplete search results.
    if result.get("timedOut") is not False:
        raise ValueError("TED search timed out or omitted its timeout status")

    notices = result.get("notices")
    if not isinstance(notices, list):
        raise ValueError("Expected a notices list from TED")

    if any(not isinstance(notice, dict) for notice in notices):
        raise ValueError("Expected each notice to be a JSON object")

    total_count = result.get("totalNoticeCount")
    if type(total_count) is not int or total_count < 0:
        raise ValueError("Expected a non-negative total notice count")

    next_token = result.get("iterationNextToken")
    if next_token is not None and not isinstance(next_token, str):
        raise ValueError("Expected an iteration token string or null")

    return result