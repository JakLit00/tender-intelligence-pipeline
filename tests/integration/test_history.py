from unittest.mock import patch
from urllib.error import URLError

import pytest

from tender_intelligence.history import run_history
from tender_intelligence.predecessors import DownloadedPredecessor
from tender_intelligence.preparation import prepare_notice
from tender_intelligence.processing import process_notice
from tender_intelligence.storage import register_notice, save_notice_xml


CURRENT_PUBLICATION = "722762-2026"
PREVIOUS_PUBLICATION = "706539-2026"


def seed_notice(connection, xml_content, publication_number):
    bundle = prepare_notice(
        xml_content,
        expected_publication_number=publication_number,
    )
    register_notice(
        connection,
        publication_number=publication_number,
        publication_date=bundle.notice.publication_date,
        search_metadata={"publication-number": publication_number},
    )
    save_notice_xml(connection, publication_number, xml_content)

    assert process_notice(connection, publication_number) == "processed"


@pytest.fixture
def predecessor_document(notice_xml):
    # Change the predecessor reference before replacing the document number.
    xml_content = (
        notice_xml
        .replace(b"706539-2026", b"668566-2026")
        .replace(b"722762-2026", b"706539-2026")
        .replace(
            b"8ac273c6-7603-4ad1-b9a2-8ed027ed773f",
            b"df078ce7-100b-4415-aad6-2db2b053ef77",
        )
    )
    return DownloadedPredecessor(
        search_metadata={"publication-number": PREVIOUS_PUBLICATION},
        xml_content=xml_content,
        bundle=prepare_notice(
            xml_content,
            expected_publication_number=PREVIOUS_PUBLICATION,
        ),
    )


def test_history_returns_none_when_no_predecessors_are_missing(
    pipeline_connection,
):
    with patch(
        "tender_intelligence.history.download_predecessor",
    ) as download:
        assert run_history(pipeline_connection) is None

    download.assert_not_called()

    row = pipeline_connection.execute(
        "SELECT count(*) FROM ops.pipeline_runs"
    ).fetchone()
    assert row == (0,)


def test_history_persists_predecessor_and_finishes_run(
    pipeline_connection,
    notice_xml,
    predecessor_document,
):
    seed_notice(pipeline_connection, notice_xml, CURRENT_PUBLICATION)

    with patch(
        "tender_intelligence.history.download_predecessor",
        return_value=predecessor_document,
    ) as download:
        run_id = run_history(pipeline_connection)

    assert run_id is not None
    download.assert_called_once()
    assert download.call_args.args[0].publication_number == CURRENT_PUBLICATION

    run = pipeline_connection.execute(
        """
        SELECT run_mode, status, finished_at IS NOT NULL
        FROM ops.pipeline_runs
        WHERE run_id = %s
        """,
        (run_id,),
    ).fetchone()
    assert run == ("history", "succeeded", True)

    outcome = pipeline_connection.execute(
        """
        SELECT publication_number, outcome
        FROM ops.run_notices
        WHERE run_id = %s
        """,
        (run_id,),
    ).fetchall()
    assert outcome == [(CURRENT_PUBLICATION, "processed")]

    predecessor = pipeline_connection.execute(
        """
        SELECT
            processing_status,
            discovered_by_scope_search,
            discovered_as_predecessor
        FROM raw.notices
        WHERE publication_number = %s
        """,
        (PREVIOUS_PUBLICATION,),
    ).fetchone()
    assert predecessor == ("succeeded", False, True)


@pytest.mark.parametrize("failure", ["not_found", "network"])
def test_history_records_predecessor_lookup_failure(
    pipeline_connection,
    notice_xml,
    failure,
):
    seed_notice(pipeline_connection, notice_xml, CURRENT_PUBLICATION)
    error = URLError("Simulated network failure") if failure == "network" else None

    with patch(
        "tender_intelligence.history.download_predecessor",
        return_value=None,
        side_effect=error,
    ):
        run_id = run_history(pipeline_connection)

    run = pipeline_connection.execute(
        """
        SELECT status
        FROM ops.pipeline_runs
        WHERE run_id = %s
        """,
        (run_id,),
    ).fetchone()
    assert run == ("failed",)

    outcome = pipeline_connection.execute(
        """
        SELECT outcome, error_message
        FROM ops.run_notices
        WHERE run_id = %s AND publication_number = %s
        """,
        (run_id, CURRENT_PUBLICATION),
    ).fetchone()

    assert outcome is not None
    assert outcome[0] == "failed"
    expected_message = (
        "Simulated network failure"
        if failure == "network"
        else "Predecessor was not found in TED"
    )
    assert expected_message in outcome[1]


def test_history_rolls_back_predecessor_if_outcome_write_fails(
    pipeline_connection,
    notice_xml,
    predecessor_document,
):
    seed_notice(pipeline_connection, notice_xml, CURRENT_PUBLICATION)

    with (
        patch(
            "tender_intelligence.history.download_predecessor",
            return_value=predecessor_document,
        ),
        patch(
            "tender_intelligence.history.record_notice_outcome",
            side_effect=RuntimeError("Simulated outcome write failure"),
        ),
    ):
        with pytest.raises(RuntimeError, match="Simulated outcome write failure"):
            run_history(pipeline_connection)

    predecessor = pipeline_connection.execute(
        """
        SELECT count(*)
        FROM raw.notices
        WHERE publication_number = %s
        """,
        (PREVIOUS_PUBLICATION,),
    ).fetchone()
    assert predecessor == (0,)

    runs = pipeline_connection.execute(
        "SELECT status FROM ops.pipeline_runs"
    ).fetchall()
    assert runs == [("failed",)]

    outcomes = pipeline_connection.execute(
        "SELECT outcome FROM ops.run_notices"
    ).fetchall()
    assert outcomes == [("pending",)]


def test_history_respects_batch_limit(
    pipeline_connection,
    notice_xml,
    predecessor_document,
):
    seed_notice(pipeline_connection, notice_xml, CURRENT_PUBLICATION)

    second_xml = notice_xml.replace(b"722762-2026", b"722763-2026")
    seed_notice(pipeline_connection, second_xml, "722763-2026")

    with patch(
        "tender_intelligence.history.download_predecessor",
        return_value=predecessor_document,
    ) as download:
        run_id = run_history(pipeline_connection, max_notices=1)

    download.assert_called_once()

    outcomes = pipeline_connection.execute(
        """
        SELECT publication_number, outcome
        FROM ops.run_notices
        WHERE run_id = %s
        """,
        (run_id,),
    ).fetchall()
    assert outcomes == [(CURRENT_PUBLICATION, "processed")]