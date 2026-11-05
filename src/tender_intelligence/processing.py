from typing import Literal
from xml.etree.ElementTree import ParseError

import psycopg

from tender_intelligence.normalization import normalize_publication_number
from tender_intelligence.preparation import prepare_notice
from tender_intelligence.storage import save_prepared_notice

ProcessingOutcome = Literal["processed", "skipped", "failed"]


def process_notice(
    conn: psycopg.Connection,
    publication_number: str,
    *,
    force: bool = False,
) -> ProcessingOutcome:
    """Process a stored XML and update its status in one transaction."""
    publication_number = normalize_publication_number(publication_number)

    with conn.transaction():
        with conn.cursor() as cursor:
            # Keep the source XML stable and serialize processing of this notice.
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

            xml_content, processing_status = row

            if processing_status == "succeeded" and not force:
                return "skipped"

            if xml_content is None:
                raise ValueError(f"XML has not been downloaded: {publication_number}")

            try:
                bundle = prepare_notice(
                    bytes(xml_content),
                    expected_publication_number=publication_number,
                )
            except (ValueError, ParseError) as exc:
                # PostgreSQL text cannot store NUL characters from invalid input.
                error_message = f"{type(exc).__name__}: {exc}".replace("\x00", "\\x00")

                cursor.execute(
                    """
                    UPDATE raw.notices
                    SET processing_status = 'failed',
                        processed_at = NULL,
                        last_error = %s
                    WHERE publication_number = %s
                    """,
                    (error_message, publication_number),
                )
                return "failed"

            save_prepared_notice(conn, bundle)

            cursor.execute(
                """
                UPDATE raw.notices
                SET processing_status = 'succeeded',
                    processed_at = CURRENT_TIMESTAMP,
                    last_error = NULL
                WHERE publication_number = %s
                """,
                (publication_number,),
            )

    return "processed"
