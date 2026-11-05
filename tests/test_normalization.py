"""Test publication number normalization."""

from datetime import date, datetime, timezone

import pytest

from tender_intelligence.normalization import (
    classify_changed_notice_reference,
    normalize_notice_id,
    normalize_notice_metadata,
    normalize_publication_number,
    normalize_submission_deadline,
    normalize_xml_date,
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


@pytest.mark.parametrize(
    "value",
    [
        "2026-10-20",
        "2026-10-20Z",
        "2026-10-20+02:00",
        "2026-10-20-05:00",
        " 2026-10-20+14:00 ",
    ],
)
def test_xml_date_preserves_source_calendar_day(value):
    assert normalize_xml_date(value) == date(2026, 10, 20)


def test_xml_date_accepts_leap_day():
    assert normalize_xml_date("2024-02-29Z") == date(2024, 2, 29)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "2026-02-29",
        "2026-02-30",
        "2026-13-01",
        "20-10-2026",
        "2026-10-20+14:01",
        "2026-10-20+01:60",
        "2026-10-20T09:00:00+02:00",
    ],
)
def test_xml_date_rejects_invalid_or_unsupported_values(value):
    with pytest.raises(ValueError, match="Invalid XML date"):
        normalize_xml_date(value)


@pytest.mark.parametrize(
    ("date_raw", "time_raw"),
    [
        ("2026-11-03+01:00", "09:00:00+01:00"),
        ("2026-11-03", "09:00:00+01:00"),
        ("2026-11-03+01:00", "09:00:00"),
        ("2026-11-03Z", "08:00:00Z"),
    ],
)
def test_deadline_resolves_to_the_correct_instant(date_raw, time_raw):
    local_date, deadline = normalize_submission_deadline(date_raw, time_raw)

    assert local_date == date(2026, 11, 3)
    assert deadline is not None
    assert deadline.astimezone(timezone.utc) == datetime(
        2026, 11, 3, 8, 0, tzinfo=timezone.utc
    )


@pytest.mark.parametrize(
    ("date_raw", "time_raw", "expected_date"),
    [
        ("2026-11-03+01:00", None, date(2026, 11, 3)),
        ("2026-11-03", "09:00:00", date(2026, 11, 3)),
        (None, "09:00:00+01:00", None),
        (None, None, None),
    ],
)
def test_incomplete_deadline_does_not_invent_an_instant(
    date_raw, time_raw, expected_date
):
    assert normalize_submission_deadline(date_raw, time_raw) == (
        expected_date,
        None,
    )


def test_deadline_rejects_conflicting_offsets():
    with pytest.raises(ValueError, match="Conflicting deadline timezone offsets"):
        normalize_submission_deadline(
            "2026-11-03+01:00",
            "09:00:00+02:00",
        )


@pytest.mark.parametrize("time_raw", ["25:00:00", "09:60:00", "09:00:00+14:01"])
def test_deadline_rejects_invalid_time(time_raw):
    with pytest.raises(ValueError, match="Invalid XML time"):
        normalize_submission_deadline("2026-11-03", time_raw)


def test_deadline_handles_offset_change_between_publications():
    _, previous = normalize_submission_deadline("2026-10-22+02:00", "09:00:00+02:00")
    _, current = normalize_submission_deadline("2026-11-03+01:00", "09:00:00+01:00")

    assert previous is not None
    assert current is not None
    assert previous.astimezone(timezone.utc).hour == 7
    assert current.astimezone(timezone.utc).hour == 8
    assert (current.date() - previous.date()).days == 12
