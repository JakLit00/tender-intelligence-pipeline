import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

logger = logging.getLogger(__name__)

DASHBOARD_FILES = (
    "index.html",
    "styles.css",
    "app.js",
    "analytics.mjs",
    "contract.mjs",
    "data/dashboard.json",
)


def build_dashboard(project_root: Path) -> Path:
    project_root = project_root.resolve()
    source = project_root / "dashboard"
    validator = project_root / "scripts/check_dashboard_metrics.mjs"
    destination = project_root / "dist/dashboard.zip"

    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js was not found in PATH")

    if not validator.is_file():
        raise FileNotFoundError(f"Missing metric validator: {validator}")

    for name in DASHBOARD_FILES:
        path = source / name
        if not path.is_file():
            raise FileNotFoundError(f"Missing dashboard file: {name}")
        if not path.resolve().is_relative_to(source.resolve()):
            raise ValueError(f"Dashboard file points outside its directory: {name}")

    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=".dashboard-build-",
        dir=destination.parent,
    ) as temporary_directory:
        temporary_root = Path(temporary_directory)
        site = temporary_root / "site"
        site.mkdir()

        # Copy only explicitly selected public assets, never the project tree.
        for name in DASHBOARD_FILES:
            target = site / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, target)

        (site / ".nojekyll").touch()

        # Validate the copied snapshot that will actually enter the archive.
        # The validator imports analytics.mjs relative to its own location.
        checks = temporary_root / "scripts"
        checks.mkdir()
        copied_dashboard = temporary_root / "dashboard"
        copied_dashboard.mkdir()
        for module in ("analytics.mjs", "contract.mjs"):
            shutil.copyfile(site / module, copied_dashboard / module)
        copied_validator = checks / validator.name
        shutil.copyfile(validator, copied_validator)

        subprocess.run(
            [node, str(copied_validator), str(site / "data/dashboard.json")],
            cwd=temporary_root,
            check=True,
            timeout=60,
        )

        candidate = temporary_root / "dashboard.zip"
        with ZipFile(candidate, "w", compression=ZIP_DEFLATED) as archive:
            for name in (*DASHBOARD_FILES, ".nojekyll"):
                archive.write(site / name, arcname=name)

        # Preserve the previous archive if copying or validation fails.
        os.replace(candidate, destination)

    return destination


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    project_root = Path(__file__).resolve().parents[1]

    try:
        destination = build_dashboard(project_root)
    except Exception:
        logger.exception("Dashboard package build failed")
        return 1

    print(f"Local dashboard package created: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
