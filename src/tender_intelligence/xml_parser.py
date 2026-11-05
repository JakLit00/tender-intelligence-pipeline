"""Extract metadata from TED eForms contract notices."""

import xml.etree.ElementTree as ET

# Namespace URIs identify XML elements; prefixes in source files may differ.
NAMESPACES = {
    "cac": ("urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"),
    "cbc": ("urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"),
    "ext": ("urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"),
    "efext": "http://data.europa.eu/p27/eforms-ubl-extensions/1",
    "efac": ("http://data.europa.eu/p27/eforms-ubl-extension-aggregate-components/1"),
    "efbc": ("http://data.europa.eu/p27/eforms-ubl-extension-basic-components/1"),
}

CONTRACT_NOTICE_TAG = (
    "{urn:oasis:names:specification:ubl:schema:xsd:ContractNotice-2}ContractNotice"
)

EXTENSION_PATH = (
    "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/efext:EformsExtension"
)


def read_text(element: ET.Element, path: str) -> str | None:
    """Read a single non-empty value, rejecting ambiguous matches."""
    matches = element.findall(path, NAMESPACES)

    # Reject ambiguous matches instead of silently taking the first value.
    if len(matches) > 1:
        raise ValueError(f"Expected at most one element at: {path}")

    if not matches or matches[0].text is None:
        return None

    return matches[0].text.strip() or None


def parse_notice_metadata(xml_bytes: bytes) -> dict[str, str | None]:
    """Extract raw metadata from an eForms contract notice."""
    try:
        root = ET.fromstring(xml_bytes)
    except LookupError as exc:
        raise ValueError("Unsupported XML encoding") from exc

    if root.tag != CONTRACT_NOTICE_TAG:
        raise ValueError(f"Unsupported XML root: {root.tag}")

    notice_id = read_text(root, "cbc:ID")

    if notice_id is None:
        raise ValueError("Missing notice identifier")

    # Preserve source formatting here; normalize identifiers and dates separately.
    fields = {
        "notice_version": "cbc:VersionID",
        "procedure_id": "cbc:ContractFolderID",
        "notice_type": "cbc:NoticeTypeCode",
        "publication_number_raw": (
            f"{EXTENSION_PATH}/efac:Publication/efbc:NoticePublicationID"
        ),
        "publication_date_raw": (
            f"{EXTENSION_PATH}/efac:Publication/efbc:PublicationDate"
        ),
        "changed_notice_identifier_raw": (
            f"{EXTENSION_PATH}/efac:Changes/efbc:ChangedNoticeIdentifier"
        ),
        "change_reason_code": (
            f"{EXTENSION_PATH}/efac:Changes/efac:ChangeReason/cbc:ReasonCode"
        ),
    }

    result = {"notice_id": notice_id}

    for field_name, path in fields.items():
        result[field_name] = read_text(root, path)

    return result


def parse_notice_lots(xml_bytes: bytes) -> list[dict[str, str | None]]:
    """Extract lot identifiers and raw submission deadlines."""
    try:
        root = ET.fromstring(xml_bytes)
    except LookupError as exc:
        raise ValueError("Unsupported XML encoding") from exc

    if root.tag != CONTRACT_NOTICE_TAG:
        raise ValueError(f"Unsupported XML root: {root.tag}")

    lots = []
    seen_lot_ids = set()

    # Other EndDate elements may describe contract duration, not submission.
    deadline_path = "cac:TenderingProcess/cac:TenderSubmissionDeadlinePeriod"

    for lot in root.findall("cac:ProcurementProjectLot", NAMESPACES):
        lot_id = read_text(lot, "cbc:ID")

        if lot_id is None:
            raise ValueError("Missing lot identifier")

        # Lot identifiers are unique within a notice, not across all notices.
        if lot_id in seen_lot_ids:
            raise ValueError(f"Duplicate lot identifier: {lot_id}")

        seen_lot_ids.add(lot_id)
        deadlines = lot.findall(deadline_path, NAMESPACES)

        # Never combine a date and time from separate deadline blocks.
        if len(deadlines) > 1:
            raise ValueError(f"Multiple submission deadline periods for lot: {lot_id}")

        deadline_date = None
        deadline_time = None

        if deadlines:
            deadline_date = read_text(deadlines[0], "cbc:EndDate")
            deadline_time = read_text(deadlines[0], "cbc:EndTime")

        lots.append(
            {
                "lot_id": lot_id,
                "submission_deadline_date_raw": deadline_date,
                "submission_deadline_time_raw": deadline_time,
            }
        )

    return lots
