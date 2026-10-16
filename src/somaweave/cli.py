"""Command-line entry point. Argument parsing and dispatch only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from somaweave import __version__
from somaweave.domain.io import CaseValidationError, load_case


def _cmd_validate_case(args: argparse.Namespace) -> int:
    path = Path(args.case)
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 2
    try:
        case = load_case(path)
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON: {exc}", file=sys.stderr)
        return 1
    except CaseValidationError as exc:
        print(f"invalid case ({len(exc.errors)} error(s)):", file=sys.stderr)
        print(exc.pretty(), file=sys.stderr)
        return 1
    summary = {
        "case_id": case.case_id,
        "schema_version": case.schema_version,
        "assembly": str(case.assembly),
        "diagnosis": case.diagnosis.name,
        "oncotree_code": case.diagnosis.oncotree_code,
        "specimens": len(case.specimens),
        "tumor_specimens": len(case.tumor_specimens()),
        "alterations": len(case.alterations),
        "treatments": len(case.treatments),
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("valid case")
        for k, v in summary.items():
            print(f"  {k}: {v}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="somaweave", description="SomaWeave research interpretation toolkit")
    parser.add_argument("--version", action="version", version=f"somaweave {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate-case", help="Validate a case JSON file against the canonical model")
    p_val.add_argument("case", help="Path to case JSON")
    p_val.add_argument("--json", action="store_true", help="Print a JSON summary")
    p_val.set_defaults(func=_cmd_validate_case)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
