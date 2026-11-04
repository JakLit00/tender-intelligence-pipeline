from unittest.mock import patch

import pytest

from tender_intelligence.predecessors import (
    DownloadedPredecessor,
    persist_predecessor,
)
from tender_intelligence.preparation import prepare_notice

from dataclasses import replace

from tender_intelligence.predecessors import (
    find_missing_predecessor_publications,
)

from tender_intelligence.models import PreparedNoticeBundle
from tender_intelligence.storage import register_notice, save_prepared_notice

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

@pytest.fixture(params=["publication_number", "notice_version"])
def predecessor_chain(request, downloaded_predecessor):
    previous_id = "df078ce7-100b-4415-aad6-2db2b053ef77"
    current_notice = downloaded_predecessor.bundle.notice

    previous_notice = replace(
        current_notice,
        publication_number="706539-2026",
        notice_id=previous_id,
        notice_version="02",
        reference_type="missing",
        changed_notice_identifier_raw=None,
        previous_publication_number=None,
        previous_notice_id=None,
        previous_notice_version=None,
        change_reason_code=None,
    )

    if request.param == "notice_version":
        current_notice = replace(
            current_notice,
            reference_type="notice_version",
            changed_notice_identifier_raw=f"{previous_id}-02",
            previous_publication_number=None,
            previous_notice_id=previous_id,
            previous_notice_version="02",
        )

    return current_notice, previous_notice


def test_missing_predecessor_list_is_empty_for_empty_database(db_connection):
    assert find_missing_predecessor_publications(db_connection) == []


def test_finds_notice_with_missing_predecessor(
    db_connection,
    predecessor_chain,
):
    current, _ = predecessor_chain

    register_notice(
        db_connection,
        publication_number=current.publication_number,
        publication_date=current.publication_date,
        search_metadata={},
    )
    save_prepared_notice(
        db_connection,
        PreparedNoticeBundle(notice=current, lots=()),
    )

    assert find_missing_predecessor_publications(db_connection) == [
        current.publication_number
    ]


def test_excludes_notice_after_predecessor_is_stored(
    db_connection,
    predecessor_chain,
):
    current, previous = predecessor_chain

    for notice in (current, previous):
        register_notice(
            db_connection,
            publication_number=notice.publication_number,
            publication_date=notice.publication_date,
            search_metadata={},
        )
        save_prepared_notice(
            db_connection,
            PreparedNoticeBundle(notice=notice, lots=()),
        )

    assert find_missing_predecessor_publications(db_connection) == []