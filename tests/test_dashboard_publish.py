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


def test_dry_run_does_not_update_existing_branch(publisher, environment):
    source, remote, write_package = environment
    publisher.publish_dashboard(source, publish=True)
    original = git(remote, "rev-parse", "gh-pages")
    write_package("new snapshot")
    assert publisher.publish_dashboard(source) is True
    assert git(remote, "rev-parse", "gh-pages") == original


@pytest.mark.parametrize("extra", ["../escape.txt", "private.txt", "index.html"])
def test_invalid_archive_never_updates_remote(publisher, environment, extra):
    source, remote, _ = environment
    publisher.publish_dashboard(source, publish=True)
    original = git(remote, "rev-parse", "gh-pages")
    with ZipFile(publisher.build_dashboard(source), "a") as archive:
        if extra == "index.html":
            with pytest.warns(UserWarning, match="Duplicate name"):
                archive.writestr(extra, "duplicate")
        else:
            archive.writestr(extra, "unexpected")
    with pytest.raises(ValueError, match="archive contents"):
        publisher.publish_dashboard(source, publish=True)
    assert git(remote, "rev-parse", "gh-pages") == original
    assert not (source.parent / "escape.txt").exists()


def test_unexpected_tracked_file_prevents_update(publisher, environment, tmp_path):
    source, remote, _ = environment
    publisher.publish_dashboard(source, publish=True)
    checkout = tmp_path / "other-checkout"
    git(tmp_path, "clone", "--branch", "gh-pages", str(remote), str(checkout))
    git(checkout, "config", "user.name", "Dashboard Test")
    git(checkout, "config", "user.email", "dashboard@example.invalid")
    (checkout / "private.txt").write_text("not an allowed asset", encoding="utf-8")
    git(checkout, "add", "private.txt")
    git(checkout, "commit", "-m", "test: unexpected asset")
    git(checkout, "push", "origin", "gh-pages")
    original = git(remote, "rev-parse", "gh-pages")
    with pytest.raises(ValueError, match="Unexpected files"):
        publisher.publish_dashboard(source, publish=True)
    assert git(remote, "rev-parse", "gh-pages") == original


def test_concurrent_update_is_rejected_without_rewriting_history(
    publisher, environment, monkeypatch
):
    source, remote, write_package = environment
    publisher.publish_dashboard(source, publish=True)
    first = git(remote, "rev-parse", "gh-pages")
    git(remote, "config", "user.name", "Dashboard Test")
    git(remote, "config", "user.email", "dashboard@example.invalid")
    tree = git(remote, "rev-parse", "gh-pages^{tree}")
    concurrent = git(
        remote, "commit-tree", tree, "-p", first, "-m", "concurrent update"
    )
    original_run_git = publisher.run_git

    def update_before_push(directory, *arguments):
        if arguments[0] == "push":
            git(remote, "update-ref", "refs/heads/gh-pages", concurrent, first)
        return original_run_git(directory, *arguments)

    monkeypatch.setattr(publisher, "run_git", update_before_push)
    write_package("another snapshot")
    with pytest.raises(publisher.GitCommandError, match="Remote branch changed"):
        publisher.publish_dashboard(source, publish=True)
    assert git(remote, "rev-parse", "gh-pages") == concurrent
    assert git(remote, "rev-parse", "gh-pages^") == first
    assert git(source, "status", "--porcelain") == ""


@pytest.mark.parametrize(
    "message, expected",
    [
        (
            "Authentication failed for https://user:synthetic-password@example.invalid/repo",
            "credential",
        ),
        ("remote: denied; Authorization: Bearer synthetic-token", "permissions"),
        (
            "Could not resolve host https://example.invalid/?token=synthetic-token",
            "network",
        ),
    ],
)
def test_git_diagnostic_does_not_echo_credentials(
    publisher, tmp_path, monkeypatch, message, expected
):
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(128, ["git", "push"], stderr=message)

    monkeypatch.setattr(publisher.subprocess, "run", fail)
    with pytest.raises(publisher.GitCommandError) as caught:
        publisher.run_git(tmp_path, "push", "origin", "HEAD:refs/heads/gh-pages")
    diagnostic = str(caught.value)
    assert "Git push failed" in diagnostic
    assert expected in diagnostic
    assert "synthetic-" not in diagnostic
    assert "example.invalid" not in diagnostic


def test_git_timeout_reports_stage_without_command_details(
    publisher, tmp_path, monkeypatch
):
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            ["git", "https://user:synthetic-password@example.invalid"], 120
        )

    monkeypatch.setattr(publisher.subprocess, "run", fail)
    with pytest.raises(
        publisher.GitCommandError, match="Git fetch timed out"
    ) as caught:
        publisher.run_git(tmp_path, "fetch", "origin")
    assert "synthetic-password" not in str(caught.value)


def test_build_failure_never_contacts_remote(publisher, environment, monkeypatch):
    source, remote, _ = environment
    original_git = publisher.run_git
    operations = []

    def track(directory, *arguments):
        operations.append(arguments[0])
        return original_git(directory, *arguments)

    def fail_build(root):
        raise ValueError("invalid dashboard contract")

    monkeypatch.setattr(publisher, "run_git", track)
    monkeypatch.setattr(publisher, "build_dashboard", fail_build)
    with pytest.raises(ValueError, match="contract"):
        publisher.publish_dashboard(source, publish=True)
    assert not {"ls-remote", "fetch", "push"}.intersection(operations)
    assert git(remote, "for-each-ref", "--format=%(refname)") == ""
