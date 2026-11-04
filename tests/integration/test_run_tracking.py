from datetime import date

import psycopg
import pytest

from tender_intelligence.run_tracking import (
    finish_run,
    link_run_notice,
    record_notice_outcome,
    start_run,
)
from tender_intelligence.storage import register_notice


@pytest.mark.parametrize("run_mode", ["backfill", "incremental", "retry"])
def test_starts_run(
    db_connection: psycopg.Connection,
    run_mode: str,
) -> None:
    run_id = start_run(
        db_connection,
        run_mode=run_mode,
        date_from=date(2026, 10, 20),
        date_to=date(2026, 10, 29),
    )

    row = db_connection.execute(
        """
        SELECT
            run_mode,
            date_from,
            date_to,
            status,
            started_at,
            finished_at,
            error_message
        FROM ops.pipeline_runs
        WHERE run_id = %s
        """,
        (run_id,),
    ).fetchone()

    assert isinstance(run_id, int)
    assert row is not None
    assert row[:4] == (
        run_mode,
        date(2026, 10, 20),
        date(2026, 10, 29),
        "running",
    )
    assert row[4] is not None
    assert row[5:] == (None, None)


def test_rejects_inverted_run_date_range(
    db_connection: psycopg.Connection,
) -> None:
    with pytest.raises(ValueError, match="date_to"):
        start_run(
            db_connection,
            run_mode="backfill",
            date_from=date(2026, 10, 29),
            date_to=date(2026, 10, 20),
        )


def test_rejects_unknown_run_mode(
    db_connection: psycopg.Connection,
) -> None:
    with pytest.raises(ValueError, match="Unsupported run mode"):
        start_run(
            db_connection,
            run_mode="unknown",
            date_from=date(2026, 10, 20),
            date_to=date(2026, 10, 29),
        )

def test_links_notice_without_resetting_existing_outcome(
    db_connection: psycopg.Connection,
) -> None:
    run_id = start_run(
        db_connection,
        run_mode="backfill",
        date_from=date(2026, 10, 20),
        date_to=date(2026, 10, 29),
    )
    register_notice(
        db_connection,
        publication_number="722762-2026",
        publication_date=date(2026, 10, 20),
        search_metadata={},
    )

    link_run_notice(
        db_connection,
        run_id=run_id,
        publication_number="00722762-2026",
    )

    row = db_connection.execute(
        """
        SELECT publication_number, outcome, error_message
        FROM ops.run_notices
        WHERE run_id = %s
        """,
        (run_id,),
    ).fetchone()
    assert row == ("722762-2026", "pending", None)

    db_connection.execute(
        """
        UPDATE ops.run_notices
        SET outcome = 'processed'
        WHERE run_id = %s AND publication_number = %s
        """,
        (run_id, "722762-2026"),
    )

    link_run_notice(
        db_connection,
        run_id=run_id,
        publication_number="722762-2026",
    )

    rows = db_connection.execute(
        """
        SELECT publication_number, outcome
        FROM ops.run_notices
        WHERE run_id = %s
        """,
        (run_id,),
    ).fetchall()
    assert rows == [("722762-2026", "processed")]


def test_rejects_link_to_missing_run(
    db_connection: psycopg.Connection,
) -> None:
    with pytest.raises(ValueError, match="Pipeline run not found"):
        link_run_notice(
            db_connection,
            run_id=-1,
            publication_number="722762-2026",
        )


def test_rejects_link_to_finished_run(
    db_connection: psycopg.Connection,
) -> None:
    run_id = start_run(
        db_connection,
        run_mode="backfill",
        date_from=date(2026, 10, 20),
        date_to=date(2026, 10, 29),
    )
    db_connection.execute(
        """
        UPDATE ops.pipeline_runs
        SET status = 'succeeded',
            finished_at = CURRENT_TIMESTAMP
        WHERE run_id = %s
        """,
        (run_id,),
    )

    with pytest.raises(ValueError, match="already finished"):
        link_run_notice(
            db_connection,
            run_id=run_id,
            publication_number="722762-2026",
        )


def test_rejects_link_to_missing_publication(
    db_connection: psycopg.Connection,
) -> None:
    run_id = start_run(
        db_connection,
        run_mode="backfill",
        date_from=date(2026, 10, 20),
        date_to=date(2026, 10, 29),
    )

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        link_run_notice(
            db_connection,
            run_id=run_id,
            publication_number="999997-2099",
        )

@pytest.fixture
def linked_notice_run(db_connection: psycopg.Connection) -> int:
    run_id = start_run(
        db_connection,
        run_mode="backfill",
        date_from=date(2026, 10, 20),
        date_to=date(2026, 10, 29),
    )
    register_notice(
        db_connection,
        publication_number="722762-2026",
        publication_date=date(2026, 10, 20),
        search_metadata={},
    )
    link_run_notice(
        db_connection,
        run_id=run_id,
        publication_number="722762-2026",
    )
    return run_id


@pytest.mark.parametrize(
    ("outcome", "error_message"),
    [
        ("processed", None),
        ("skipped", None),
        ("failed", "Invalid XML"),
    ],
)
def test_records_notice_outcome(
    db_connection: psycopg.Connection,
    linked_notice_run: int,
    outcome: str,
    error_message: str | None,
) -> None:
    record_notice_outcome(
        db_connection,
        run_id=linked_notice_run,
        publication_number="722762-2026",
        outcome=outcome,
        error_message=error_message,
    )

    row = db_connection.execute(
        """
        SELECT outcome, error_message
        FROM ops.run_notices
        WHERE run_id = %s AND publication_number = %s
        """,
        (linked_notice_run, "722762-2026"),
    ).fetchone()

    assert row == (outcome, error_message)


