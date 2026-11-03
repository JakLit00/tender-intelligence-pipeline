"""Test publication number normalization."""

import pytest

from tender_intelligence.normalization import (
    classify_changed_notice_reference,
    normalize_notice_id,
    normalize_notice_metadata,
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
        "notice_id": None,
        "notice_version": None,
    }


@pytest.mark.parametrize("value", [None, "", "   "])
def test_classifies_missing_reference(value):
    assert classify_changed_notice_reference(value) == {
        "reference_raw": value,
        "reference_type": "missing",
        "publication_number": None,
        "notice_id": None,
        "notice_version": None,
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
        "notice_id": None,
        "notice_version": None,
    }

@pytest.mark.parametrize("version", ["01", "02", "12"])
def test_classifies_notice_uuid_with_version(version):
    notice_id = "755db7f6-6aa1-453b-9087-1df5f7725112"
    raw_value = f"{notice_id}-{version}"

    assert classify_changed_notice_reference(raw_value) == {
        "reference_raw": raw_value,
        "reference_type": "notice_version",
        "publication_number": None,
        "notice_id": notice_id,
        "notice_version": version,
    }


def test_normalizes_uuid_case_without_changing_raw_reference():
    raw_value = " 755DB7F6-6AA1-453B-9087-1DF5F7725112-02 "

    result = classify_changed_notice_reference(raw_value)

    assert result["reference_raw"] == raw_value
    assert result["reference_type"] == "notice_version"
    assert result["notice_id"] == "755db7f6-6aa1-453b-9087-1df5f7725112"
    assert result["notice_version"] == "02"


@pytest.mark.parametrize(
    "raw_value",
    [
        "755db7f6-6aa1-453b-9087-1df5f7725112",
        "755db7f6-6aa1-453b-9087-1df5f7725112-2",
        "755db7f6-6aa1-453b-9087-1df5f7725112-002",
        "755db7f6-6aa1-453b-9087-1df5f7725112-02-extra",
        "755db7f6-6aa1-153b-9087-1df5f7725112-02",
    ],
)
def test_keeps_unsupported_uuid_references_unresolved(raw_value):
    assert classify_changed_notice_reference(raw_value) == {
        "reference_raw": raw_value,
        "reference_type": "unresolved",
        "publication_number": None,
        "notice_id": None,
        "notice_version": None,
    }

def test_metadata_and_reference_use_the_same_normalized_uuid():
    original_id = "755DB7F6-6AA1-453B-9087-1DF5F7725112"
    metadata = {
        "notice_id": original_id,
        "notice_version": "02",
    }

    normalized = normalize_notice_metadata(metadata)
    reference = classify_changed_notice_reference(f"{original_id}-02")

    assert normalized["notice_id"] == reference["notice_id"]
    assert normalized["notice_version"] == reference["notice_version"]
    assert normalized["notice_id"] == original_id.lower()

    # Normalization must not overwrite the source representation.
    assert metadata["notice_id"] == original_id


@pytest.mark.parametrize(
    "value",
    [
        "",
        "not-a-uuid",
        "755db7f6-6aa1-153b-9087-1df5f7725112",
    ],
)
def test_rejects_invalid_notice_ids(value):
    with pytest.raises(ValueError):
        normalize_notice_id(value)


def test_metadata_normalization_requires_notice_id():
    with pytest.raises(ValueError, match="Missing notice identifier"):
        normalize_notice_metadata({"notice_id": None})