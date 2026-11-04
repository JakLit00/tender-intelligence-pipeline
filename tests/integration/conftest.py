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

@pytest.fixture
def pipeline_connection() -> Iterator[psycopg.Connection]:
    def clear_test_data() -> None:
        with psycopg.connect(
            host="127.0.0.1",
            port=5435,
            dbname="tender_intelligence_test",
            user="tender_test_admin",
            password="local_test_admin_password",
            connect_timeout=5,
            autocommit=True,
        ) as admin:
            identity = admin.execute(
                "SELECT current_database(), current_user"
            ).fetchone()

            if identity != (
                "tender_intelligence_test",
                "tender_test_admin",
            ):
                raise RuntimeError("Refusing to clear an unexpected database")

            # Only the dedicated test database is cleared.
            admin.execute(
                """
                TRUNCATE TABLE
                    ops.run_notices,
                    staging.notice_lots,
                    staging.notices,
                    raw.notices,
                    ops.pipeline_runs
                """
            )

    clear_test_data()

    try:
        with psycopg.connect(
            host="127.0.0.1",
            port=5435,
            dbname="tender_intelligence_test",
            user="tender_app",
            password="local_test_app_password",
            connect_timeout=5,
            application_name="tender-pipeline-tests",
            autocommit=True,
        ) as conn:
            identity = conn.execute(
                "SELECT current_database(), current_user"
            ).fetchone()

            if identity != ("tender_intelligence_test", "tender_app"):
                raise RuntimeError("Unexpected pipeline test connection")

            yield conn
    finally:
        clear_test_data()