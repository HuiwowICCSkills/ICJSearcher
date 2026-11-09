#!/usr/bin/env python3
"""Command-line entry point for ICJSearcher."""

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from skillkit import run_cli  # noqa: E402
import icj_adapter as adapter  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(run_cli(adapter))
