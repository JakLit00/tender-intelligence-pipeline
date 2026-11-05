import io
import json
from datetime import datetime, timedelta, timezone
from email.message import Message
from email.utils import format_datetime
from unittest.mock import call, patch
from urllib.error import HTTPError, URLError

import pytest

from tender_intelligence.ted_client import fetch_search_page


def json_response(payload: object) -> io.BytesIO:
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


def test_fetches_first_page_without_iteration_token() -> None:
    response = {
        "notices": [{"publication-number": "722762-2026"}],
        "totalNoticeCount": 132,
        "iterationNextToken": "next-page-token",
        "timedOut": False,
    }

    with patch(
        "tender_intelligence.ted_client.urlopen",
        return_value=json_response(response),
    ) as mocked_urlopen:
        result = fetch_search_page("buyer-country = POL", limit=5)

    assert result == response
    mocked_urlopen.assert_called_once()

    request = mocked_urlopen.call_args.args[0]
    payload = json.loads(request.data)

    assert request.get_method() == "POST"
    assert request.full_url == ("https://api.ted.europa.eu/v3/notices/search")
    assert payload["query"] == "buyer-country = POL"
    assert payload["scope"] == "ALL"
    assert payload["paginationMode"] == "ITERATION"
    assert payload["limit"] == 5
    assert "publication-number" in payload["fields"]
    assert "publication-date" in payload["fields"]
    assert "iterationNextToken" not in payload
    assert mocked_urlopen.call_args.kwargs["timeout"] == 30


def test_passes_iteration_token_to_next_request() -> None:
    response = {
        "notices": [],
        "totalNoticeCount": 132,
        "iterationNextToken": None,
        "timedOut": False,
    }

    with patch(
        "tender_intelligence.ted_client.urlopen",
        return_value=json_response(response),
    ) as mocked_urlopen:
        fetch_search_page(
            "buyer-country = POL",
            iteration_token="previous-page-token",
        )

    request = mocked_urlopen.call_args.args[0]
    payload = json.loads(request.data)

    assert payload["iterationNextToken"] == "previous-page-token"


@pytest.mark.parametrize(
    "response",
    [
        {
            "notices": [],
            "totalNoticeCount": 0,
            "timedOut": True,
        },
        {
            "notices": [],
            "totalNoticeCount": 0,
        },
    ],
)
def test_rejects_timeout_or_missing_timeout_status(response: dict) -> None:
    with patch(
        "tender_intelligence.ted_client.urlopen",
        return_value=json_response(response),
    ):
        with pytest.raises(ValueError, match="timeout|timed out"):
            fetch_search_page("buyer-country = POL")


@pytest.mark.parametrize(
    ("response", "message"),
    [
        ([], "Expected a JSON object"),
        (
            {"notices": {}, "totalNoticeCount": 0, "timedOut": False},
            "Expected a notices list",
        ),
        (
            {"notices": ["invalid"], "totalNoticeCount": 1, "timedOut": False},
            "Expected each notice",
        ),
        (
            {"notices": [], "totalNoticeCount": -1, "timedOut": False},
            "non-negative total notice count",
        ),
        (
            {"notices": [], "totalNoticeCount": True, "timedOut": False},
            "non-negative total notice count",
        ),
        (
            {
                "notices": [],
                "totalNoticeCount": 0,
                "timedOut": False,
                "iterationNextToken": 123,
            },
            "iteration token",
        ),
    ],
)
def test_rejects_invalid_response_structure(
    response: object,
    message: str,
) -> None:
    with patch(
        "tender_intelligence.ted_client.urlopen",
        return_value=json_response(response),
    ):
        with pytest.raises(ValueError, match=message):
            fetch_search_page("buyer-country = POL")


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": " "},
        {"query": "buyer-country = POL", "limit": 0},
        {"query": "buyer-country = POL", "limit": 251},
        {"query": "buyer-country = POL", "iteration_token": " "},
    ],
)
def test_rejects_invalid_arguments_before_http_request(
    arguments: dict,
) -> None:
    with patch("tender_intelligence.ted_client.urlopen") as mocked_urlopen:
        with pytest.raises(ValueError):
            fetch_search_page(**arguments)

    mocked_urlopen.assert_not_called()


def test_propagates_network_failure() -> None:
    with patch(
        "tender_intelligence.ted_client.urlopen",
        side_effect=URLError("Connection unavailable"),
    ):
        with pytest.raises(URLError, match="Connection unavailable"):
            fetch_search_page("buyer-country = POL")


