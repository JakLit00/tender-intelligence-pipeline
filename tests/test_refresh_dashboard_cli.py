import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "refresh_dashboard.py"
)


@pytest.fixture
def refresh_cli():
    spec = importlib.util.spec_from_file_location(
        "refresh_dashboard_cli_under_test",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def environment(tmp_path, monkeypatch, refresh_cli):
    project_root = tmp_path / "project"
    scripts = project_root / "scripts"
    scripts.mkdir(parents=True)

    monkeypatch.setattr(
        refresh_cli,
        "__file__",
        str(scripts / "refresh_dashboard.py"),
    )
    monkeypatch.setattr(
        refresh_cli.sys,
        "argv",
        ["refresh_dashboard.py"],
    )
    monkeypatch.setattr(refresh_cli, "load_dotenv", MagicMock())
    monkeypatch.setattr(
        refresh_cli.shutil,
        "which",
        lambda name: "/fake/node",
    )

    dbt_executable = project_root / ".venv-dbt" / (
        "Scripts/dbt.exe"
        if refresh_cli.os.name == "nt"
        else "bin/dbt"
    )
    dbt_executable.parent.mkdir(parents=True)
    dbt_executable.touch()

    destination = project_root / "dashboard/data/dashboard.json"
    destination.parent.mkdir(parents=True)
    original = b'{"previous_snapshot": true}\n'
    destination.write_bytes(original)

    app_connection = MagicMock()
    app_connection.execute.return_value.fetchone.return_value = (
        "tender_intelligence",
        "tender_app",
    )
    app_connection.__enter__.return_value = app_connection

    report_connection = MagicMock()
    report_connection.execute.return_value.fetchone.return_value = (
        "tender_intelligence",
        "tender_reporter",
    )
    report_connection.__enter__.return_value = report_connection

    monkeypatch.setattr(
        refresh_cli,
        "connect_database",
        MagicMock(return_value=app_connection),
    )
    monkeypatch.setattr(
        refresh_cli,
        "connect_reporting_database",
        MagicMock(return_value=report_connection),
    )

    ingestion = MagicMock(
        return_value=SimpleNamespace(
            incremental_run_id=30,
            history_run_ids=(31,),
        )
    )
    monkeypatch.setattr(refresh_cli, "refresh_ingestion", ingestion)

    read_snapshot = MagicMock(
        return_value={
            "scope": {"notice_count": 1},
            "summary": {"total_lot_observations": 1},
            "observations": [{"publication_number": "722762-2026"}],
        }
    )
    monkeypatch.setattr(
        refresh_cli,
        "read_dashboard_snapshot",
        read_snapshot,
    )

    candidate_content = b'{"candidate_snapshot": true}\n'

    def write_candidate(snapshot, path, *, generated_at):
        path.write_bytes(candidate_content)

    monkeypatch.setattr(
        refresh_cli,
        "write_dashboard_snapshot",
        write_candidate,
    )

    commands = MagicMock(
        return_value=subprocess.CompletedProcess([], 0)
    )
    monkeypatch.setattr(refresh_cli.subprocess, "run", commands)

    return SimpleNamespace(
        destination=destination,
        original=original,
        candidate_content=candidate_content,
        ingestion=ingestion,
        read_snapshot=read_snapshot,
        commands=commands,
    )


def assert_previous_snapshot_preserved(environment):
    assert environment.destination.read_bytes() == environment.original
    assert list(environment.destination.parent.iterdir()) == [
        environment.destination
    ]


def test_replaces_snapshot_only_after_metric_validation(
    refresh_cli,
    environment,
):
    def run_command(command, **kwargs):
        assert kwargs["check"] is True

        if any(
            str(argument).endswith("check_dashboard_metrics.mjs")
            for argument in command
        ):
            candidate = Path(command[-1])

            assert candidate != environment.destination
            assert candidate.read_bytes() == environment.candidate_content
            assert (
                environment.destination.read_bytes()
                == environment.original
            )

        return subprocess.CompletedProcess(command, 0)

    environment.commands.side_effect = run_command

    assert refresh_cli.main() == 0

    assert (
        environment.destination.read_bytes()
        == environment.candidate_content
    )
    assert environment.commands.call_count == 4
    assert list(environment.destination.parent.iterdir()) == [
        environment.destination
    ]


def test_preserves_snapshot_when_dbt_build_fails(
    refresh_cli,
    environment,
):
    def run_command(command, **kwargs):
        if "build" in command:
            raise subprocess.CalledProcessError(1, command)

        return subprocess.CompletedProcess(command, 0)

    environment.commands.side_effect = run_command

    assert refresh_cli.main() == 1

    environment.read_snapshot.assert_not_called()
    assert_previous_snapshot_preserved(environment)


def test_preserves_snapshot_when_metric_validation_fails(
    refresh_cli,
    environment,
):
    def run_command(command, **kwargs):
        if any(
            str(argument).endswith("check_dashboard_metrics.mjs")
            for argument in command
        ):
            raise subprocess.CalledProcessError(1, command)

        return subprocess.CompletedProcess(command, 0)

    environment.commands.side_effect = run_command

    assert refresh_cli.main() == 1

    environment.read_snapshot.assert_called_once()
    assert_previous_snapshot_preserved(environment)


def test_preserves_snapshot_when_ingestion_fails(
    refresh_cli,
    environment,
):
    environment.ingestion.side_effect = RuntimeError(
        "Incremental run ended with partial"
    )

    assert refresh_cli.main() == 1

    environment.read_snapshot.assert_not_called()
    assert environment.commands.call_count == 2
    assert_previous_snapshot_preserved(environment)


def test_stops_before_ingestion_when_preflight_fails(
    refresh_cli,
    environment,
):
    environment.commands.side_effect = subprocess.CalledProcessError(
        1,
        ["node", "--version"],
    )

    assert refresh_cli.main() == 1

    environment.ingestion.assert_not_called()
    assert_previous_snapshot_preserved(environment)