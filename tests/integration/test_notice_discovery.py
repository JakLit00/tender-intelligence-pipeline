from datetime import date

import pytest

from tender_intelligence.storage import register_notice


PUBLICATION_NUMBER = "722762-2026"


@pytest.mark.parametrize(
    ("sources", "expected_flags"),
    [
        (("scope_search",), (True, False)),
        (("predecessor",), (False, True)),
        (("scope_search", "predecessor"), (True, True)),
        (("predecessor", "scope_search"), (True, True)),
        (("predecessor", "predecessor"), (False, True)),
        (("scope_search", "predecessor", "scope_search"), (True, True)),
    ],
)
def test_preserves_discovery_sources(
    db_connection,
    sources,
    expected_flags,
):
    for source in sources:
        register_notice(
            db_connection,
            publication_number=PUBLICATION_NUMBER,
            publication_date=date(2026, 10, 20),
            search_metadata={"publication-number": PUBLICATION_NUMBER},
            discovery_source=source,
        )

    rows = db_connection.execute(
        """
        SELECT
            discovered_by_scope_search,
            discovered_as_predecessor
        FROM raw.notices
        WHERE publication_number = %s
        """,
        (PUBLICATION_NUMBER,),
    ).fetchall()

    assert rows == [expected_flags]


def test_rejects_unknown_discovery_source(db_connection):
    with pytest.raises(ValueError, match="Unsupported discovery source"):
        register_notice(
            db_connection,
            publication_number=PUBLICATION_NUMBER,
            publication_date=date(2026, 10, 20),
            search_metadata={},
            discovery_source="unknown",  # type: ignore[arg-type]
        )

    row = db_connection.execute(
        """
        SELECT count(*)
        FROM raw.notices
        WHERE publication_number = %s
        """,
        (PUBLICATION_NUMBER,),
    ).fetchone()

    assert row == (0,)