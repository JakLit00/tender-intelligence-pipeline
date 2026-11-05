import re
from typing import cast
from uuid import UUID

from tender_intelligence.models import (
    PreparedLot,
    PreparedNotice,
    PreparedNoticeBundle,
    ReferenceType,
)
from tender_intelligence.normalization import (
    DeadlineTimezoneConflict,
    classify_changed_notice_reference,
    normalize_notice_id,
    normalize_publication_number,
    normalize_submission_deadline,
    normalize_xml_date,
)
from tender_intelligence.xml_parser import (
    parse_notice_lots,
    parse_notice_metadata,
)


def _required_text(value: str | None, field_name: str) -> str:
    if value is None or not value.strip():
        raise ValueError(f"Missing required field: {field_name}")

    return value.strip()


def prepare_notice(
    xml_content: bytes,
    *,
    expected_publication_number: str,
) -> PreparedNoticeBundle:
    """Parse and validate one notice before any database writes."""
    metadata = parse_notice_metadata(xml_content)

    publication_number = normalize_publication_number(
        _required_text(
            metadata["publication_number_raw"],
            "publication_number",
        )
    )
    expected_number = normalize_publication_number(expected_publication_number)

    if publication_number != expected_number:
        raise ValueError(
            "Publication number mismatch: "
            f"expected {expected_number}, got {publication_number}"
        )

    notice_id = normalize_notice_id(_required_text(metadata["notice_id"], "notice_id"))
    notice_version = _required_text(metadata["notice_version"], "notice_version")

    if re.fullmatch(r"[0-9]{2}", notice_version) is None:
        raise ValueError(f"Invalid notice version: {notice_version!r}")

    procedure_id_raw = metadata["procedure_id"]
    procedure_id = None

    if procedure_id_raw is not None and procedure_id_raw.strip():
        try:
            procedure_id = str(UUID(procedure_id_raw.strip()))
        except ValueError as exc:
            raise ValueError(f"Invalid procedure ID: {procedure_id_raw!r}") from exc

    notice_type = _required_text(metadata["notice_type"], "notice_type")
    publication_date = normalize_xml_date(
        _required_text(
            metadata["publication_date_raw"],
            "publication_date",
        )
    )

    reference = classify_changed_notice_reference(
        metadata["changed_notice_identifier_raw"]
    )
    reference_type = reference["reference_type"]

    if reference_type not in (
        "missing",
        "publication_number",
        "notice_version",
        "unresolved",
    ):
        raise ValueError(f"Unexpected reference type: {reference_type!r}")

    notice = PreparedNotice(
        publication_number=publication_number,
        notice_id=notice_id,
        notice_version=notice_version,
        procedure_id=procedure_id,
        notice_type=notice_type,
        publication_date=publication_date,
        changed_notice_identifier_raw=reference["reference_raw"],
        reference_type=cast(ReferenceType, reference_type),
        previous_publication_number=reference["publication_number"],
        previous_notice_id=reference["notice_id"],
        previous_notice_version=reference["notice_version"],
        change_reason_code=metadata["change_reason_code"],
    )

    lots = []

    for raw_lot in parse_notice_lots(xml_content):
        quality_issue = None

        try:
            local_date, deadline_at = normalize_submission_deadline(
                raw_lot["submission_deadline_date_raw"],
                raw_lot["submission_deadline_time_raw"],
            )
        except DeadlineTimezoneConflict:
            # Preserve the source day without inferring an uncertain UTC instant.
            local_date = normalize_xml_date(
                _required_text(
                    raw_lot["submission_deadline_date_raw"],
                    "submission_deadline_date_raw",
                )
            )
            deadline_at = None
            quality_issue = "conflicting_timezone_offsets"

        lots.append(
            PreparedLot(
                publication_number=publication_number,
                lot_id=_required_text(raw_lot["lot_id"], "lot_id"),
                submission_deadline_date_raw=(raw_lot["submission_deadline_date_raw"]),
                submission_deadline_time_raw=(raw_lot["submission_deadline_time_raw"]),
                submission_deadline_local_date=local_date,
                submission_deadline_at=deadline_at,
                submission_deadline_quality_issue=quality_issue,
            )
        )

    return PreparedNoticeBundle(
        notice=notice,
        lots=tuple(lots),
    )
