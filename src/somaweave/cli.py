"""Command-line entry point. Argument parsing and dispatch only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from somaweave import __version__
from somaweave.domain.io import CaseValidationError, load_case
from somaweave.workflows import RootsError
from somaweave.workflows import run as run_interpret_case


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


def _cmd_interpret_case(args: argparse.Namespace) -> int:
    path = Path(args.case)
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 2
    if args.providers_config and not Path(args.providers_config).exists():
        print(f"error: providers config {args.providers_config} does not exist", file=sys.stderr)
        return 2
    try:
        result = run_interpret_case(
            path, results_root=args.results_root, work_root=args.work_root, cache_root=args.cache_root,
            providers_config=args.providers_config, offline=args.offline, run_id=args.run_id,
        )
    except RootsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON: {exc}", file=sys.stderr)
        return 1
    except CaseValidationError as exc:
        print(f"invalid case ({len(exc.errors)} error(s)):", file=sys.stderr)
        print(exc.pretty(), file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report and exit 1
        print(f"error: run failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"run {result.run_id} complete: {result.run_dir}")
    print(f"  mode: {'offline' if result.offline else 'online'}; source statuses: {result.status_counts}")
    for f in result.findings_summary:
        print(f"  {f['alteration_id']}: analytical={f['analytical']} oncogenicity={f['oncogenicity']} "
              f"tier={f['actionability_tier']} relevance={f['relevance']}")
    print(f"  report: {result.report_markdown_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="somaweave", description="SomaWeave research interpretation toolkit")
    parser.add_argument("--version", action="version", version=f"somaweave {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate-case", help="Validate a case JSON file against the canonical model")
    p_val.add_argument("case", help="Path to case JSON")
    p_val.add_argument("--json", action="store_true", help="Print a JSON summary")
    p_val.set_defaults(func=_cmd_validate_case)

    p_int = sub.add_parser("interpret-case", help="Run the full interpretation workflow for a case JSON file")
    p_int.add_argument("case", help="Path to case JSON")
    p_int.add_argument("--results-root", default=None, help="Results root (default: SOMAWEAVE_RESULTS_ROOT)")
    p_int.add_argument("--work-root", default=None, help="Work root (default: SOMAWEAVE_WORK_ROOT)")
    p_int.add_argument("--cache-root", default=None, help="Payload cache root (default: SOMAWEAVE_CACHE_ROOT)")
    p_int.add_argument("--providers-config", default=None, help="Providers JSON (default: configs/providers.example.json)")
    p_int.add_argument("--offline", action="store_true", help="Do not contact any source; every query is recorded as not_queried")
    p_int.add_argument("--run-id", default=None, help="Run id (default: UTC timestamp + input hash)")
    p_int.set_defaults(func=_cmd_interpret_case)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
