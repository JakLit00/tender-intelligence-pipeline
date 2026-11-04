from collections.abc import Iterator

import psycopg
import pytest


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    with psycopg.connect(
        host="127.0.0.1",
        port=5435,
        dbname="tender_intelligence_test",
        user="tender_app",
        password="local_test_app_password",
        connect_timeout=5,
        application_name="tender-intelligence-tests",
        autocommit=True,
    ) as conn:
        row = conn.execute(
            """
            SELECT current_database(), current_user, rolsuper
            FROM pg_roles
            WHERE rolname = current_user
            """
        ).fetchone()

        if row != ("tender_intelligence_test", "tender_app", False):
            raise RuntimeError("Unexpected integration test database or role")

        # Each test gets a transaction that is rolled back even on success.
        with conn.transaction(force_rollback=True):
            yield conn