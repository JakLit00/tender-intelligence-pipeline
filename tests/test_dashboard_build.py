import importlib.util
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest


@pytest.fixture
def builder():
    path = Path(__file__).resolve().parents[1] / "scripts/build_dashboard.py"
    spec = importlib.util.spec_from_file_location("dashboard_build_script", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def project(tmp_path, builder, monkeypatch):
    for name in builder.DASHBOARD_FILES:
        path = tmp_path / "dashboard" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "check_dashboard_metrics.mjs").write_text("", encoding="utf-8")
    monkeypatch.setattr(builder.shutil, "which", lambda name: "/tools/node")
    return tmp_path


def test_package_contains_only_selected_files(builder, project, monkeypatch):
    (project / ".env").write_text("SECRET=private", encoding="utf-8")
    (project / "dashboard/private.txt").write_text("private", encoding="utf-8")
    monkeypatch.setattr(builder.subprocess, "run", lambda *args, **kwargs: None)

    destination = builder.build_dashboard(project)

    with ZipFile(destination) as archive:
        assert set(archive.namelist()) == {
            *builder.DASHBOARD_FILES,
            ".nojekyll",
        }
        assert archive.read(".nojekyll") == b""


def test_validation_failure_preserves_previous_package(builder, project, monkeypatch):
    destination = project / "dist/dashboard.zip"
    destination.parent.mkdir()
    destination.write_bytes(b"previous package")

    def fail_validation(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "node")

    monkeypatch.setattr(builder.subprocess, "run", fail_validation)

    with pytest.raises(subprocess.CalledProcessError):
        builder.build_dashboard(project)

    assert destination.read_bytes() == b"previous package"
    assert list(destination.parent.iterdir()) == [destination]


def test_missing_snapshot_prevents_package_creation(builder, project):
    (project / "dashboard/data/dashboard.json").unlink()

    with pytest.raises(FileNotFoundError, match="data/dashboard.json"):
        builder.build_dashboard(project)

    assert not (project / "dist/dashboard.zip").exists()


def test_validator_receives_copied_snapshot(builder, project, monkeypatch):
    original = project / "dashboard/data/dashboard.json"
    original.write_text('{"snapshot": "original"}', encoding="utf-8")

    def check_snapshot(command, **kwargs):
        copied = Path(command[2])
        original.write_text('{"snapshot": "changed"}', encoding="utf-8")
        assert copied != original
        assert copied.read_text(encoding="utf-8") == '{"snapshot": "original"}'
        assert kwargs["check"] is True
        assert kwargs["timeout"] == 60

    monkeypatch.setattr(builder.subprocess, "run", check_snapshot)

    destination = builder.build_dashboard(project)

    with ZipFile(destination) as archive:
        assert archive.read("data/dashboard.json") == b'{"snapshot": "original"}'
