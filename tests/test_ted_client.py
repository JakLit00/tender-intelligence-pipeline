import io
import json
from unittest.mock import patch
from urllib.error import URLError

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
    assert request.full_url == (
        "https://api.ted.europa.eu/v3/notices/search"
    )
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
    with patch(
        "tender_intelligence.ted_client.urlopen"
    ) as mocked_urlopen:
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