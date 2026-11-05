import psycopg


def test_application_role_has_required_table_permissions(
    db_connection: psycopg.Connection,
) -> None:
    permissions = {
        "raw.notices": ("SELECT", "INSERT", "UPDATE"),
        "staging.notices": ("SELECT", "INSERT", "UPDATE"),
        "staging.notice_lots": ("SELECT", "INSERT", "UPDATE", "DELETE"),
    }

    for table_name, privileges in permissions.items():
        for privilege in privileges:
            row = db_connection.execute(
                """
                SELECT has_table_privilege(current_user, %s, %s)
                """,
                (table_name, privilege),
            ).fetchone()

            assert row == (True,), f"Missing {privilege} permission on {table_name}"
