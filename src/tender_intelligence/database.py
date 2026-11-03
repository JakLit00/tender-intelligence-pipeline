import os

import psycopg


def _required_env(name: str) -> str:
    value = os.environ.get(name)

    if value is None or not value.strip():
        raise ValueError(f"Missing environment variable: {name}")

    return value


def connect_database() -> psycopg.Connection:
    """Open an application connection using environment variables."""
    host = _required_env("APP_DB_HOST")
    port_raw = _required_env("APP_DB_PORT")
    dbname = _required_env("APP_DB_NAME")
    user = _required_env("APP_DB_USER")
    password = _required_env("APP_DB_PASSWORD")

    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError("APP_DB_PORT must be an integer") from exc

    if not 1 <= port <= 65535:
        raise ValueError("APP_DB_PORT must be between 1 and 65535")

    return psycopg.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        connect_timeout=10,
        application_name="tender-intelligence-pipeline",
        # Writers must explicitly group related changes with conn.transaction().
        autocommit=True,
    )