"""Explicit external-comparator commands, independent of benchmark signing."""
import argparse
import json
from pathlib import Path

from somaweave.domain.io import load_case
from .vcf import export_vcf, read_map, tumor_site
from .run import run
from .parser import parse_annotations, read_filters, compare_retention


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export")
    exp.add_argument("--case", required=True, type=Path)
    exp.add_argument("--out", required=True, type=Path)
    exp.add_argument("--sample", required=True)
    exp.add_argument("--map", type=Path)
    exp.add_argument("--scenario")
    exp.add_argument("--specimen-id")
    execute = sub.add_parser("run")
    execute.add_argument("config", type=Path)
    parse = sub.add_parser("parse")
    parse.add_argument("--table", type=Path, required=True)
    parse.add_argument("--ledger", type=Path, required=True)
    parse.add_argument("--native-vcf", type=Path)
    parse.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "run":
        return run(args.config)
    if args.command == "export":
        case = load_case(args.case)
        if args.map and not args.scenario:
            parser.error("--map requires --scenario")
        mapping = read_map(args.map, args.scenario) if args.map else None
        ledger = export_vcf(case, args.out, args.sample, mapping, args.specimen_id)
        site, note = tumor_site(case.diagnosis.oncotree_code)
        args.out.with_suffix(".export.json").write_text(json.dumps({"alleles": ledger, "tumor_site": site,
            "tumor_site_note": note, "genotype": "0/1 format placeholder; not inferred"}, indent=2) + "\n")
    else:
        ledger = json.loads(args.ledger.read_text())["alleles"]
        annotations = parse_annotations(args.table)
        filters = read_filters(args.native_vcf) if args.native_vcf else {}
        args.out.write_text(json.dumps(compare_retention(ledger, annotations, filters), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
