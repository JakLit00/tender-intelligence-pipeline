from typing import Any

import psycopg

from tender_intelligence.search_preparation import prepare_search_batch
from tender_intelligence.storage import register_notice


def register_search_results(
    conn: psycopg.Connection,
    notices: list[dict[str, Any]],
) -> int:
    """Validate and register a complete search batch atomically."""
    batch = prepare_search_batch(notices)

    if batch.empty:
        return 0

    with conn.transaction():
        for row in batch.itertuples(index=False):
            register_notice(
                conn,
                publication_number=row.publication_number,
                publication_date=row.publication_date,
                search_metadata=row.search_metadata,
            )

    return len(batch)