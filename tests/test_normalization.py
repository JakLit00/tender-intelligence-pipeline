"""Test publication number normalization."""

import pytest

from tender_intelligence.normalization import (
    classify_changed_notice_reference,
    normalize_publication_number,
)


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("00722762-2026", "722762-2026"),
        ("722762-2026", "722762-2026"),
        (" 00722762-2026 \n", "722762-2026"),
        ("00000001-2026", "1-2026"),
    ],
)
def test_normalizes_publication_numbers(raw_value, expected):
    assert normalize_publication_number(raw_value) == expected


@pytest.mark.parametrize(
    "raw_value",
    [
        "",
        "00000000-2026",
        "722762",
        "722762-26",
        "722762-2026-extra",
        "8ac273c6-7603-4ad1-b9a2-8ed027ed773f",
    ],
)
def test_rejects_invalid_publication_numbers(raw_value):
    # UUID references require separate handling, not publication normalization.
    with pytest.raises(ValueError, match="Invalid publication number"):
        normalize_publication_number(raw_value)

def test_classifies_publication_reference_and_preserves_original():
    assert classify_changed_notice_reference("00706539-2026") == {
        "reference_raw": "00706539-2026",
        "reference_type": "publication_number",
        "publication_number": "706539-2026",
    }


@pytest.mark.parametrize("value", [None, "", "   "])
def test_classifies_missing_reference(value):
    assert classify_changed_notice_reference(value) == {
        "reference_raw": value,
        "reference_type": "missing",
        "publication_number": None,
    }


@pytest.mark.parametrize(
    "value",
    [
        "8ac273c6-7603-4ad1-b9a2-8ed027ed773f",
        "unexpected-reference",
    ],
)
def test_preserves_unresolved_reference(value):
    assert classify_changed_notice_reference(value) == {
        "reference_raw": value,
        "reference_type": "unresolved",
        "publication_number": None,
    }