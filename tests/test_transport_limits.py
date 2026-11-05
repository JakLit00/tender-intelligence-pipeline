import errno
import io
import socket
import ssl
from http.client import IncompleteRead
from unittest.mock import call, patch
from urllib.error import URLError

import pytest

from tender_intelligence.ted_client import fetch_notice_xml, fetch_search_page


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError(),
        ConnectionResetError(),
        ConnectionAbortedError(),
        URLError(TimeoutError()),
        URLError(socket.gaierror(socket.EAI_AGAIN, "temporary DNS")),
        IncompleteRead(b"partial", 10),
    ],
)
def test_retries_only_transient_transport_failures(error):
    with (
        patch(
            "tender_intelligence.ted_client.urlopen",
            side_effect=[error, io.BytesIO(b"<notice/>")],
        ) as request,
        patch("tender_intelligence.ted_client.time.sleep") as sleep,
    ):
        assert fetch_notice_xml("123-2026") == b"<notice/>"
    assert request.call_count == 2
    sleep.assert_called_once_with(1.0)


@pytest.mark.parametrize(
    "error",
    [
        URLError("unknown failure"),
        URLError(ssl.SSLCertVerificationError("bad certificate")),
        ssl.SSLError("protocol error"),
        URLError(socket.gaierror(socket.EAI_NONAME, "not found")),
        OSError(errno.EACCES, "permission denied"),
    ],
)
def test_does_not_retry_permanent_or_unclassified_transport_failures(error):
    with (
        patch("tender_intelligence.ted_client.urlopen", side_effect=error) as request,
        patch("tender_intelligence.ted_client.time.sleep") as sleep,
    ):
        with pytest.raises(URLError):
            fetch_notice_xml("123-2026")
    request.assert_called_once()
    sleep.assert_not_called()


def test_transport_attempts_are_bounded():
    with (
        patch(
            "tender_intelligence.ted_client.urlopen", side_effect=TimeoutError()
        ) as request,
        patch("tender_intelligence.ted_client.time.sleep") as sleep,
    ):
        with pytest.raises(URLError):
            fetch_notice_xml("123-2026")
    assert request.call_count == 3
    assert sleep.call_args_list == [call(1.0), call(2.0)]


class ChunkedResponse(io.BytesIO):
    headers = {"Content-Length": "1"}
    bytes_read = 0

    def read(self, size=-1):
        assert 0 < size <= 65536
        chunk = super().read(min(size, 3))
        self.bytes_read += len(chunk)
        return chunk


@pytest.mark.parametrize(
    "fetch, argument",
    [(fetch_notice_xml, "123-2026"), (fetch_search_page, "buyer-country = POL")],
)
@pytest.mark.parametrize("headers", [{}, {"Content-Length": "1"}])
def test_enforces_actual_byte_limit_despite_small_or_missing_content_length(
    fetch, argument, headers
):
    response = ChunkedResponse(b"x" * 100)
    response.headers = headers
    with (
        patch("tender_intelligence.ted_client.MAX_RESPONSE_BYTES", 10),
        patch(
            "tender_intelligence.ted_client.urlopen", return_value=response
        ) as request,
    ):
        with pytest.raises(ValueError, match="byte limit"):
            fetch(argument)
    assert response.closed
    assert response.bytes_read == 11
    request.assert_called_once()


def test_accepts_exact_byte_limit():
    with (
        patch("tender_intelligence.ted_client.MAX_RESPONSE_BYTES", 10),
        patch(
            "tender_intelligence.ted_client.urlopen",
            return_value=ChunkedResponse(b"x" * 10),
        ),
    ):
        assert fetch_notice_xml("123-2026") == b"x" * 10


def test_retries_failure_during_body_read_without_reusing_partial_data():
    class InterruptedBody(io.BytesIO):
        def read(self, size=-1):
            if self.tell():
                raise ConnectionResetError()
            return super().read(3)

    first = InterruptedBody(b"broken content")
    with (
        patch(
            "tender_intelligence.ted_client.urlopen",
            side_effect=[first, io.BytesIO(b"<ok/>")],
        ),
        patch("tender_intelligence.ted_client.time.sleep"),
    ):
        assert fetch_notice_xml("123-2026") == b"<ok/>"
    assert first.closed
