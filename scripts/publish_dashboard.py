import argparse
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile

from build_dashboard import DASHBOARD_FILES, build_dashboard

logger = logging.getLogger(__name__)

REPOSITORY_URL = "https://github.com/JakLit00/tender-intelligence-pipeline.git"
PUBLISH_BRANCH = "gh-pages"


class GitCommandError(RuntimeError):
    pass


def _git_failure_reason(stderr: str) -> str:
    message = stderr.lower()
    if any(
        word in message for word in ("non-fast-forward", "fetch first", "stale info")
    ):
        return "Remote branch changed; review the latest dashboard and retry"
    if any(
        word in message
        for word in (
            "authentication",
            "permission denied",
            "403",
            "could not read username",
            "repository not found",
        )
    ):
        return "Check repository access and Git credential configuration"
    if any(
        word in message
        for word in ("resolve host", "connect", "timed out", "ssl", "certificate")
    ):
        return "Check network connectivity and TLS configuration"
    if (
        "user.name" in message
        or "user.email" in message
        or "identity unknown" in message
    ):
        return "Configure Git user.name and user.email"
    return "Check repository state, Git configuration and remote permissions"


def run_git(directory: Path, *arguments: str) -> str:
    operation = arguments[0]
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as error:
        # Classify stderr without copying URLs, headers or arbitrary credentials.
        reason = _git_failure_reason(error.stderr or "")
        if operation == "config" and arguments[1:2] in (
            ("user.name",),
            ("user.email",),
        ):
            reason = "Configure Git user.name and user.email"
        raise GitCommandError(
            f"Git {operation} failed (exit {error.returncode}): {reason}"
        ) from None
    except subprocess.TimeoutExpired:
        raise GitCommandError(f"Git {operation} timed out after 120 seconds") from None
    return result.stdout.strip()


def publish_dashboard(project_root: Path, *, publish: bool = False) -> bool:
    project_root = project_root.resolve()

    if shutil.which("git") is None:
        raise RuntimeError("Git was not found in PATH")

    if run_git(project_root, "status", "--porcelain"):
        raise RuntimeError("Commit or resolve local changes before publishing")

    name = run_git(project_root, "config", "user.name")
    email = run_git(project_root, "config", "user.email")
    if not name or not email:
        raise RuntimeError("Configure Git user.name and user.email")

    archive_path = build_dashboard(project_root)
    expected_files = {*DASHBOARD_FILES, ".nojekyll"}

    with tempfile.TemporaryDirectory(prefix="tender-dashboard-publish-") as directory:
        checkout = Path(directory)
        run_git(checkout, "init")
        run_git(checkout, "config", "user.name", name)
        run_git(checkout, "config", "user.email", email)
        run_git(checkout, "remote", "add", "origin", REPOSITORY_URL)

        reference = f"refs/heads/{PUBLISH_BRANCH}"
        existing = run_git(checkout, "ls-remote", "--heads", "origin", reference)

        if existing:
            run_git(checkout, "fetch", "--depth=1", "origin", reference)
            run_git(checkout, "checkout", "-b", PUBLISH_BRANCH, "FETCH_HEAD")

            tracked = set(run_git(checkout, "ls-files", "-z").rstrip("\0").split("\0"))
            unexpected = tracked - expected_files
            if unexpected:
                raise ValueError(
                    "Unexpected files on publishing branch: "
                    + ", ".join(sorted(unexpected))
                )

            run_git(checkout, "rm", "-r", "--ignore-unmatch", ".")
        else:
            run_git(checkout, "checkout", "--orphan", PUBLISH_BRANCH)

        with ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(names) != len(expected_files) or set(names) != expected_files:
                raise ValueError("Unexpected dashboard archive contents")

            # Explicit destinations prevent arbitrary archive paths from being used.
            for relative_path in sorted(expected_files):
                target = checkout / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(relative_path))

        run_git(checkout, "add", "--all")

        if not run_git(checkout, "diff", "--cached", "--name-only"):
            logger.info("Published dashboard already matches the local package")
            return False

        source_commit = run_git(project_root, "rev-parse", "--short", "HEAD")
        run_git(
            checkout,
            "commit",
            "-m",
            f"deploy: update dashboard from {source_commit}",
        )

        arguments = ["push"]
        if not publish:
            arguments.append("--dry-run")
        arguments.extend(["origin", f"HEAD:{reference}"])

        # A normal push rejects concurrent updates instead of overwriting history.
        run_git(checkout, *arguments)

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build and publish the dashboard to the gh-pages branch."
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Push the dashboard; otherwise perform a dry run.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        changed = publish_dashboard(
            Path(__file__).resolve().parents[1],
            publish=args.publish,
        )
    except GitCommandError as error:
        logger.error("%s", error)
        return 1
    except subprocess.CalledProcessError as error:
        logger.error("Dashboard validation failed (exit %s)", error.returncode)
        return 1
    except Exception:
        logger.exception("Dashboard publication failed")
        return 1

    if changed:
        logger.info(
            "Dashboard pushed to gh-pages"
            if args.publish
            else "Publication dry run completed"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
