#!/usr/bin/env python3
"""Reproduce the GitHub Actions pytest job locally, exactly.

Builds a throwaway venv, installs the package the same way
.github/workflows/pytest.yml does (pip install -e ".[dev]"), and runs the
same bare `pytest` invocation from the repo root. Catches drift between
"works with python -m pytest on my machine" and "works in CI" before you
push -- see .github/workflows/pytest.yml for the source of truth this
mirrors.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT / ".ci-check-venv"


def bin_path(name: str) -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / f"{name}.exe"
    return VENV_DIR / "bin" / name


def run(cmd: list[str]) -> None:
    print(f"+ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=ROOT)


def main() -> int:
    if VENV_DIR.exists():
        shutil.rmtree(VENV_DIR)

    print(f"Creating clean venv at {VENV_DIR} ...")
    venv.create(VENV_DIR, with_pip=True)

    python = str(bin_path("python"))
    pytest = str(bin_path("pytest"))

    try:
        run([python, "-m", "pip", "install", "--upgrade", "pip"])
        run([python, "-m", "pip", "install", "-e", ".[dev]"])
        run([pytest])
    except subprocess.CalledProcessError as exc:
        print(f"\nCI check FAILED (exit {exc.returncode})")
        return exc.returncode
    finally:
        shutil.rmtree(VENV_DIR, ignore_errors=True)

    print("\nCI check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
