from unittest.mock import call, patch

import pytest

from tender_intelligence.ted_client import fetch_all_notices


def make_page(
    numbers: list[str],
    *,
    total: int,
    token: str | None = None,
) -> dict:
    return {
        "notices": [{"publication-number": number} for number in numbers],
        "totalNoticeCount": total,
        "iterationNextToken": token,
        "timedOut": False,
    }


def test_collects_pages_and_passes_tokens() -> None:
    pages = [
        make_page(["100-2026"], total=3, token="token-1"),
        make_page(["101-2026"], total=3, token="token-2"),
        make_page(["102-2026"], total=3, token="final-token"),
    ]

    with patch(
        "tender_intelligence.ted_client.fetch_search_page",
        side_effect=pages,
    ) as fetch_page:
        result = fetch_all_notices("buyer-country = POL", page_size=1)

    assert [notice["publication-number"] for notice in result] == [
        "100-2026",
        "101-2026",
        "102-2026",
    ]
    assert fetch_page.call_args_list == [
        call("buyer-country = POL", iteration_token=None, limit=1),
        call("buyer-country = POL", iteration_token="token-1", limit=1),
        call("buyer-country = POL", iteration_token="token-2", limit=1),
    ]


def test_returns_empty_list_for_zero_results() -> None:
    with patch(
        "tender_intelligence.ted_client.fetch_search_page",
        return_value=make_page([], total=0),
    ) as fetch_page:
        assert fetch_all_notices("buyer-country = POL") == []

    fetch_page.assert_called_once()


def test_rejects_changed_total_count() -> None:
    pages = [
        make_page(["100-2026"], total=2, token="token-1"),
        make_page(["101-2026"], total=3, token="token-2"),
    ]

    with patch(
        "tender_intelligence.ted_client.fetch_search_page",
        side_effect=pages,
    ):
        with pytest.raises(ValueError, match="count changed"):
            fetch_all_notices("buyer-country = POL")


def test_rejects_repeated_publication() -> None:
    pages = [
        make_page(["100-2026"], total=2, token="token-1"),
        make_page(["100-2026"], total=2),
    ]

    with patch(
        "tender_intelligence.ted_client.fetch_search_page",
        side_effect=pages,
    ):
        with pytest.raises(ValueError, match="Repeated publication"):
            fetch_all_notices("buyer-country = POL")


def test_rejects_repeated_token_before_completion() -> None:
    pages = [
        make_page(["100-2026"], total=3, token="token-1"),
        make_page(["101-2026"], total=3, token="token-1"),
    ]

    with patch(
        "tender_intelligence.ted_client.fetch_search_page",
        side_effect=pages,
    ) as fetch_page:
        with pytest.raises(ValueError, match="Repeated iteration token"):
            fetch_all_notices("buyer-country = POL")

    assert fetch_page.call_count == 2


@pytest.mark.parametrize("token", [None, "", " "])
def test_rejects_missing_token_before_completion(token: str | None) -> None:
    with patch(
        "tender_intelligence.ted_client.fetch_search_page",
        return_value=make_page(["100-2026"], total=2, token=token),
    ):
        with pytest.raises(ValueError, match="Missing iteration token"):
            fetch_all_notices("buyer-country = POL")


def test_rejects_empty_page_before_completion() -> None:
    pages = [
        make_page(["100-2026"], total=2, token="token-1"),
        make_page([], total=2, token="token-2"),
    ]

    with patch(
        "tender_intelligence.ted_client.fetch_search_page",
        side_effect=pages,
    ):
        with pytest.raises(ValueError, match="empty page"):
            fetch_all_notices("buyer-country = POL")


def test_rejects_more_results_than_reported() -> None:
    with patch(
        "tender_intelligence.ted_client.fetch_search_page",
        return_value=make_page(
            ["100-2026", "101-2026"],
            total=1,
        ),
    ):
        with pytest.raises(ValueError, match="more notices"):
            fetch_all_notices("buyer-country = POL")


@pytest.mark.parametrize(
    "notice",
    [
        {},
        {"publication-number": None},
        {"publication-number": " "},
        {"publication-number": 100},
    ],
)
def test_rejects_invalid_publication_number(notice: dict) -> None:
    page = make_page([], total=1)
    page["notices"] = [notice]

    with patch(
        "tender_intelligence.ted_client.fetch_search_page",
        return_value=page,
    ):
        with pytest.raises(ValueError, match="publication number"):
            fetch_all_notices("buyer-country = POL")


def test_does_not_return_partial_results_after_page_failure() -> None:
    with patch(
        "tender_intelligence.ted_client.fetch_search_page",
        side_effect=[
            make_page(["100-2026"], total=2, token="token-1"),
            ValueError("TED search timed out"),
        ],
    ):
        with pytest.raises(ValueError, match="timed out"):
            fetch_all_notices("buyer-country = POL")
