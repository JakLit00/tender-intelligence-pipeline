from copy import deepcopy
from typing import Any

import pandas as pd

from tender_intelligence.normalization import (
    normalize_publication_number,
    normalize_xml_date,
)

SEARCH_COLUMNS = (
    "publication_number",
    "publication_date",
    "search_metadata",
)


def prepare_search_batch(
    notices: list[dict[str, Any]],
) -> pd.DataFrame:
    """Prepare search results for registration, rejecting duplicate identities."""
    if not notices:
        return pd.DataFrame(columns=list(SEARCH_COLUMNS))

    for index, notice in enumerate(notices):
        if not isinstance(notice, dict):
            raise ValueError(f"Notice at index {index} must be a dictionary")

        for field in ("publication-number", "publication-date"):
            value = notice.get(field)

            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Missing or invalid {field} at index {index}")

    batch = pd.DataFrame(
        {
            "publication_number": [notice["publication-number"] for notice in notices],
            "publication_date": [notice["publication-date"] for notice in notices],
            # Keep nested source metadata independent of the input objects.
            "search_metadata": [deepcopy(notice) for notice in notices],
        }
    )

    batch["publication_number"] = batch["publication_number"].map(
        normalize_publication_number
    )

    # Publication dates represent source calendar days, not UTC instants.
    batch["publication_date"] = batch["publication_date"].map(normalize_xml_date)

    duplicate_mask = batch["publication_number"].duplicated(keep=False)

    if duplicate_mask.any():
        duplicate_numbers = (
            batch.loc[duplicate_mask, "publication_number"].drop_duplicates().tolist()
        )
        raise ValueError(
            "Duplicate publications after normalization: "
            + ", ".join(duplicate_numbers)
        )

    return batch
