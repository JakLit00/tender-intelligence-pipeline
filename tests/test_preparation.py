from datetime import date, datetime, timezone

import pytest

from tender_intelligence.preparation import prepare_notice


def test_prepares_notice_and_lot_from_xml(notice_xml: bytes) -> None:
    bundle = prepare_notice(
        notice_xml,
        expected_publication_number="722762-2026",
    )

    notice = bundle.notice
    assert notice.publication_number == "722762-2026"
    assert notice.notice_id == "8ac273c6-7603-4ad1-b9a2-8ed027ed773f"
    assert notice.notice_version == "01"
    assert notice.procedure_id == "4835bb55-6b3a-4579-81d8-b34df3e663ce"
    assert notice.notice_type == "cn-standard"
    assert notice.publication_date == date(2026, 10, 20)
    assert notice.reference_type == "publication_number"
    assert notice.previous_publication_number == "706539-2026"
    assert notice.previous_notice_id is None
    assert notice.previous_notice_version is None
    assert notice.change_reason_code == "cor-buy"

    assert len(bundle.lots) == 1
    lot = bundle.lots[0]
    assert lot.publication_number == notice.publication_number
    assert lot.lot_id == "LOT-0001"
    assert lot.submission_deadline_date_raw == "2026-11-03+01:00"
    assert lot.submission_deadline_time_raw == "09:00:00+01:00"
    assert lot.submission_deadline_local_date == date(2026, 11, 3)
    assert lot.submission_deadline_at == datetime(
        2026, 11, 3, 8, 0, tzinfo=timezone.utc
    )


def test_rejects_unexpected_publication(notice_xml: bytes) -> None:
    with pytest.raises(ValueError, match="Publication number mismatch"):
        prepare_notice(
            notice_xml,
            expected_publication_number="706539-2026",
        )


@pytest.mark.parametrize(
    ("element", "value", "field_name"),
    [
        ("efbc:NoticePublicationID", "00722762-2026", "publication_number"),
        ("efbc:PublicationDate", "2026-10-20+02:00", "publication_date"),
        ("cbc:VersionID", "01", "notice_version"),
        ("cbc:NoticeTypeCode", "cn-standard", "notice_type"),
    ],
)
def test_rejects_missing_required_metadata(
    notice_xml: bytes,
    element: str,
    value: str,
    field_name: str,
) -> None:
    xml_content = notice_xml.replace(
        f"<{element}>{value}</{element}>".encode(),
        b"",
    )

    with pytest.raises(ValueError, match=f"Missing required field: {field_name}"):
        prepare_notice(
            xml_content,
            expected_publication_number="722762-2026",
        )


def test_rejects_invalid_notice_version(notice_xml: bytes) -> None:
    xml_content = notice_xml.replace(
        b"<cbc:VersionID>01</cbc:VersionID>",
        b"<cbc:VersionID>1</cbc:VersionID>",
    )

    with pytest.raises(ValueError, match="Invalid notice version"):
        prepare_notice(
            xml_content,
            expected_publication_number="722762-2026",
        )


def test_rejects_invalid_procedure_id(notice_xml: bytes) -> None:
    xml_content = notice_xml.replace(
        b"4835bb55-6b3a-4579-81d8-b34df3e663ce",
        b"invalid-procedure-id",
    )

    with pytest.raises(ValueError, match="Invalid procedure ID"):
        prepare_notice(
            xml_content,
            expected_publication_number="722762-2026",
        )


def test_prepares_notice_version_reference(notice_xml: bytes) -> None:
    xml_content = notice_xml.replace(
        b"706539-2026",
        b"df078ce7-100b-4415-aad6-2db2b053ef77-01",
    )

    notice = prepare_notice(
        xml_content,
        expected_publication_number="722762-2026",
    ).notice

    assert notice.reference_type == "notice_version"
    assert notice.previous_publication_number is None
    assert notice.previous_notice_id == "df078ce7-100b-4415-aad6-2db2b053ef77"
    assert notice.previous_notice_version == "01"


def test_preserves_unresolved_reference(notice_xml: bytes) -> None:
    xml_content = notice_xml.replace(
        b"706539-2026",
        b"unknown-reference",
    )

    notice = prepare_notice(
        xml_content,
        expected_publication_number="722762-2026",
    ).notice

    assert notice.reference_type == "unresolved"
    assert notice.changed_notice_identifier_raw == "unknown-reference"
    assert notice.previous_publication_number is None
    assert notice.previous_notice_id is None
    assert notice.previous_notice_version is None


def test_preserves_conflicting_deadline_as_quality_issue(
    notice_xml: bytes,
) -> None:
    xml_content = notice_xml.replace(
        b"2026-11-03+01:00",
        b"2026-11-03Z",
    )

    bundle = prepare_notice(
        xml_content,
        expected_publication_number="722762-2026",
    )

    assert bundle.notice.publication_number == "722762-2026"
    assert len(bundle.lots) == 1

    lot = bundle.lots[0]
    assert lot.submission_deadline_date_raw == "2026-11-03Z"
    assert lot.submission_deadline_time_raw == "09:00:00+01:00"
    assert lot.submission_deadline_local_date == date(2026, 11, 3)
    assert lot.submission_deadline_at is None
    assert (
        lot.submission_deadline_quality_issue
        == "conflicting_timezone_offsets"
    )