import importlib.util
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest


def git(directory: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(directory), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


@pytest.fixture
def publisher(monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))

    spec = importlib.util.spec_from_file_location(
        "dashboard_publish_script",
        scripts / "publish_dashboard.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def environment(tmp_path, publisher, monkeypatch):
    # Keep Git configuration and credentials independent of the developer machine.
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "empty-gitconfig"))
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")

    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.name", "Dashboard Test")
    git(source, "config", "user.email", "dashboard@example.invalid")
    (source / "README.md").write_text("Test project", encoding="utf-8")
    git(source, "add", "README.md")
    git(source, "commit", "-m", "test: initialize source")

    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare")

    archive_path = tmp_path / "dashboard.zip"

    def write_package(marker):
        with ZipFile(archive_path, "w") as archive:
            for name in publisher.DASHBOARD_FILES:
                archive.writestr(name, marker)
            archive.writestr(".nojekyll", "")

    write_package("first snapshot")
    monkeypatch.setattr(publisher, "REPOSITORY_URL", str(remote))
    monkeypatch.setattr(
        publisher,
        "build_dashboard",
        lambda project_root: archive_path,
    )

    return source, remote, write_package


def test_dry_run_does_not_create_remote_branch(publisher, environment):
    source, remote, _ = environment

    assert publisher.publish_dashboard(source) is True

    assert git(remote, "for-each-ref", "--format=%(refname)") == ""
    assert git(source, "branch", "--show-current") == "main"
    assert git(source, "status", "--porcelain") == ""


def test_publish_creates_only_dashboard_files(publisher, environment):
    source, remote, _ = environment

    assert publisher.publish_dashboard(source, publish=True) is True

    files = set(git(remote, "ls-tree", "-r", "--name-only", "gh-pages").splitlines())
    assert files == {*publisher.DASHBOARD_FILES, ".nojekyll"}
    assert git(remote, "show", "gh-pages:data/dashboard.json") == "first snapshot"
    assert git(source, "branch", "--show-current") == "main"
    assert git(source, "status", "--porcelain") == ""


def test_update_preserves_history_and_skips_identical_package(publisher, environment):
    source, remote, write_package = environment

    publisher.publish_dashboard(source, publish=True)
    first_commit = git(remote, "rev-parse", "gh-pages")

    assert publisher.publish_dashboard(source, publish=True) is False
    assert git(remote, "rev-parse", "gh-pages") == first_commit

    write_package("second snapshot")
    assert publisher.publish_dashboard(source, publish=True) is True

    assert git(remote, "rev-parse", "gh-pages^") == first_commit
    assert git(remote, "show", "gh-pages:data/dashboard.json") == "second snapshot"


def test_dirty_source_prevents_publication(publisher, environment):
    source, remote, _ = environment
    (source / "README.md").write_text("Uncommitted change", encoding="utf-8")

    with pytest.raises(RuntimeError, match="local changes"):
        publisher.publish_dashboard(source, publish=True)

    assert git(remote, "for-each-ref", "--format=%(refname)") == ""
