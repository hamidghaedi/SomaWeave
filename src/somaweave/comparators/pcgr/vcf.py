"""Lossless small-allele export, without interpretation or eligibility filtering.

Only explicit GRCh38 anchored DNA alleles are exportable. Protein-only fixtures
require a separate, owner-reviewable genomic map; no coordinates are inferred
here. One measurement is required unless specimen_id selects exactly one.
TVAF/NVAF use raw ALT/(REF+ALT), never template counts or reported_vaf. TDP/NDP
retain reported depth, otherwise REF+ALT. Missing support is omitted, not zero.
Caller FILTER codes are preserved. GT=0/1 is an explicit format placeholder,
not a measured genotype. All alleles, including held/artifact alleles, remain.
Original identifiers and positions are retained in the external export ledger.
No CNA/fusion is coerced into an SNV or a measured RNA/CNA input.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from somaweave.domain.case import Case

SMALL = {"SNV", "MNV", "insertion", "deletion", "delins"}
# PCGR 2.2.5 --help tissue classes, not disease equivalence assertions.
SITES = {"MEL": 24, "GIST": 25, "GBM": 8, "GB": 8, "LUAD": 15,
         "PAAD": 19, "COAD": 9, "SPN": 19, "PLEMESO": 22}


def tumor_site(code: str | None) -> tuple[int, str]:
    if code in SITES:
        return SITES[code], f"Explicit PCGR 2.2.5 tissue lookup for recorded OncoTree {code}; not subtype equivalence."
    return 0, f"No explicit clean tissue mapping for {code!r}; site 0 (Any)."


def read_map(path: Path, scenario: str) -> dict[str, dict[str, str]]:
    with path.open() as f:
        rows = [r for r in csv.DictReader(f, delimiter="\t") if r["scenario_id"] == scenario]
    if len({r["alteration_id"] for r in rows}) != len(rows):
        raise ValueError("duplicate alteration in genomic map")
    return {r["alteration_id"]: r for r in rows}


def allele_key(chrom: str, pos: int, ref: str, alt: str) -> str:
    chrom = chrom.removeprefix("chr")
    if chrom not in [str(n) for n in range(1, 23)] + ["X", "Y", "MT"]:
        raise ValueError(f"unsupported chromosome: {chrom}")
    if pos < 1 or not re.fullmatch("[ACGT]+", ref) or not re.fullmatch("[ACGT]+", alt) or ref == alt:
        raise ValueError("requires a positive position and distinct anchored DNA alleles")
    return f"{chrom}:{pos}:{ref}:{alt}"


def _support(support, af_tag: str, dp_tag: str) -> list[str]:
    if support is None:
        return []
    parts = []
    counts = support.ref_count is not None and support.alt_count is not None
    total = support.ref_count + support.alt_count if counts else None
    if total:
        parts.append(f"{af_tag}={support.alt_count / total:.10g}")
    depth = support.depth if support.depth is not None else total
    if depth is not None:
        parts.append(f"{dp_tag}={depth}")
    return parts


def export_vcf(case: Case, path: Path, sample: str, mapping: dict | None = None,
               specimen_id: str | None = None) -> list[dict]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", sample):
        raise ValueError("unsafe sample identifier")
    if case.assembly.value != "GRCh38":
        raise ValueError("PCGR comparator requires GRCh38; no implicit liftover")
    mapping = mapping or {}
    records, ledger, seen = [], [], set()
    for a in case.alterations:
        if a.alteration_type.value not in SMALL:
            raise ValueError(f"{a.alteration_id}: non-small alteration is not comparable through SNV/indel VCF")
        p = a.position
        m = mapping.get(a.alteration_id)
        if p:
            if p.assembly.value != "GRCh38":
                raise ValueError("allele assembly must be GRCh38")
            key = allele_key(p.chromosome, p.position, p.reference, p.alternate)
        elif m and all(m.get(k) for k in ("chrom", "pos", "ref", "alt")):
            key = allele_key(m["chrom"], int(m["pos"]), m["ref"], m["alt"])
        else:
            raise ValueError(f"{a.alteration_id}: no explicit genomic allele")
        if key in seen:
            raise ValueError("duplicate genomic allele; do not silently collapse findings")
        seen.add(key)
        measurements = [v for v in a.measurements if specimen_id is None or v.specimen_id == specimen_id]
        if len(measurements) > 1 or (specimen_id is not None and not measurements):
            raise ValueError("ambiguous or absent specimen measurement")
        measurement = measurements[0] if measurements else None
        info, filters = [], []
        if measurement:
            info = _support(measurement.tumor, "TVAF", "TDP") + _support(measurement.normal, "NVAF", "NDP")
            filters = measurement.caller_filters
        if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", v) for v in filters):
            raise ValueError("unsafe caller FILTER value")
        actual = [v for v in filters if v not in {"PASS", "."}]
        filt = ";".join(actual) if actual else ("PASS" if "PASS" in filters else ".")
        chrom, pos, ref, alt = key.split(":")
        records.append((chrom, int(pos), ref, alt, filt, ";".join(info) or "."))
        ledger.append({"alteration_id": a.alteration_id, "allele_key": key,
                       "original_position": p.model_dump(mode="json") if p else None,
                       "genomic_map": m if not p else None,
                       "caller_filters": filters, "export_filter": filt})
    if not records:
        raise ValueError("no small alleles: an empty successful comparator would be misleading")
    header = ["##fileformat=VCFv4.2", "##reference=GRCh38",
              '##SomaWeaveGT="0/1 is a format placeholder, not an inferred genotype"']
    for chrom in sorted({r[0] for r in records}, key=lambda c: (0, int(c)) if c.isdigit() else (1, c)):
        header.append(f"##contig=<ID={chrom}>")
    for tag, typ, desc in [("TVAF", "Float", "Tumor raw ALT/(REF+ALT)"), ("TDP", "Integer", "Tumor raw depth"),
                           ("NVAF", "Float", "Normal raw ALT/(REF+ALT)"), ("NDP", "Integer", "Normal raw depth")]:
        header.append(f'##INFO=<ID={tag},Number=1,Type={typ},Description="{desc}">')
    for filt in sorted({v for r in records for v in r[4].split(";") if v not in {"PASS", "."}}):
        header.append(f'##FILTER=<ID={filt},Description="Original upstream caller FILTER">')
    header += ['##FORMAT=<ID=GT,Number=1,Type=String,Description="Placeholder genotype">',
               f"#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t{sample}"]
    for chrom, pos, ref, alt, filt, info in sorted(records, key=lambda r: ((0, int(r[0])) if r[0].isdigit() else (1, r[0]), r[1:4])):
        header.append(f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\t{filt}\t{info}\tGT\t0/1")
    path.write_text("\n".join(header) + "\n")
    return ledger
