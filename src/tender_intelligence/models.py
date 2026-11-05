from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

ReferenceType = Literal[
    "missing",
    "publication_number",
    "notice_version",
    "unresolved",
]


@dataclass(frozen=True)
class PreparedNotice:
    publication_number: str
    notice_id: str
    notice_version: str
    procedure_id: str | None
    notice_type: str
    publication_date: date
    changed_notice_identifier_raw: str | None
    reference_type: ReferenceType
    previous_publication_number: str | None
    previous_notice_id: str | None
    previous_notice_version: str | None
    change_reason_code: str | None


@dataclass(frozen=True)
class PreparedLot:
    publication_number: str
    lot_id: str
    submission_deadline_date_raw: str | None
    submission_deadline_time_raw: str | None
    submission_deadline_local_date: date | None
    submission_deadline_at: datetime | None
    submission_deadline_quality_issue: (
        Literal["conflicting_timezone_offsets"] | None
    ) = None


@dataclass(frozen=True)
class PreparedNoticeBundle:
    notice: PreparedNotice
    lots: tuple[PreparedLot, ...]
