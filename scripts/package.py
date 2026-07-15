"""Package the workbench into a single-folder PyInstaller distribution."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "backend" / "src" / "data_workbench" / "static"
ENTRYPOINT = ROOT / "backend" / "src" / "data_workbench" / "cli.py"


def main() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_frontend.py")], check=True
    )
    if not STATIC.is_dir():
        raise SystemExit("frontend assets missing; build_frontend.py failed")
    separator = ";" if os.name == "nt" else ":"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--name",
            "data-workbench",
            "--add-data",
            f"{STATIC}{separator}data_workbench/static",
            "--collect-all",
            "duckdb",
            str(ENTRYPOINT),
        ],
        check=True,
        cwd=ROOT,
    )
    print(f"packaged distribution in {ROOT / 'dist' / 'data-workbench'}")


if __name__ == "__main__":
    main()
