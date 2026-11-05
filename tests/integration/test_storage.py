from dataclasses import replace
from datetime import date, datetime, timezone

import psycopg
import pytest

from tender_intelligence.models import (
    PreparedLot,
    PreparedNotice,
    PreparedNoticeBundle,
)
from tender_intelligence.storage import save_prepared_notice


@pytest.fixture
def prepared_bundle(
    db_connection: psycopg.Connection,
) -> PreparedNoticeBundle:
    notice = PreparedNotice(
        publication_number="999999-2099",
        notice_id="8ac273c6-7603-4ad1-b9a2-8ed027ed773f",
        notice_version="01",
        procedure_id="4835bb55-6b3a-4579-81d8-b34df3e663ce",
        notice_type="cn-standard",
        publication_date=date(2099, 1, 1),
        changed_notice_identifier_raw=None,
        reference_type="missing",
        previous_publication_number=None,
        previous_notice_id=None,
        previous_notice_version=None,
        change_reason_code=None,
    )

    first_lot = PreparedLot(
        publication_number=notice.publication_number,
        lot_id="LOT-0001",
        submission_deadline_date_raw="2099-02-01Z",
        submission_deadline_time_raw="09:00:00Z",
        submission_deadline_local_date=date(2099, 2, 1),
        submission_deadline_at=datetime(2099, 2, 1, 9, 0, tzinfo=timezone.utc),
    )

    db_connection.execute(
        """
        INSERT INTO raw.notices (
            publication_number,
            publication_date,
            search_metadata
        )
        VALUES (%s, %s, %s::jsonb)
        """,
        (
            notice.publication_number,
            notice.publication_date,
            '{"source": "integration-test"}',
        ),
    )

    return PreparedNoticeBundle(
        notice=notice,
        lots=(
            first_lot,
            replace(first_lot, lot_id="LOT-0002"),
        ),
    )


def read_staging(
    conn: psycopg.Connection,
    publication_number: str,
) -> tuple:
    notices = conn.execute(
        """
        SELECT *
        FROM staging.notices
        WHERE publication_number = %s
        """,
        (publication_number,),
    ).fetchall()

    lots = conn.execute(
        """
        SELECT *
        FROM staging.notice_lots
        WHERE publication_number = %s
        ORDER BY lot_id
        """,
        (publication_number,),
    ).fetchall()

    return notices, lots


def test_repeated_save_does_not_duplicate_records(
    db_connection: psycopg.Connection,
    prepared_bundle: PreparedNoticeBundle,
) -> None:
    save_prepared_notice(db_connection, prepared_bundle)
    save_prepared_notice(db_connection, prepared_bundle)

    notices, lots = read_staging(
        db_connection,
        prepared_bundle.notice.publication_number,
    )

    assert len(notices) == 1
    assert len(lots) == 2


def test_reprocessing_updates_notice_and_removes_obsolete_lots(
    db_connection: psycopg.Connection,
    prepared_bundle: PreparedNoticeBundle,
) -> None:
    save_prepared_notice(db_connection, prepared_bundle)

    updated_bundle = replace(
        prepared_bundle,
        notice=replace(
            prepared_bundle.notice,
            change_reason_code="cor-buy",
        ),
        lots=(prepared_bundle.lots[0],),
    )
    save_prepared_notice(db_connection, updated_bundle)

    publication_number = prepared_bundle.notice.publication_number

    reason = db_connection.execute(
        """
        SELECT change_reason_code
        FROM staging.notices
        WHERE publication_number = %s
        """,
        (publication_number,),
    ).fetchone()

    lot_ids = db_connection.execute(
        """
        SELECT lot_id
        FROM staging.notice_lots
        WHERE publication_number = %s
        ORDER BY lot_id
        """,
        (publication_number,),
    ).fetchall()

    assert reason == ("cor-buy",)
    assert lot_ids == [("LOT-0001",)]


def test_failed_save_restores_previous_notice_and_lots(
    db_connection: psycopg.Connection,
    prepared_bundle: PreparedNoticeBundle,
) -> None:
    save_prepared_notice(db_connection, prepared_bundle)

    publication_number = prepared_bundle.notice.publication_number
    before = read_staging(db_connection, publication_number)

    invalid_bundle = replace(
        prepared_bundle,
        notice=replace(
            prepared_bundle.notice,
            change_reason_code="update-add",
        ),
        lots=(
            prepared_bundle.lots[0],
            replace(prepared_bundle.lots[1], lot_id=""),
        ),
    )

    with pytest.raises(psycopg.errors.CheckViolation):
        save_prepared_notice(db_connection, invalid_bundle)

    assert read_staging(db_connection, publication_number) == before


def test_empty_lot_set_removes_previous_lots(
    db_connection: psycopg.Connection,
    prepared_bundle: PreparedNoticeBundle,
) -> None:
    save_prepared_notice(db_connection, prepared_bundle)

    save_prepared_notice(
        db_connection,
        replace(prepared_bundle, lots=()),
    )

    notices, lots = read_staging(
        db_connection,
        prepared_bundle.notice.publication_number,
    )

    assert len(notices) == 1
    assert lots == []


def test_rejects_lot_from_another_publication(
    db_connection: psycopg.Connection,
    prepared_bundle: PreparedNoticeBundle,
) -> None:
    invalid_bundle = replace(
        prepared_bundle,
        lots=(
            replace(
                prepared_bundle.lots[0],
                publication_number="999998-2099",
            ),
        ),
    )

    with pytest.raises(ValueError, match="different publication"):
        save_prepared_notice(db_connection, invalid_bundle)

    assert read_staging(
        db_connection,
        prepared_bundle.notice.publication_number,
    ) == ([], [])


def test_rejects_duplicate_lot_ids(
    db_connection: psycopg.Connection,
    prepared_bundle: PreparedNoticeBundle,
) -> None:
    invalid_bundle = replace(
        prepared_bundle,
        lots=(
            prepared_bundle.lots[0],
            prepared_bundle.lots[0],
        ),
    )

    with pytest.raises(ValueError, match="Duplicate lot ID"):
        save_prepared_notice(db_connection, invalid_bundle)

    assert read_staging(
        db_connection,
        prepared_bundle.notice.publication_number,
    ) == ([], [])
