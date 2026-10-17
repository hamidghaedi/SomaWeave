#!/usr/bin/env python
"""Repository benchmark command; reusable replay logic lives in workflows."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from somaweave.workflows.benchmark import evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, default=ROOT / "tests/benchmark")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--allow-draft", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--results-root")
    parser.add_argument("--cache-root")
    parser.add_argument("--providers-config")
    parser.add_argument("--run-id-prefix")
    args = vars(parser.parse_args())
    try:
        return evaluate(**args)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
