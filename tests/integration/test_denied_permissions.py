import psycopg
import pytest


@pytest.mark.parametrize(
    "role,password,statement",
    [
        ("tender_app", "local_test_app_password", "TRUNCATE raw.notices"),
        (
            "tender_app",
            "local_test_app_password",
            "CREATE TABLE staging.permission_probe (id int)",
        ),
        ("tender_app", "local_test_app_password", "DROP TABLE staging.notice_lots"),
        (
            "tender_dbt",
            "local_test_dbt_password",
            "UPDATE raw.notices SET last_error=NULL WHERE false",
        ),
        (
            "tender_dbt",
            "local_test_dbt_password",
            "DELETE FROM staging.notice_lots WHERE false",
        ),
        (
            "tender_reporter",
            "local_test_report_password",
            "SELECT xml_content FROM raw.notices LIMIT 0",
        ),
        (
            "tender_reporter",
            "local_test_report_password",
            "SELECT * FROM staging.notices LIMIT 0",
        ),
        (
            "tender_reporter",
            "local_test_report_password",
            "CREATE TABLE analytics.permission_probe (id int)",
        ),
        (
            "tender_reporter",
            "local_test_report_password",
            "UPDATE raw.notices SET last_error=NULL WHERE false",
        ),
        ("tender_app", "local_test_app_password", "SET ROLE tender_test_admin"),
        ("tender_dbt", "local_test_dbt_password", "SET ROLE tender_test_admin"),
        ("tender_reporter", "local_test_report_password", "SET ROLE tender_test_admin"),
    ],
)
def test_role_cannot_exceed_its_permissions(dbt_models, role, password, statement):
    with psycopg.connect(
        host="127.0.0.1",
        port=5435,
        dbname="tender_intelligence_test",
        user=role,
        password=password,
        connect_timeout=5,
        autocommit=True,
    ) as connection:
        assert connection.execute(
            "SELECT current_database(),current_user,rolsuper FROM pg_roles WHERE rolname=current_user"
        ).fetchone() == ("tender_intelligence_test", role, False)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with connection.transaction(force_rollback=True):
                connection.execute(statement)


def test_reporter_has_select_without_write_privileges_on_analytics(dbt_models):
    with psycopg.connect(
        host="127.0.0.1",
        port=5435,
        dbname="tender_intelligence_test",
        user="tender_reporter",
        password="local_test_report_password",
        connect_timeout=5,
        autocommit=True,
    ) as connection:
        assert connection.execute(
            "SELECT current_database(),current_user"
        ).fetchone() == ("tender_intelligence_test", "tender_reporter")
        rows = connection.execute(
            """
            SELECT table_name,
                   has_table_privilege(current_user, format('%I.%I', table_schema, table_name), 'SELECT'),
                   has_table_privilege(current_user, format('%I.%I', table_schema, table_name), 'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
            FROM information_schema.tables WHERE table_schema='analytics'
            """
        ).fetchall()
        assert any(row[0] == "mart_lot_deadline_changes" for row in rows)
        assert all(row[1:] == (True, False) for row in rows)
