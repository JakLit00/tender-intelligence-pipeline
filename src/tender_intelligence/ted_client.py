import json
from typing import Any
from urllib.request import Request, urlopen
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError


SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"

SEARCH_FIELDS = (
    "publication-number",
    "publication-date",
    "notice-type",
    "notice-title",
    "buyer-name",
    "classification-cpv",
)

RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
MAX_RETRY_DELAY_SECONDS = 60


def _retry_delay(value: str | None, *, attempt: int) -> float:
    fallback = float(2 ** (attempt - 1))

    if value is None:
        return fallback

    value = value.strip()

    if value.isascii() and value.isdigit():
        return float(value)

    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return fallback

    if retry_at.tzinfo is None:
        return fallback

    return max(
        0.0,
        (retry_at - datetime.now(timezone.utc)).total_seconds(),
    )


def _request_search_json(request: Request) -> Any:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            if (
                exc.code not in RETRYABLE_HTTP_CODES
                or attempt == MAX_ATTEMPTS
            ):
                raise

            delay = _retry_delay(
                exc.headers.get("Retry-After"),
                attempt=attempt,
            )

            # Stop rather than retry earlier than the server requested.
            if delay > MAX_RETRY_DELAY_SECONDS:
                raise

            exc.close()
            time.sleep(delay)

    raise RuntimeError("Search request attempts exhausted")

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

    result = _request_search_json(request)

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