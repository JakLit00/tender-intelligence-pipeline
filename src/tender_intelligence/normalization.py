"""Normalize source values used to identify and compare notices."""

import re
from datetime import date, datetime, time
from uuid import UUID


PUBLICATION_NUMBER_PATTERN = re.compile(r"([0-9]{1,8})-([0-9]{4})")

NOTICE_VERSION_REFERENCE_PATTERN = re.compile(
    r"(?P<notice_id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    r"-(?P<notice_version>[0-9]{2})"
)

XML_DATE_PATTERN = re.compile(
    r"(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})"
    r"(?P<offset>Z|[+-](?:(?:0[0-9]|1[0-3]):[0-5][0-9]|14:00))?"
)

XML_TIME_PATTERN = re.compile(
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?"
    r"(?:Z|[+-](?:(?:0[0-9]|1[0-3]):[0-5][0-9]|14:00))?"
)

def normalize_publication_number(value: str) -> str:
    """Normalize a TED publication number to an unpadded number-year."""
    match = PUBLICATION_NUMBER_PATTERN.fullmatch(value.strip())

    if match is None:
        raise ValueError(f"Invalid publication number: {value!r}")

    number_text, year = match.groups()
    number = int(number_text)

    if number == 0:
        raise ValueError(f"Invalid publication number: {value!r}")

    # Remove padding only from the numeric part, preserving the year.
    return f"{number}-{year}"

def normalize_notice_id(value: str) -> str:
    """Validate a canonical UUID v4 shape and normalize its letter case."""
    text = value.strip()

    # UUID() also accepts compact and braced forms; keep our input contract strict.
    if re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        text,
    ) is None:
        raise ValueError(f"Invalid notice identifier: {value!r}")

    notice_id = UUID(text)

    if notice_id.version != 4:
        raise ValueError(f"Expected UUID v4 notice identifier: {value!r}")

    return str(notice_id)


def normalize_notice_metadata(
    metadata: dict[str, str | None],
) -> dict[str, str | None]:
    """Return metadata with a normalized notice ID, leaving input unchanged."""
    notice_id = metadata.get("notice_id")

    if notice_id is None:
        raise ValueError("Missing notice identifier")

    normalized = metadata.copy()
    normalized["notice_id"] = normalize_notice_id(notice_id)
    return normalized

def classify_changed_notice_reference(
    value: str | None,
) -> dict[str, str | None]:
    """Classify a predecessor reference while preserving its source value."""
    result: dict[str, str | None] = {
        "reference_raw": value,
        "reference_type": "missing",
        "publication_number": None,
        "notice_id": None,
        "notice_version": None,
    }

    if value is None or not value.strip():
        return result

    text = value.strip()

    try:
        publication_number = normalize_publication_number(text)
    except ValueError:
        publication_number = None

    if publication_number is not None:
        result["reference_type"] = "publication_number"
        result["publication_number"] = publication_number
        return result

    match = NOTICE_VERSION_REFERENCE_PATTERN.fullmatch(text)

    if match is not None:
        try:
            notice_id = normalize_notice_id(match.group("notice_id"))
        except ValueError:
            notice_id = None

        if notice_id is not None:
            result["reference_type"] = "notice_version"
            result["notice_id"] = notice_id

            # The version belongs to the referenced notice, not the current one.
            result["notice_version"] = match.group("notice_version")
            return result

    # Unknown formats remain available for later resolution and auditing.
    result["reference_type"] = "unresolved"
    return result

def normalize_xml_date(value: str) -> date:
    """Extract a calendar date from the supported XML date format."""
    match = XML_DATE_PATTERN.fullmatch(value.strip())

    if match is None:
        raise ValueError(f"Invalid XML date: {value!r}")

    try:
        # Preserve the source calendar day; a date alone is not a UTC instant.
        return date.fromisoformat(match.group("date"))
    except ValueError as exc:
        raise ValueError(f"Invalid XML date: {value!r}") from exc

def normalize_submission_deadline(
    date_raw: str | None,
    time_raw: str | None,
) -> tuple[date | None, datetime | None]:
    """Return the source calendar date and an aware deadline when possible."""
    date_text = date_raw.strip() if date_raw is not None else ""
    time_text = time_raw.strip() if time_raw is not None else ""

    local_date = None
    date_timezone = None
    parsed_time = None

    if date_text:
        local_date = normalize_xml_date(date_text)
        date_match = XML_DATE_PATTERN.fullmatch(date_text)

        # normalize_xml_date has already validated the complete date string.
        assert date_match is not None
        offset = date_match.group("offset")

        if offset is not None:
            date_timezone = time.fromisoformat(
                f"00:00:00{offset}"
            ).tzinfo

    if time_text:
        if XML_TIME_PATTERN.fullmatch(time_text) is None:
            raise ValueError(f"Invalid XML time: {time_raw!r}")

        try:
            parsed_time = time.fromisoformat(time_text)
        except ValueError as exc:
            raise ValueError(f"Invalid XML time: {time_raw!r}") from exc

    if local_date is None or parsed_time is None:
        return local_date, None

    time_timezone = parsed_time.tzinfo

    if (
        date_timezone is not None
        and time_timezone is not None
        and date_timezone != time_timezone
    ):
        raise ValueError("Conflicting deadline timezone offsets")

    deadline_timezone = time_timezone or date_timezone

    # Never infer a timezone from the machine running the pipeline.
    if deadline_timezone is None:
        return local_date, None

    deadline = datetime.combine(
        local_date,
        parsed_time,
        tzinfo=deadline_timezone,
    )
    return local_date, deadline