@pytest.mark.parametrize(
    ("outcome", "error_message"),
    [
        ("failed", None),
        ("failed", " "),
        ("processed", "Unexpected error"),
        ("skipped", "Unexpected error"),
        ("unknown", None),
    ],
)
def test_rejects_invalid_outcome_arguments(
    db_connection: psycopg.Connection,
    linked_notice_run: int,
    outcome: str,
    error_message: str | None,
) -> None:
    with pytest.raises(ValueError):
        record_notice_outcome(
            db_connection,
            run_id=linked_notice_run,
            publication_number="722762-2026",
            outcome=outcome,
            error_message=error_message,
        )

    row = db_connection.execute(
        """
        SELECT outcome, error_message
        FROM ops.run_notices
        WHERE run_id = %s AND publication_number = %s
        """,
        (linked_notice_run, "722762-2026"),
    ).fetchone()

    assert row == ("pending", None)


def test_rejects_outcome_for_unlinked_publication(
    db_connection: psycopg.Connection,
    linked_notice_run: int,
) -> None:
    with pytest.raises(ValueError, match="is not linked"):
        record_notice_outcome(
            db_connection,
            run_id=linked_notice_run,
            publication_number="999997-2099",
            outcome="processed",
        )


def test_rejects_outcome_for_finished_run(
    db_connection: psycopg.Connection,
    linked_notice_run: int,
) -> None:
    db_connection.execute(
        """
        UPDATE ops.pipeline_runs
        SET status = 'succeeded',
            finished_at = CURRENT_TIMESTAMP
        WHERE run_id = %s
        """,
        (linked_notice_run,),
    )

    with pytest.raises(ValueError, match="already finished"):
        record_notice_outcome(
            db_connection,
            run_id=linked_notice_run,
            publication_number="722762-2026",
            outcome="processed",
        )

@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [
        ("processed", "succeeded"),
        ("skipped", "succeeded"),
        ("failed", "failed"),
    ],
)
def test_finishes_run_from_notice_outcome(
    db_connection: psycopg.Connection,
    linked_notice_run: int,
    outcome: str,
    expected_status: str,
) -> None:
    record_notice_outcome(
        db_connection,
        run_id=linked_notice_run,
        publication_number="722762-2026",
        outcome=outcome,
        error_message="Invalid XML" if outcome == "failed" else None,
    )

    assert finish_run(
        db_connection, run_id=linked_notice_run
    ) == expected_status

    row = db_connection.execute(
        """
        SELECT status, finished_at >= started_at, error_message
        FROM ops.pipeline_runs
        WHERE run_id = %s
        """,
        (linked_notice_run,),
    ).fetchone()

    expected_error = (
        "1 of 1 publications failed" if outcome == "failed" else None
    )
    assert row == (expected_status, True, expected_error)


def test_finishes_empty_run_successfully(
    db_connection: psycopg.Connection,
) -> None:
    run_id = start_run(
        db_connection,
        run_mode="backfill",
        date_from=date(2026, 10, 20),
        date_to=date(2026, 10, 29),
    )

    assert finish_run(db_connection, run_id=run_id) == "succeeded"


def test_cannot_finish_run_with_pending_publications(
    db_connection: psycopg.Connection,
    linked_notice_run: int,
) -> None:
    with pytest.raises(ValueError, match="pending publications"):
        finish_run(db_connection, run_id=linked_notice_run)

    row = db_connection.execute(
        """
        SELECT status, finished_at
        FROM ops.pipeline_runs
        WHERE run_id = %s
        """,
        (linked_notice_run,),
    ).fetchone()

    assert row == ("running", None)


def test_finishes_mixed_results_as_partial(
    db_connection: psycopg.Connection,
    linked_notice_run: int,
) -> None:
    record_notice_outcome(
        db_connection,
        run_id=linked_notice_run,
        publication_number="722762-2026",
        outcome="processed",
    )

    register_notice(
        db_connection,
        publication_number="706539-2026",
        publication_date=date(2026, 10, 12),
        search_metadata={},
    )
    link_run_notice(
        db_connection,
        run_id=linked_notice_run,
        publication_number="706539-2026",
    )
    record_notice_outcome(
        db_connection,
        run_id=linked_notice_run,
        publication_number="706539-2026",
        outcome="failed",
        error_message="Download failed",
    )

    assert finish_run(
        db_connection, run_id=linked_notice_run
    ) == "partial"

    row = db_connection.execute(
        """
        SELECT error_message
        FROM ops.pipeline_runs
        WHERE run_id = %s
        """,
        (linked_notice_run,),
    ).fetchone()

    assert row == ("1 of 2 publications failed",)


def test_cannot_finish_run_twice(
    db_connection: psycopg.Connection,
) -> None:
    run_id = start_run(
        db_connection,
        run_mode="backfill",
        date_from=date(2026, 10, 20),
        date_to=date(2026, 10, 29),
    )
    finish_run(db_connection, run_id=run_id)

    with pytest.raises(ValueError, match="already finished"):
        finish_run(db_connection, run_id=run_id)