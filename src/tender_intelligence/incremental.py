from datetime import date, timedelta
from psycopg import Connection

def calculate_incremental_window(
    *,
    initial_date: date,
    last_successful_date: date | None,
    today: date,
    overlap_days: int = 3,
) -> tuple[date, date] | None:
    if type(overlap_days) is not int or overlap_days < 1:
        raise ValueError("overlap_days must be a positive integer")

    date_to = today - timedelta(days=1)

    if initial_date > date_to:
        return None

    if last_successful_date is None:
        return initial_date, date_to

    if last_successful_date < initial_date:
        raise ValueError("Last successful date precedes the initial date")

    if last_successful_date > date_to:
        raise ValueError("Last successful date is later than yesterday")

    # Include the last successful day in the overlap.
    date_from = max(
        initial_date,
        last_successful_date - timedelta(days=overlap_days - 1),
    )

    return date_from, date_to

def get_last_successful_date(
    connection: Connection,
    *,
    initial_date: date,
) -> date | None:
    rows = connection.execute(
        """
        SELECT date_from, date_to
        FROM ops.pipeline_runs
        WHERE status = 'succeeded'
          AND run_mode IN ('backfill', 'incremental')
          AND date_to >= %s
        ORDER BY date_from, date_to
        """,
        (initial_date,),
    ).fetchall()

    covered_until = None
    next_required_date = initial_date

    for date_from, date_to in rows:
        if date_from > next_required_date:
            break

        if covered_until is None or date_to > covered_until:
            covered_until = date_to
            next_required_date = date_to + timedelta(days=1)

    return covered_until