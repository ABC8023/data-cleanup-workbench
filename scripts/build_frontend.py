"""Build the React frontend into the backend's packaged static assets."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
STATIC = ROOT / "backend" / "src" / "data_workbench" / "static"


def main() -> None:
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit("npm is required to build the frontend")
    subprocess.run([npm, "--prefix", str(FRONTEND), "ci"], check=True)
    subprocess.run([npm, "--prefix", str(FRONTEND), "run", "build"], check=True)
    if STATIC.exists():
        shutil.rmtree(STATIC)
    shutil.copytree(FRONTEND / "dist", STATIC)
    print(f"frontend assets staged in {STATIC}")


if __name__ == "__main__":
    sys.exit(main())
