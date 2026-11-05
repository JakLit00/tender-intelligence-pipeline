from dataclasses import replace
from unittest.mock import patch

import pytest

from tender_intelligence.predecessors import (
    download_predecessor,
    find_notice_version,
    validate_predecessor,
)
from tender_intelligence.preparation import prepare_notice

NOTICE_ID = "d7678430-ecb9-47e2-9a76-6c6f70962ff0"


def test_finds_notice_by_exact_id_and_version():
    notice = {"publication-number": "717699-2026"}

    with patch(
        "tender_intelligence.predecessors.fetch_all_notices",
        return_value=[notice],
    ) as fetch:
        result = find_notice_version(NOTICE_ID, "02")

    assert result == notice
    fetch.assert_called_once_with(
        f'notice-identifier = "{NOTICE_ID}" AND notice-version = "02"',
        page_size=10,
    )


def test_returns_none_when_predecessor_is_not_found():
    with patch(
        "tender_intelligence.predecessors.fetch_all_notices",
        return_value=[],
    ):
        assert find_notice_version(NOTICE_ID, "02") is None


def test_rejects_ambiguous_matches():
    notices = [
        {"publication-number": "717699-2026"},
        {"publication-number": "717700-2026"},
    ]

    with patch(
        "tender_intelligence.predecessors.fetch_all_notices",
        return_value=notices,
    ):
        with pytest.raises(ValueError, match="Ambiguous notice version"):
            find_notice_version(NOTICE_ID, "02")


@pytest.mark.parametrize("version", ["2", "002", "ab"])
def test_rejects_invalid_version_before_search(version):
    with patch(
        "tender_intelligence.predecessors.fetch_all_notices",
    ) as fetch:
        with pytest.raises(ValueError, match="exactly two digits"):
            find_notice_version(NOTICE_ID, version)

    fetch.assert_not_called()


@pytest.fixture
def notice_pair(notice_xml):
    current = prepare_notice(
        notice_xml,
        expected_publication_number="722762-2026",
    ).notice

    predecessor = replace(
        current,
        publication_number="706539-2026",
        notice_id="df078ce7-100b-4415-aad6-2db2b053ef77",
        notice_version="02",
    )
    return current, predecessor


def test_accepts_predecessor_by_publication_number(notice_pair):
    current, predecessor = notice_pair

    validate_predecessor(current, predecessor)


def test_rejects_wrong_predecessor_publication(notice_pair):
    current, predecessor = notice_pair
    predecessor = replace(
        predecessor,
        publication_number="668566-2026",
    )

    with pytest.raises(ValueError, match="identity does not match"):
        validate_predecessor(current, predecessor)


def test_accepts_predecessor_by_notice_version(notice_pair):
    current, predecessor = notice_pair
    current = replace(
        current,
        reference_type="notice_version",
        changed_notice_identifier_raw=(
            f"{predecessor.notice_id}-{predecessor.notice_version}"
        ),
        previous_publication_number=None,
        previous_notice_id=predecessor.notice_id,
        previous_notice_version=predecessor.notice_version,
    )

    validate_predecessor(current, predecessor)


def test_rejects_wrong_predecessor_version(notice_pair):
    current, predecessor = notice_pair
    current = replace(
        current,
        reference_type="notice_version",
        changed_notice_identifier_raw=f"{predecessor.notice_id}-01",
        previous_publication_number=None,
        previous_notice_id=predecessor.notice_id,
        previous_notice_version="01",
    )

    with pytest.raises(ValueError, match="identity does not match"):
        validate_predecessor(current, predecessor)


def test_rejects_self_reference(notice_pair):
    current, _ = notice_pair
    current = replace(
        current,
        previous_publication_number=current.publication_number,
        changed_notice_identifier_raw=current.publication_number,
    )

    with pytest.raises(ValueError, match="its own predecessor"):
        validate_predecessor(current, current)


def test_rejects_different_procedure(notice_pair):
    current, predecessor = notice_pair
    predecessor = replace(
        predecessor,
        procedure_id="54a4d718-b51e-4b24-9a69-b1d88a28a2d6",
    )

    with pytest.raises(ValueError, match="different procedure"):
        validate_predecessor(current, predecessor)


def test_accepts_missing_predecessor_procedure_id(notice_pair):
    current, predecessor = notice_pair
    predecessor = replace(predecessor, procedure_id=None)

    validate_predecessor(current, predecessor)


def test_rejects_missing_reference(notice_pair):
    current, predecessor = notice_pair
    current = replace(
        current,
        reference_type="missing",
        changed_notice_identifier_raw=None,
        previous_publication_number=None,
    )

    with pytest.raises(ValueError, match="no supported predecessor reference"):
        validate_predecessor(current, predecessor)


@pytest.mark.parametrize(
    "reference_type",
    ["publication_number", "notice_version"],
)
def test_downloads_and_validates_predecessor(notice_xml, reference_type):
    predecessor = prepare_notice(
        notice_xml,
        expected_publication_number="722762-2026",
    ).notice

    current = replace(
        predecessor,
        publication_number="749999-2026",
        notice_id="df078ce7-100b-4415-aad6-2db2b053ef77",
        reference_type=reference_type,
        changed_notice_identifier_raw=(
            predecessor.publication_number
            if reference_type == "publication_number"
            else f"{predecessor.notice_id}-{predecessor.notice_version}"
        ),
        previous_publication_number=(
            predecessor.publication_number
            if reference_type == "publication_number"
            else None
        ),
        previous_notice_id=(
            predecessor.notice_id if reference_type == "notice_version" else None
        ),
        previous_notice_version=(
            predecessor.notice_version if reference_type == "notice_version" else None
        ),
    )
    metadata = {"publication-number": "722762-2026"}

    with (
        patch(
            "tender_intelligence.predecessors.fetch_all_notices",
            return_value=[metadata],
        ),
        patch(
            "tender_intelligence.predecessors.fetch_notice_xml",
            return_value=notice_xml,
        ) as download,
    ):
        result = download_predecessor(current)

    assert result is not None
    assert result.search_metadata == metadata
    assert result.xml_content == notice_xml
    assert result.bundle.notice == predecessor
    download.assert_called_once_with("722762-2026")


def test_does_not_download_when_search_finds_no_predecessor(notice_pair):
    current, _ = notice_pair

    with (
        patch(
            "tender_intelligence.predecessors.fetch_all_notices",
            return_value=[],
        ),
        patch(
            "tender_intelligence.predecessors.fetch_notice_xml",
        ) as download,
    ):
        assert download_predecessor(current) is None

    download.assert_not_called()


def test_rejects_downloaded_xml_with_wrong_publication(
    notice_pair,
    notice_xml,
):
    current, _ = notice_pair

    with (
        patch(
            "tender_intelligence.predecessors.fetch_all_notices",
            return_value=[{"publication-number": "706539-2026"}],
        ),
        patch(
            "tender_intelligence.predecessors.fetch_notice_xml",
            return_value=notice_xml,
        ),
    ):
        # The search points to 706539, but the XML contains 722762.
        with pytest.raises(ValueError):
            download_predecessor(current)
