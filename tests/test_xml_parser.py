"""Test lot extraction independently of the TED API."""

import pytest

from tender_intelligence.xml_parser import parse_notice_lots


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