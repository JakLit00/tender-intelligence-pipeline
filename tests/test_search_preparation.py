from copy import deepcopy
from datetime import date

import pytest

from tender_intelligence.search_preparation import prepare_search_batch


def test_prepares_normalized_fields_and_preserves_metadata() -> None:
    source = {
        "publication-number": "00722762-2026",
        "publication-date": "2026-10-20+02:00",
        "buyer-name": {"pol": ["Example buyer"]},
        "classification-cpv": ["72250000", "72250000"],
    }
    original = deepcopy(source)

    batch = prepare_search_batch([source])

    assert list(batch.columns) == [
        "publication_number",
        "publication_date",
        "search_metadata",
    ]
    assert len(batch) == 1

    row = batch.iloc[0]
    assert row["publication_number"] == "722762-2026"
    assert row["publication_date"] == date(2026, 10, 20)
    assert row["search_metadata"] == original
    assert source == original

    source["buyer-name"]["pol"].append("Another buyer")
    assert row["search_metadata"]["buyer-name"]["pol"] == [
        "Example buyer"
    ]


def test_empty_batch_has_expected_columns() -> None:
    batch = prepare_search_batch([])

    assert batch.empty
    assert list(batch.columns) == [
        "publication_number",
        "publication_date",
        "search_metadata",
    ]


def test_preserves_distinct_publications() -> None:
    batch = prepare_search_batch(
        [
            {
                "publication-number": "722762-2026",
                "publication-date": "2026-10-20+02:00",
            },
            {
                "publication-number": "706539-2026",
                "publication-date": "2026-10-12+02:00",
            },
        ]
    )

    assert batch["publication_number"].tolist() == [
        "722762-2026",
        "706539-2026",
    ]
    assert batch["publication_date"].tolist() == [
        date(2026, 10, 20),
        date(2026, 10, 12),
    ]


@pytest.mark.parametrize(
    "second_number",
    ["722762-2026", "00722762-2026"],
)
def test_rejects_duplicate_normalized_publications(
    second_number: str,
) -> None:
    notices = [
        {
            "publication-number": "722762-2026",
            "publication-date": "2026-10-20+02:00",
        },
        {
            "publication-number": second_number,
            "publication-date": "2026-10-20+02:00",
        },
    ]

    with pytest.raises(
        ValueError,
        match="Duplicate publications after normalization: 722762-2026",
    ):
        prepare_search_batch(notices)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("publication-number", None),
        ("publication-number", " "),
        ("publication-number", 722762),
        ("publication-date", None),
        ("publication-date", ""),
        ("publication-date", ["2026-10-20"]),
    ],
)
def test_rejects_missing_or_invalid_field_types(
    field: str,
    value: object,
) -> None:
    notice = {
        "publication-number": "722762-2026",
        "publication-date": "2026-10-20+02:00",
    }
    notice[field] = value

    with pytest.raises(ValueError, match=field):
        prepare_search_batch([notice])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("publication-number", "invalid", "Invalid publication number"),
        ("publication-date", "2026-02-30", "Invalid XML date"),
    ],
)
def test_rejects_invalid_field_values(
    field: str,
    value: str,
    message: str,
) -> None:
    notice = {
        "publication-number": "722762-2026",
        "publication-date": "2026-10-20+02:00",
    }
    notice[field] = value

    with pytest.raises(ValueError, match=message):
        prepare_search_batch([notice])


def test_rejects_non_dictionary_notice() -> None:
    with pytest.raises(ValueError, match="must be a dictionary"):
        prepare_search_batch(["invalid"])