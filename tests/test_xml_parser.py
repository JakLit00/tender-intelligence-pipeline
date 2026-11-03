"""Test lot extraction independently of the TED API."""

import pytest

from tender_intelligence.xml_parser import (
    parse_notice_lots,
    parse_notice_metadata,
)


def make_notice(lots_xml: str) -> bytes:
    """Wrap test lots in a minimal contract notice."""
    return f"""
    <ContractNotice
        xmlns="urn:oasis:names:specification:ubl:schema:xsd:ContractNotice-2"
        xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
        xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
    >
        {lots_xml}
    </ContractNotice>
    """.encode("utf-8")


def test_deadlines_remain_associated_with_their_lots():
    xml = make_notice("""
        <cac:ProcurementProjectLot>
            <cbc:ID>LOT-0001</cbc:ID>
            <cac:TenderingProcess>
                <cac:TenderSubmissionDeadlinePeriod>
                    <cbc:EndDate>2026-11-03+01:00</cbc:EndDate>
                    <cbc:EndTime>09:00:00+01:00</cbc:EndTime>
                </cac:TenderSubmissionDeadlinePeriod>
            </cac:TenderingProcess>
        </cac:ProcurementProjectLot>
        <cac:ProcurementProjectLot>
            <cbc:ID>LOT-0002</cbc:ID>
            <cac:TenderingProcess>
                <cac:TenderSubmissionDeadlinePeriod>
                    <cbc:EndDate>2026-11-10+01:00</cbc:EndDate>
                </cac:TenderSubmissionDeadlinePeriod>
            </cac:TenderingProcess>
        </cac:ProcurementProjectLot>
    """)

    assert parse_notice_lots(xml) == [
        {
            "lot_id": "LOT-0001",
            "submission_deadline_date_raw": "2026-11-03+01:00",
            "submission_deadline_time_raw": "09:00:00+01:00",
        },
        {
            "lot_id": "LOT-0002",
            "submission_deadline_date_raw": "2026-11-10+01:00",
            "submission_deadline_time_raw": None,
        },
    ]


def test_unrelated_end_date_is_not_a_submission_deadline():
    xml = make_notice("""
        <cac:ProcurementProjectLot>
            <cbc:ID>LOT-0001</cbc:ID>
            <cac:ProcurementProject>
                <cac:PlannedPeriod>
                    <cbc:EndDate>2027-12-31+01:00</cbc:EndDate>
                </cac:PlannedPeriod>
            </cac:ProcurementProject>
        </cac:ProcurementProjectLot>
    """)

    assert parse_notice_lots(xml) == [
        {
            "lot_id": "LOT-0001",
            "submission_deadline_date_raw": None,
            "submission_deadline_time_raw": None,
        }
    ]


def test_missing_lot_identifier_is_rejected():
    xml = make_notice("""
        <cac:ProcurementProjectLot />
    """)

    with pytest.raises(ValueError, match="Missing lot identifier"):
        parse_notice_lots(xml)


def test_duplicate_lot_identifier_is_rejected():
    xml = make_notice("""
        <cac:ProcurementProjectLot>
            <cbc:ID>LOT-0001</cbc:ID>
        </cac:ProcurementProjectLot>
        <cac:ProcurementProjectLot>
            <cbc:ID>LOT-0001</cbc:ID>
        </cac:ProcurementProjectLot>
    """)

    with pytest.raises(ValueError, match="Duplicate lot identifier"):
        parse_notice_lots(xml)

def test_metadata_uses_publication_date_and_preserves_raw_values():
    xml = make_notice("""
        <cbc:ID schemeName="notice-id">notice-123</cbc:ID>
        <cbc:ContractFolderID>procedure-456</cbc:ContractFolderID>
        <cbc:VersionID>01</cbc:VersionID>
        <cbc:NoticeTypeCode>cn-standard</cbc:NoticeTypeCode>
        <cbc:IssueDate>2026-10-19Z</cbc:IssueDate>
        <ext:UBLExtensions
            xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
            xmlns:efext="http://data.europa.eu/p27/eforms-ubl-extensions/1"
            xmlns:efac="http://data.europa.eu/p27/eforms-ubl-extension-aggregate-components/1"
            xmlns:efbc="http://data.europa.eu/p27/eforms-ubl-extension-basic-components/1"
        >
            <ext:UBLExtension>
                <ext:ExtensionContent>
                    <efext:EformsExtension>
                        <efac:Publication>
                            <efbc:NoticePublicationID>00722762-2026</efbc:NoticePublicationID>
                            <efbc:PublicationDate>2026-10-20+02:00</efbc:PublicationDate>
                        </efac:Publication>
                        <efac:Changes>
                            <efbc:ChangedNoticeIdentifier>706539-2026</efbc:ChangedNoticeIdentifier>
                            <efac:ChangeReason>
                                <cbc:ReasonCode>cor-buy</cbc:ReasonCode>
                            </efac:ChangeReason>
                        </efac:Changes>
                    </efext:EformsExtension>
                </ext:ExtensionContent>
            </ext:UBLExtension>
        </ext:UBLExtensions>
    """)

    result = parse_notice_metadata(xml)

    assert result == {
        "notice_id": "notice-123",
        "notice_version": "01",
        "procedure_id": "procedure-456",
        "notice_type": "cn-standard",
        "publication_number_raw": "00722762-2026",
        "publication_date_raw": "2026-10-20+02:00",
        "changed_notice_identifier_raw": "706539-2026",
        "change_reason_code": "cor-buy",
    }


def test_notice_without_changes_has_no_predecessor_or_reason():
    xml = make_notice("""
        <cbc:ID schemeName="notice-id">notice-123</cbc:ID>
        <cbc:NoticeTypeCode>cn-standard</cbc:NoticeTypeCode>
    """)

    result = parse_notice_metadata(xml)

    assert result["changed_notice_identifier_raw"] is None
    assert result["change_reason_code"] is None


def test_nested_identifier_does_not_replace_missing_notice_identifier():
    # A lot ID must not be mistaken for the notice-level ID.
    xml = make_notice("""
        <cac:ProcurementProjectLot>
            <cbc:ID>LOT-0001</cbc:ID>
        </cac:ProcurementProjectLot>
    """)

    with pytest.raises(ValueError, match="Missing notice identifier"):
        parse_notice_metadata(xml)