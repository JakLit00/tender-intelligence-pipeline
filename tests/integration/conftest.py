import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

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


@pytest.fixture(scope="session")
def dbt_runner(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    temporary = tmp_path_factory.mktemp("dbt-test")
    # A dedicated profile cannot inherit a developer's host, target or password.
    (temporary / "profiles.yml").write_text(
        "tender_intelligence:\n"
        "  target: test\n"
        "  outputs:\n"
        "    test:\n"
        "      type: postgres\n"
        "      host: 127.0.0.1\n"
        "      port: 5435\n"
        "      dbname: tender_intelligence_test\n"
        "      user: tender_dbt\n"
        "      password: local_test_dbt_password\n"
        "      schema: analytics\n"
        "      threads: 2\n"
        "      connect_timeout: 5\n",
        encoding="utf-8",
    )
    with psycopg.connect(
        host="127.0.0.1",
        port=5435,
        dbname="tender_intelligence_test",
        user="tender_dbt",
        password="local_test_dbt_password",
        connect_timeout=5,
        autocommit=True,
    ) as connection:
        identity = connection.execute(
            "SELECT current_database(), current_user, rolsuper "
            "FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        if identity != ("tender_intelligence_test", "tender_dbt", False):
            raise RuntimeError("Unexpected dbt test database or role")
    executable = (
        root / ".venv-dbt" / ("Scripts/dbt.exe" if os.name == "nt" else "bin/dbt")
    )
    if not executable.is_file():
        pytest.fail(
            "Install requirements-dbt.txt in .venv-dbt before integration tests"
        )

    def run(*arguments):
        return subprocess.run(
            [
                str(executable),
                *arguments,
                "--target",
                "test",
                "--project-dir",
                str(root / "dbt"),
                "--profiles-dir",
                str(temporary),
                "--target-path",
                str(temporary / "target"),
                "--log-path",
                str(temporary / "logs"),
                "--no-use-colors",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
            env={
                **os.environ,
                "PYTHON_DOTENV_DISABLED": "1",
                "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
            },
        )

    return run, temporary / "target"


@pytest.fixture(scope="session")
def dbt_models(dbt_runner):
    run, _ = dbt_runner
    result = run("run")
    assert result.returncode == 0, result.stdout + result.stderr
