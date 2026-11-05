import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-t", "--target", choices=("dev", "test"), default="dev")
    args, dbt_arguments = parser.parse_known_args()

    if not dbt_arguments:
        raise ValueError("Provide a dbt command, for example: debug")

    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(
        project_root / ".env",
        override=False,
        interpolate=False,
    )

    if args.target == "test":
        required_variables = ("DBT_TEST_DB_PASSWORD",)
    else:
        required_variables = (
            "APP_DB_HOST",
            "APP_DB_PORT",
            "APP_DB_NAME",
            "DBT_DB_PASSWORD",
        )

    for name in required_variables:
        if not os.environ.get(name, "").strip():
            raise ValueError(f"Missing environment variable: {name}")

    if os.name == "nt":
        executable = project_root / ".venv-dbt" / "Scripts" / "dbt.exe"
    else:
        executable = project_root / ".venv-dbt" / "bin" / "dbt"

    if not executable.is_file():
        raise FileNotFoundError("dbt executable not found in .venv-dbt")

    result = subprocess.run(
        [
            str(executable),
            *dbt_arguments,
            "--target",
            args.target,
            "--project-dir",
            str(project_root / "dbt"),
            "--profiles-dir",
            str(project_root / "dbt"),
        ],
        cwd=project_root,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())