from dataclasses import asdict

import psycopg

from tender_intelligence.models import PreparedNoticeBundle


UPSERT_NOTICE_SQL = """
INSERT INTO staging.notices (
    publication_number,
    notice_id,
    notice_version,
    procedure_id,
    notice_type,
    publication_date,
    changed_notice_identifier_raw,
    reference_type,
    previous_publication_number,
    previous_notice_id,
    previous_notice_version,
    change_reason_code
)
VALUES (
    %(publication_number)s,
    %(notice_id)s,
    %(notice_version)s,
    %(procedure_id)s,
    %(notice_type)s,
    %(publication_date)s,
    %(changed_notice_identifier_raw)s,
    %(reference_type)s,
    %(previous_publication_number)s,
    %(previous_notice_id)s,
    %(previous_notice_version)s,
    %(change_reason_code)s
)
ON CONFLICT (publication_number) DO UPDATE SET
    notice_id = EXCLUDED.notice_id,
    notice_version = EXCLUDED.notice_version,
    procedure_id = EXCLUDED.procedure_id,
    notice_type = EXCLUDED.notice_type,
    publication_date = EXCLUDED.publication_date,
    changed_notice_identifier_raw = EXCLUDED.changed_notice_identifier_raw,
    reference_type = EXCLUDED.reference_type,
    previous_publication_number = EXCLUDED.previous_publication_number,
    previous_notice_id = EXCLUDED.previous_notice_id,
    previous_notice_version = EXCLUDED.previous_notice_version,
    change_reason_code = EXCLUDED.change_reason_code,
    parsed_at = CURRENT_TIMESTAMP
"""

INSERT_LOT_SQL = """
INSERT INTO staging.notice_lots (
    publication_number,
    lot_id,
    submission_deadline_date_raw,
    submission_deadline_time_raw,
    submission_deadline_local_date,
    submission_deadline_at
)
VALUES (
    %(publication_number)s,
    %(lot_id)s,
    %(submission_deadline_date_raw)s,
    %(submission_deadline_time_raw)s,
    %(submission_deadline_local_date)s,
    %(submission_deadline_at)s
)
"""


def save_prepared_notice(
    conn: psycopg.Connection,
    bundle: PreparedNoticeBundle,
) -> None:
    """Atomically upsert a notice and replace its complete lot set."""
    publication_number = bundle.notice.publication_number
    lot_ids: set[str] = set()

    for lot in bundle.lots:
        if lot.publication_number != publication_number:
            raise ValueError(
                f"Lot {lot.lot_id!r} belongs to a different publication"
            )

        if lot.lot_id in lot_ids:
            raise ValueError(f"Duplicate lot ID: {lot.lot_id!r}")

        lot_ids.add(lot.lot_id)

    with conn.transaction():
        with conn.cursor() as cursor:
            # Upsert the parent first to serialize writes for this publication.
            cursor.execute(
                UPSERT_NOTICE_SQL,
                asdict(bundle.notice),
            )

            # Full replacement also removes lots absent from the new result.
            cursor.execute(
                """
                DELETE FROM staging.notice_lots
                WHERE publication_number = %s
                """,
                (publication_number,),
            )

            if bundle.lots:
                cursor.executemany(
                    INSERT_LOT_SQL,
                    [asdict(lot) for lot in bundle.lots],
                )