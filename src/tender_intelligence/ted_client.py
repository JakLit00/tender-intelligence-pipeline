import json
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tender_intelligence.normalization import normalize_publication_number

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


def _request_bytes(request: Request) -> bytes:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code not in RETRYABLE_HTTP_CODES or attempt == MAX_ATTEMPTS:
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

    result = json.loads(_request_bytes(request))

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


def fetch_all_notices(
    query: str,
    *,
    page_size: int = 100,
) -> list[dict[str, Any]]:
    """Collect all search results, rejecting incomplete or repeated pages."""
    notices: list[dict[str, Any]] = []
    seen_publications: set[str] = set()
    seen_tokens: set[str] = set()
    iteration_token = None
    expected_total = None

    while True:
        page = fetch_search_page(
            query,
            iteration_token=iteration_token,
            limit=page_size,
        )

        total_count = page["totalNoticeCount"]

        if expected_total is None:
            expected_total = total_count
        elif total_count != expected_total:
            raise ValueError("TED result count changed during pagination")

        page_notices = page["notices"]

        for notice in page_notices:
            publication_number = notice.get("publication-number")

            if (
                not isinstance(publication_number, str)
                or not publication_number.strip()
            ):
                raise ValueError(
                    "Missing or invalid publication number in search results"
                )

            if publication_number in seen_publications:
                raise ValueError(
                    f"Repeated publication during pagination: {publication_number}"
                )

            seen_publications.add(publication_number)
            notices.append(notice)

        if len(notices) > expected_total:
            raise ValueError("Received more notices than the reported total")

        # A final response may still carry a token; use the count to finish.
        if len(notices) == expected_total:
            return notices

        if not page_notices:
            raise ValueError("Received an empty page before collecting all notices")

        next_token = page.get("iterationNextToken")

        if not isinstance(next_token, str) or not next_token.strip():
            raise ValueError("Missing iteration token before collecting all notices")

        if next_token in seen_tokens:
            raise ValueError("Repeated iteration token during pagination")

        seen_tokens.add(next_token)
        iteration_token = next_token


def fetch_notice_xml(publication_number: str) -> bytes:
    """Download the original XML bytes for a TED publication."""
    publication_number = normalize_publication_number(publication_number)

    request = Request(
        f"https://ted.europa.eu/en/notice/{publication_number}/xml",
        headers={
            "Accept": "application/xml",
            "User-Agent": "tender-intelligence-pipeline/0.1",
        },
        method="GET",
    )

    xml_content = _request_bytes(request)

    if not xml_content.strip():
        raise ValueError(f"TED returned an empty XML response: {publication_number}")

    return xml_content
