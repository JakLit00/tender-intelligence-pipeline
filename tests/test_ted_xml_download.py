import io
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from tender_intelligence.ted_client import fetch_notice_xml


def test_downloads_original_bytes_using_normalized_number() -> None:
    xml_content = (
        b'<?xml version="1.0" encoding="ISO-8859-1"?>'
        b"<notice>caf\xe9</notice>"
    )

    with patch(
        "tender_intelligence.ted_client.urlopen",
        return_value=io.BytesIO(xml_content),
    ) as mocked_urlopen:
        result = fetch_notice_xml("00722762-2026")

    assert result == xml_content
    mocked_urlopen.assert_called_once()

    request = mocked_urlopen.call_args.args[0]
    assert request.get_method() == "GET"
    assert request.full_url == (
        "https://ted.europa.eu/en/notice/722762-2026/xml"
    )
    assert request.get_header("Accept") == "application/xml"
    assert mocked_urlopen.call_args.kwargs["timeout"] == 30


@pytest.mark.parametrize("content", [b"", b" \r\n\t"])
def test_rejects_empty_xml_response(content: bytes) -> None:
    with patch(
        "tender_intelligence.ted_client.urlopen",
        return_value=io.BytesIO(content),
    ):
        with pytest.raises(ValueError, match="empty XML response"):
            fetch_notice_xml("722762-2026")


def test_rejects_invalid_publication_before_request() -> None:
    with patch(
        "tender_intelligence.ted_client.urlopen"
    ) as mocked_urlopen:
        with pytest.raises(ValueError, match="Invalid publication number"):
            fetch_notice_xml("invalid")

    mocked_urlopen.assert_not_called()


def test_retries_temporary_failure_when_downloading_xml() -> None:
    headers = Message()
    headers["Retry-After"] = "2"

    error = HTTPError(
        url="https://ted.europa.eu/en/notice/722762-2026/xml",
        code=503,
        msg="Service unavailable",
        hdrs=headers,
        fp=io.BytesIO(b""),
    )
    xml_content = b"<notice/>"

    with (
        patch(
            "tender_intelligence.ted_client.urlopen",
            side_effect=[error, io.BytesIO(xml_content)],
        ) as mocked_urlopen,
        patch("tender_intelligence.ted_client.time.sleep") as mocked_sleep,
    ):
        assert fetch_notice_xml("722762-2026") == xml_content

    assert mocked_urlopen.call_count == 2
    mocked_sleep.assert_called_once_with(2.0)


def test_does_not_retry_missing_xml() -> None:
    error = HTTPError(
        url="https://ted.europa.eu/en/notice/722762-2026/xml",
        code=404,
        msg="Not found",
        hdrs=Message(),
        fp=io.BytesIO(b""),
    )

    with (
        patch(
            "tender_intelligence.ted_client.urlopen",
            side_effect=error,
        ) as mocked_urlopen,
        patch("tender_intelligence.ted_client.time.sleep") as mocked_sleep,
    ):
        with pytest.raises(HTTPError) as caught:
            fetch_notice_xml("722762-2026")

    assert caught.value.code == 404
    mocked_urlopen.assert_called_once()
    mocked_sleep.assert_not_called()