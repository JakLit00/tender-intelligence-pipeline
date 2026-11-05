import re
from dataclasses import dataclass
from typing import Any

from psycopg import Connection

from tender_intelligence.models import PreparedNotice, PreparedNoticeBundle
from tender_intelligence.normalization import normalize_notice_id
from tender_intelligence.preparation import prepare_notice
from tender_intelligence.processing import ProcessingOutcome, process_notice
from tender_intelligence.storage import register_notice, save_notice_xml
from tender_intelligence.ted_client import fetch_all_notices, fetch_notice_xml


def find_notice_version(
    notice_id: str,
    notice_version: str,
) -> dict[str, Any] | None:
    normalized_id = normalize_notice_id(notice_id)

    if not re.fullmatch(r"[0-9]{2}", notice_version):
        raise ValueError("Notice version must contain exactly two digits")

    # Predecessors may fall outside the original date and business filters.
    query = (
        f'notice-identifier = "{normalized_id}" AND notice-version = "{notice_version}"'
    )
    notices = fetch_all_notices(query, page_size=10)

    if not notices:
        return None

    if len(notices) > 1:
        raise ValueError(
            f"Ambiguous notice version: {normalized_id}-{notice_version}; "
            f"found {len(notices)} publications"
        )

    return notices[0]


def validate_predecessor(
    current: PreparedNotice,
    predecessor: PreparedNotice,
) -> None:
    if current.publication_number == predecessor.publication_number:
        raise ValueError("A notice cannot be its own predecessor")

    if current.reference_type == "publication_number":
        matches = current.previous_publication_number == predecessor.publication_number
    elif current.reference_type == "notice_version":
        matches = (
            current.previous_notice_id == predecessor.notice_id
            and current.previous_notice_version == predecessor.notice_version
        )
    else:
        raise ValueError("Notice has no supported predecessor reference")

    if not matches:
        raise ValueError("Predecessor identity does not match the reference")

    # Missing procedure IDs do not establish a mismatch.
    if (
        current.procedure_id is not None
        and predecessor.procedure_id is not None
        and current.procedure_id != predecessor.procedure_id
    ):
        raise ValueError("Predecessor belongs to a different procedure")


@dataclass(frozen=True)
class DownloadedPredecessor:
    search_metadata: dict[str, Any]
    xml_content: bytes
    bundle: PreparedNoticeBundle


def download_predecessor(
    current: PreparedNotice,
) -> DownloadedPredecessor | None:
    if current.reference_type == "missing":
        return None

    if current.reference_type == "notice_version":
        if (
            current.previous_notice_id is None
            or current.previous_notice_version is None
        ):
            raise ValueError("Incomplete predecessor version reference")

        metadata = find_notice_version(
            current.previous_notice_id,
            current.previous_notice_version,
        )

    elif current.reference_type == "publication_number":
        if current.previous_publication_number is None:
            raise ValueError("Missing predecessor publication number")

        notices = fetch_all_notices(
            f'publication-number = "{current.previous_publication_number}"',
            page_size=10,
        )

        if len(notices) > 1:
            raise ValueError("Ambiguous predecessor publication number")

        metadata = notices[0] if notices else None

    else:
        raise ValueError("Unsupported predecessor reference")

    if metadata is None:
        return None

    publication_number = metadata["publication-number"]
    xml_content = fetch_notice_xml(publication_number)
    bundle = prepare_notice(
        xml_content,
        expected_publication_number=publication_number,
    )
    validate_predecessor(current, bundle.notice)

    return DownloadedPredecessor(
        search_metadata=metadata,
        xml_content=xml_content,
        bundle=bundle,
    )


def persist_predecessor(
    connection: Connection,
    predecessor: DownloadedPredecessor,
) -> ProcessingOutcome:
    notice = predecessor.bundle.notice

    with connection.transaction():
        register_notice(
            connection,
            publication_number=notice.publication_number,
            publication_date=notice.publication_date,
            search_metadata=predecessor.search_metadata,
            discovery_source="predecessor",
        )
        save_notice_xml(
            connection,
            notice.publication_number,
            predecessor.xml_content,
        )
        return process_notice(connection, notice.publication_number)


def find_missing_predecessor_publications(
    connection: Connection,
) -> list[str]:
    rows = connection.execute(
        """
        SELECT current_notice.publication_number
        FROM staging.notices AS current_notice
        WHERE current_notice.reference_type IN (
            'publication_number',
            'notice_version'
        )
          AND NOT EXISTS (
              SELECT 1
              FROM staging.notices AS predecessor
              WHERE (
                  current_notice.reference_type = 'publication_number'
                  AND predecessor.publication_number
                      = current_notice.previous_publication_number
              )
              OR (
                  current_notice.reference_type = 'notice_version'
                  AND predecessor.notice_id
                      = current_notice.previous_notice_id
                  AND predecessor.notice_version
                      = current_notice.previous_notice_version
              )
          )
        ORDER BY current_notice.publication_number
        """
    ).fetchall()

    return [row[0] for row in rows]
