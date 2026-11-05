"""Check application-role connectivity to PostgreSQL."""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def required_env(name: str) -> str:
    """Read a required setting without exposing its value in errors."""
    value = os.getenv(name)

    if value is None or value == "":
        raise ValueError(f"Missing environment variable: {name}")

    return value


def main() -> None:
    # Explicit paths avoid loading a different project's .env.
    # Existing environment variables take precedence over local defaults.
    load_dotenv(
        PROJECT_ROOT / ".env",
        override=False,
        interpolate=False,
    )

    with psycopg.connect(
        host=required_env("APP_DB_HOST"),
        port=int(required_env("APP_DB_PORT")),
        dbname=required_env("APP_DB_NAME"),
        user=required_env("APP_DB_USER"),
        password=required_env("APP_DB_PASSWORD"),
        connect_timeout=10,
        application_name="tender-intelligence-connection-check",
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    current_database(),
                    current_user,
                    rolsuper
                FROM pg_roles
                WHERE rolname = current_user
                """
            )
            result = cursor.fetchone()

    if result is None:
        raise RuntimeError("The connection check returned no role information")

    database, user, is_superuser = result

    if is_superuser:
        raise RuntimeError("The application must not connect as a superuser")

    print(f"Database: {database}")
    print(f"User: {user}")
    print(f"Superuser: {is_superuser}")
    print("Connection check passed.")


if __name__ == "__main__":
    main()
