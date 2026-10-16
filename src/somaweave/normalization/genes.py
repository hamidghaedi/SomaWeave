"""Gene symbol normalization.

Symbols are upper-cased and stripped, then checked against a small built-in
table of retired HGNC symbols that still appear in reports. An external HGNC
table (``hgnc_complete_set.txt`` TSV with ``symbol`` and ``prev_symbol``
columns) can be supplied for full coverage; nothing is downloaded here.

The original symbol is always retained; an alias substitution is reported
explicitly rather than applied silently.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# Retired symbol -> current HGNC symbol. Deliberately small; the HGNC table hook
# is the route to completeness.
BUILTIN_PREVIOUS_SYMBOLS: dict[str, str] = {
    "MLL": "KMT2A",
    "MLL2": "KMT2D",
    "MLL3": "KMT2C",
    "MLL4": "KMT2B",
    "C11ORF30": "EMSY",
    "FAM123B": "AMER1",
    "WTX": "AMER1",
    "MYCL1": "MYCL",
    "PARK2": "PRKN",
    "FAM175A": "ABRAXAS1",
    "MRE11A": "MRE11",
    "H3F3A": "H3-3A",
    "HIST1H3B": "H3C2",
    "WHSC1": "NSD2",
    "WHSC1L1": "NSD3",
    "MKL1": "MRTFA",
    "GPR124": "ADGRA2",
    "C15ORF55": "NUTM1",
    "TCEB1": "ELOC",
    "FAM46C": "TENT5C",
    "SEPT9": "SEPTIN9",
    "CASC5": "KNL1",
    "RQCD1": "CNOT9",
    "PAK7": "PAK5",
    "ADPRT": "PARP1",
    "CDKN2": "CDKN2A",
    "MTS1": "CDKN2A",
}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NormalizedGeneSymbol(_Model):
    original: str = Field(description="Symbol as supplied (surrounding whitespace removed).")
    normalized: str = Field(description="Upper-cased, whitespace-stripped symbol after alias resolution.")
    alias_applied: bool = Field(default=False, description="True if a previous symbol was replaced by its current symbol.")
    alias_source: Optional[str] = Field(default=None, description="'builtin' or 'hgnc_table' when alias_applied is True.")
    notes: list[str] = Field(default_factory=list)


def load_hgnc_previous_symbols(path: str | Path, include_alias_symbols: bool = False) -> dict[str, str]:
    """Build a previous-symbol -> current-symbol map from an HGNC complete-set TSV.

    Expected columns: ``symbol``, ``prev_symbol`` (pipe-separated), and
    optionally ``alias_symbol``. Alias symbols are excluded by default because
    they are frequently ambiguous across genes; when included, any alias that
    maps to more than one current symbol is dropped and reported in the
    returned map under the key ``"__ambiguous__"`` as a comma-joined list.
    """
    mapping: dict[str, str] = {}
    ambiguous: set[str] = set()
    with Path(path).open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if reader.fieldnames is None or "symbol" not in reader.fieldnames or "prev_symbol" not in reader.fieldnames:
            raise ValueError("HGNC table must have 'symbol' and 'prev_symbol' columns")
        for row in reader:
            current = (row.get("symbol") or "").strip().upper()
            if not current:
                continue
            fields = [row.get("prev_symbol") or ""]
            if include_alias_symbols:
                fields.append(row.get("alias_symbol") or "")
            for field in fields:
                for prev in field.split("|"):
                    prev = prev.strip().upper()
                    if not prev or prev == current:
                        continue
                    if prev in mapping and mapping[prev] != current:
                        ambiguous.add(prev)
                    else:
                        mapping[prev] = current
    for prev in ambiguous:
        mapping.pop(prev, None)
    if ambiguous:
        mapping["__ambiguous__"] = ",".join(sorted(ambiguous))
    return mapping


def normalize_gene_symbol(symbol: Optional[str], hgnc_previous: Optional[dict[str, str]] = None) -> Optional[NormalizedGeneSymbol]:
    """Normalize a gene symbol; returns ``None`` when no symbol is supplied.

    Resolution order: external HGNC table (if given), then the built-in
    table. A symbol that is already current passes through unchanged.
    """
    if symbol is None:
        return None
    cleaned = "".join(symbol.split()).upper()
    notes: list[str] = []
    if not cleaned:
        return NormalizedGeneSymbol(original=symbol, normalized="", notes=["empty symbol"])
    if cleaned != symbol:
        notes.append("case/whitespace normalized")
    if hgnc_previous and cleaned in hgnc_previous and cleaned != "__ambiguous__":
        return NormalizedGeneSymbol(original=symbol, normalized=hgnc_previous[cleaned], alias_applied=True,
                                    alias_source="hgnc_table", notes=notes)
    if cleaned in BUILTIN_PREVIOUS_SYMBOLS and BUILTIN_PREVIOUS_SYMBOLS[cleaned] != cleaned:
        return NormalizedGeneSymbol(original=symbol, normalized=BUILTIN_PREVIOUS_SYMBOLS[cleaned], alias_applied=True,
                                    alias_source="builtin", notes=notes)
    return NormalizedGeneSymbol(original=symbol, normalized=cleaned, notes=notes)
