import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def retry_cli(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/retry_failed_processing.py"
    spec = importlib.util.spec_from_file_location("retry_cli_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "load_dotenv", MagicMock())
    monkeypatch.setattr(module, "connect_database", MagicMock())
    return module


@pytest.mark.parametrize(
    "arguments", [[], ["--source-run-id", "0"], ["--source-run-id", "-1"]]
)
def test_retry_cli_requires_positive_source_before_configuration(
    retry_cli, monkeypatch, arguments
):
    monkeypatch.setattr("sys.argv", ["retry_failed_processing.py", *arguments])
    with pytest.raises(SystemExit) as error:
        retry_cli.main()
    assert error.value.code == 2
    retry_cli.load_dotenv.assert_not_called()
    retry_cli.connect_database.assert_not_called()


@pytest.mark.parametrize(
    "status,code", [("succeeded", 0), ("partial", 1), ("failed", 1)]
)
def test_retry_cli_passes_source_id_and_propagates_status(
    retry_cli, monkeypatch, status, code
):
    monkeypatch.setattr(
        "sys.argv", ["retry_failed_processing.py", "--source-run-id", "123"]
    )
    connection = retry_cli.connect_database.return_value.__enter__.return_value
    connection.execute.return_value.fetchone.side_effect = [
        ("tender_intelligence", "tender_app"),
        (status,),
    ]
    retry = MagicMock(return_value=456)
    monkeypatch.setattr(retry_cli, "retry_processing", retry)
    assert retry_cli.main() == code
    retry.assert_called_once_with(connection, source_run_id=123)
