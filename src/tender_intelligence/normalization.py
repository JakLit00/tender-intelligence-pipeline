"""Normalize source values used to identify and compare notices."""

import re


PUBLICATION_NUMBER_PATTERN = re.compile(r"([0-9]{1,8})-([0-9]{4})")


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

def classify_changed_notice_reference(
    value: str | None,
) -> dict[str, str | None]:
    """Classify a predecessor reference without discarding unknown formats."""
    if value is None or not value.strip():
        return {
            "reference_raw": value,
            "reference_type": "missing",
            "publication_number": None,
        }

    try:
        publication_number = normalize_publication_number(value)
    except ValueError:
        # Unknown formats remain available for later resolution and auditing.
        return {
            "reference_raw": value,
            "reference_type": "unresolved",
            "publication_number": None,
        }

    return {
        "reference_raw": value,
        "reference_type": "publication_number",
        "publication_number": publication_number,
    }