from unittest.mock import patch

import pytest

from tender_intelligence.predecessors import (
    DownloadedPredecessor,
    persist_predecessor,
)
from tender_intelligence.preparation import prepare_notice


PUBLICATION_NUMBER = "722762-2026"


@pytest.fixture
def downloaded_predecessor(notice_xml):
    return DownloadedPredecessor(
        search_metadata={"publication-number": PUBLICATION_NUMBER},
        xml_content=notice_xml,
        bundle=prepare_notice(
            notice_xml,
            expected_publication_number=PUBLICATION_NUMBER,
        ),
    )


def test_persists_predecessor_and_its_lots(
    db_connection,
    downloaded_predecessor,
):
    outcome = persist_predecessor(
        db_connection,
        downloaded_predecessor,
    )

    assert outcome == "processed"

    raw_row = db_connection.execute(
        """
        SELECT
            discovered_by_scope_search,
            discovered_as_predecessor,
            processing_status,
            xml_content
        FROM raw.notices
        WHERE publication_number = %s
        """,
        (PUBLICATION_NUMBER,),
    ).fetchone()

    assert raw_row == (
        False,
        True,
        "succeeded",
        downloaded_predecessor.xml_content,
    )

    notice_row = db_connection.execute(
        """
        SELECT publication_number
        FROM staging.notices
        WHERE publication_number = %s
        """,
        (PUBLICATION_NUMBER,),
    ).fetchone()

    assert notice_row == (PUBLICATION_NUMBER,)

    lots = db_connection.execute(
        """
        SELECT lot_id
        FROM staging.notice_lots
        WHERE publication_number = %s
        ORDER BY lot_id
        """,
        (PUBLICATION_NUMBER,),
    ).fetchall()

    assert lots == [("LOT-0001",)]


def test_skips_identical_processed_predecessor(
    db_connection,
    downloaded_predecessor,
):
    first_outcome = persist_predecessor(
        db_connection,
        downloaded_predecessor,
    )
    second_outcome = persist_predecessor(
        db_connection,
        downloaded_predecessor,
    )

    assert first_outcome == "processed"
    assert second_outcome == "skipped"

    row = db_connection.execute(
        """
        SELECT count(*)
        FROM staging.notice_lots
        WHERE publication_number = %s
        """,
        (PUBLICATION_NUMBER,),
    ).fetchone()

    assert row == (1,)


def test_rolls_back_registration_when_processing_raises(
    db_connection,
    downloaded_predecessor,
):
    with patch(
        "tender_intelligence.predecessors.process_notice",
        side_effect=RuntimeError("Simulated processing failure"),
    ):
        with pytest.raises(RuntimeError, match="Simulated processing failure"):
            persist_predecessor(
                db_connection,
                downloaded_predecessor,
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