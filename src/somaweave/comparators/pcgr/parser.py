"""Parse PCGR native assertions; missing output never becomes a negative call.

Exact GRCh38 anchored allele keys only. Multiple transcript rows are preserved.
Absent rows have an unknown reason unless a native VCF FILTER supplies one.
PCGR does not assess SomaWeave's read/template analytical reliability axis.
"""
from __future__ import annotations

import csv
import gzip
from pathlib import Path
import re

from .vcf import allele_key


def _open(path: Path):
    return gzip.open(path, "rt") if path.suffix == ".gz" else path.open()


def _key(row: dict) -> str:
    if all(row.get(k) for k in ("CHROM", "POS", "REF", "ALT")):
        return allele_key(row["CHROM"], int(row["POS"]), row["REF"], row["ALT"])
    if row.get("VAR_ID"):
        c, p, r, a = row["VAR_ID"].split("_", 3)
        return allele_key(c, int(p), r, a)
    match = re.fullmatch(r"(?:chr)?([^:]+):g\.(\d+)([ACGT]+)>([ACGT]+)", row.get("GENOMIC_CHANGE", ""))
    if not match:
        raise ValueError("unsupported PCGR genomic identity; never join by protein/gene")
    return allele_key(match[1], int(match[2]), match[3], match[4])


def parse_annotations(path: Path) -> dict[str, list[dict]]:
    with _open(path) as f:
        reader = csv.DictReader((line for line in f if not line.startswith("##")), delimiter="\t")
        required = {"CONSEQUENCE", "ONCOGENICITY", "ONCOGENICITY_CODE", "ACTIONABILITY_TIER"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("not the native PCGR SNV/indel report annotation table")
        found: dict[str, list[dict]] = {}
        for row in reader:
            key = _key(row)
            # Source column names and values are deliberately retained verbatim.
            native = {k: v for k, v in row.items() if k in required or k in {
                "GENOMIC_CHANGE", "SYMBOL", "ALTERATION", "PROTEIN_CHANGE", "MUTATION_HOTSPOT",
                "ACTIONABILITY_FRAMEWORK", "HGVSc", "HGVSp", "MANE_SELECT",
                "MUTATION_HOTSPOT_CANCERTYPE", "CLINVAR_CLASSIFICATION", "CALL_CONFIDENCE",
                "FILTER"} or k.lower().startswith("gnomad")}
            found.setdefault(key, []).append(native)
        return found


def read_filters(path: Path) -> dict[str, str]:
    filters = {}
    with _open(path) as f:
        for line in f:
            if line.startswith("#"):
                continue
            fields = line.rstrip().split("\t")
            if len(fields) < 8:
                raise ValueError("malformed native VCF")
            key = allele_key(fields[0], int(fields[1]), fields[3], fields[4])
            filters[key] = fields[6]
    return filters


def compare_retention(ledger: list[dict], annotations: dict, filters: dict | None = None) -> list[dict]:
    result = []
    for item in ledger:
        key = item["allele_key"]
        rows = annotations.get(key, [])
        native_filter = (filters or {}).get(key)
        result.append({"alteration_id": item["alteration_id"], "allele_key": key,
                       "retained": bool(rows), "native_filter": native_filter,
                       "filter_reason": native_filter if native_filter not in {None, "PASS", "."} else
                       (None if rows else "Not retained; native reason not exposed in supplied files"),
                       "technical_axis": "not assessed by PCGR", "native_rows": rows})
    return result
