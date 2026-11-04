from datetime import date
from typing import Any, Literal

from tender_intelligence.normalization import normalize_publication_number
from tender_intelligence.models import PreparedNoticeBundle

from dataclasses import asdict

from psycopg import Connection
from psycopg.types.json import Jsonb

import psycopg





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
    submission_deadline_at,
    submission_deadline_quality_issue
)
VALUES (
    %(publication_number)s,
    %(lot_id)s,
    %(submission_deadline_date_raw)s,
    %(submission_deadline_time_raw)s,
    %(submission_deadline_local_date)s,
    %(submission_deadline_at)s,
    %(submission_deadline_quality_issue)s
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

def save_notice_xml(
    conn: psycopg.Connection,
    publication_number: str,
    xml_content: bytes,
) -> bool:
    """Store changed XML and return whether processing is required."""
    if not xml_content:
        raise ValueError("XML content must not be empty")

    with conn.transaction():
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT xml_content, processing_status
                FROM raw.notices
                WHERE publication_number = %s
                FOR UPDATE
                """,
                (publication_number,),
            )
            row = cursor.fetchone()

            if row is None:
                raise ValueError(
                    f"Publication not found in raw.notices: {publication_number}"
                )

            previous_xml, processing_status = row

            if previous_xml == xml_content:
                return processing_status != "succeeded"

            # Changed source bytes invalidate the previous processing result.
            cursor.execute(
                """
                UPDATE raw.notices
                SET xml_content = %s,
                    xml_downloaded_at = CURRENT_TIMESTAMP,
                    processing_status = 'pending',
                    processed_at = NULL,
                    last_error = NULL
                WHERE publication_number = %s
                """,
                (xml_content, publication_number),
            )

    return True

def register_notice(
    connection: Connection,
    *,
    publication_number: str,
    publication_date: date,
    search_metadata: dict[str, Any],
    discovery_source: Literal["scope_search", "predecessor"] = "scope_search",
) -> None:
    if discovery_source not in ("scope_search", "predecessor"):
        raise ValueError(f"Unsupported discovery source: {discovery_source}")

    normalized_number = normalize_publication_number(publication_number)

    with connection.transaction():
        connection.execute(
            """
            INSERT INTO raw.notices (
                publication_number,
                publication_date,
                search_metadata,
                discovered_by_scope_search,
                discovered_as_predecessor
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (publication_number) DO UPDATE
            SET
                publication_date = EXCLUDED.publication_date,
                search_metadata = EXCLUDED.search_metadata,
                last_seen_at = clock_timestamp(),
                discovered_by_scope_search = (
                    raw.notices.discovered_by_scope_search
                    OR EXCLUDED.discovered_by_scope_search
                ),
                discovered_as_predecessor = (
                    raw.notices.discovered_as_predecessor
                    OR EXCLUDED.discovered_as_predecessor
                )
            """,
            (
                normalized_number,
                publication_date,
                Jsonb(search_metadata),
                discovery_source == "scope_search",
                discovery_source == "predecessor",
            ),
        )