"""Normalize source values used to identify and compare notices."""

import re
from uuid import UUID


PUBLICATION_NUMBER_PATTERN = re.compile(r"([0-9]{1,8})-([0-9]{4})")

NOTICE_VERSION_REFERENCE_PATTERN = re.compile(
    r"(?P<notice_id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    r"-(?P<notice_version>[0-9]{2})"
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