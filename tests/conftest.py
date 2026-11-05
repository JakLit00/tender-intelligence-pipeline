import pytest


@pytest.fixture
def notice_xml() -> bytes:
    return b"""\
<ContractNotice
    xmlns="urn:oasis:names:specification:ubl:schema:xsd:ContractNotice-2"
    xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
    xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
    xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
    xmlns:efext="http://data.europa.eu/p27/eforms-ubl-extensions/1"
    xmlns:efac="http://data.europa.eu/p27/eforms-ubl-extension-aggregate-components/1"
    xmlns:efbc="http://data.europa.eu/p27/eforms-ubl-extension-basic-components/1"
>
    <ext:UBLExtensions>
        <ext:UBLExtension>
            <ext:ExtensionContent>
                <efext:EformsExtension>
                    <efac:Changes>
                        <efbc:ChangedNoticeIdentifier>706539-2026</efbc:ChangedNoticeIdentifier>
                        <efac:ChangeReason>
                            <cbc:ReasonCode>cor-buy</cbc:ReasonCode>
                        </efac:ChangeReason>
                    </efac:Changes>
                    <efac:Publication>
                        <efbc:NoticePublicationID>00722762-2026</efbc:NoticePublicationID>
                        <efbc:PublicationDate>2026-10-20+02:00</efbc:PublicationDate>
                    </efac:Publication>
                </efext:EformsExtension>
            </ext:ExtensionContent>
        </ext:UBLExtension>
    </ext:UBLExtensions>
    <cbc:ID schemeName="notice-id">8ac273c6-7603-4ad1-b9a2-8ed027ed773f</cbc:ID>
    <cbc:ContractFolderID>4835bb55-6b3a-4579-81d8-b34df3e663ce</cbc:ContractFolderID>
    <cbc:VersionID>01</cbc:VersionID>
    <cbc:NoticeTypeCode>cn-standard</cbc:NoticeTypeCode>
    <cac:ProcurementProjectLot>
        <cbc:ID>LOT-0001</cbc:ID>
        <cac:TenderingProcess>
            <cac:TenderSubmissionDeadlinePeriod>
                <cbc:EndDate>2026-11-03+01:00</cbc:EndDate>
                <cbc:EndTime>09:00:00+01:00</cbc:EndTime>
            </cac:TenderSubmissionDeadlinePeriod>
        </cac:TenderingProcess>
    </cac:ProcurementProjectLot>
</ContractNotice>
"""