def test_rejects_invalid_json() -> None:
    with patch(
        "tender_intelligence.ted_client.urlopen",
        return_value=io.BytesIO(b"not a JSON response"),
    ):
        with pytest.raises(json.JSONDecodeError):
            fetch_search_page("buyer-country = POL")


def http_error(
    status: int,
    retry_after: str | None = None,
) -> HTTPError:
    headers = Message()

    if retry_after is not None:
        headers["Retry-After"] = retry_after

    return HTTPError(
        url="https://api.ted.europa.eu/v3/notices/search",
        code=status,
        msg="Test HTTP error",
        hdrs=headers,
        fp=io.BytesIO(b""),
    )


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retries_transient_http_error(status: int) -> None:
    response = {
        "notices": [],
        "totalNoticeCount": 0,
        "timedOut": False,
    }

    with (
        patch(
            "tender_intelligence.ted_client.urlopen",
            side_effect=[
                http_error(status),
                json_response(response),
            ],
        ) as mocked_urlopen,
        patch("tender_intelligence.ted_client.time.sleep") as mocked_sleep,
    ):
        result = fetch_search_page("buyer-country = POL")

    assert result == response
    assert mocked_urlopen.call_count == 2
    mocked_sleep.assert_called_once_with(1.0)


def test_stops_after_three_failed_attempts() -> None:
    errors = [http_error(503) for _ in range(3)]

    with (
        patch(
            "tender_intelligence.ted_client.urlopen",
            side_effect=errors,
        ) as mocked_urlopen,
        patch("tender_intelligence.ted_client.time.sleep") as mocked_sleep,
    ):
        with pytest.raises(HTTPError) as caught:
            fetch_search_page("buyer-country = POL")

    assert caught.value is errors[-1]
    assert mocked_urlopen.call_count == 3
    assert mocked_sleep.call_args_list == [call(1.0), call(2.0)]


def test_does_not_retry_bad_request() -> None:
    with (
        patch(
            "tender_intelligence.ted_client.urlopen",
            side_effect=http_error(400),
        ) as mocked_urlopen,
        patch("tender_intelligence.ted_client.time.sleep") as mocked_sleep,
    ):
        with pytest.raises(HTTPError) as caught:
            fetch_search_page("invalid query")

    assert caught.value.code == 400
    mocked_urlopen.assert_called_once()
    mocked_sleep.assert_not_called()


def test_respects_retry_after_seconds() -> None:
    response = {
        "notices": [],
        "totalNoticeCount": 0,
        "timedOut": False,
    }

    with (
        patch(
            "tender_intelligence.ted_client.urlopen",
            side_effect=[
                http_error(429, "7"),
                json_response(response),
            ],
        ),
        patch("tender_intelligence.ted_client.time.sleep") as mocked_sleep,
    ):
        assert fetch_search_page("buyer-country = POL") == response

    mocked_sleep.assert_called_once_with(7.0)


def test_respects_retry_after_http_date() -> None:
    now = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
    retry_at = format_datetime(now + timedelta(seconds=10), usegmt=True)
    response = {
        "notices": [],
        "totalNoticeCount": 0,
        "timedOut": False,
    }

    with (
        patch(
            "tender_intelligence.ted_client.urlopen",
            side_effect=[
                http_error(503, retry_at),
                json_response(response),
            ],
        ),
        patch("tender_intelligence.ted_client.datetime") as mocked_datetime,
        patch("tender_intelligence.ted_client.time.sleep") as mocked_sleep,
    ):
        mocked_datetime.now.return_value = now
        assert fetch_search_page("buyer-country = POL") == response

    mocked_sleep.assert_called_once_with(10.0)


def test_invalid_retry_after_uses_fallback_delay() -> None:
    response = {
        "notices": [],
        "totalNoticeCount": 0,
        "timedOut": False,
    }

    with (
        patch(
            "tender_intelligence.ted_client.urlopen",
            side_effect=[
                http_error(503, "not-a-date"),
                json_response(response),
            ],
        ),
        patch("tender_intelligence.ted_client.time.sleep") as mocked_sleep,
    ):
        assert fetch_search_page("buyer-country = POL") == response

    mocked_sleep.assert_called_once_with(1.0)


def test_long_retry_after_stops_without_retrying_early() -> None:
    with (
        patch(
            "tender_intelligence.ted_client.urlopen",
            side_effect=http_error(429, "120"),
        ) as mocked_urlopen,
        patch("tender_intelligence.ted_client.time.sleep") as mocked_sleep,
    ):
        with pytest.raises(HTTPError) as caught:
            fetch_search_page("buyer-country = POL")

    assert caught.value.code == 429
    mocked_urlopen.assert_called_once()
    mocked_sleep.assert_not_called()
