"""Alteration-class applicability of evidence records.

A knowledge-base record describes a *molecular profile* (an exact variant,
a codon, "truncating mutations", a fusion, an expression state, a copy-number
state, or simply "GENE mutation"). A record retrieved at the gene tier is
only usable for the case alteration when its profile class can be produced by
that alteration. A fusion or over-expression record says nothing about a
missense SNV in the same gene, and a record about a *different* specific
variant (EGFR L858R) says nothing about EGFR P1033L. Capping such records at
tier III does not make them applicable; they are excluded from the
oncogenicity and actionability pools and kept as context.

The classifier works on the source's variant description text (CIViC
molecular-profile name, OncoKB alteration label, ClinVar title). Complex
profiles joined by ``OR`` apply when any component applies; ``AND`` profiles
apply only when every component applies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

from somaweave.domain import Alteration, AlterationType, EvidenceRecord, MatchSpecificity

ProfileClass = Literal[
    "exact", "codon", "other_variant", "truncating_class", "splice_class", "region",
    "gene_wide", "fusion", "expression", "copy_number", "other",
]

SMALL_VARIANT_TYPES = frozenset({AlterationType.SNV, AlterationType.MNV, AlterationType.INSERTION,
                                 AlterationType.DELETION, AlterationType.DELINS})
VARIANT_MATCHED_CLASSES = frozenset({"exact", "codon", "truncating_class", "splice_class"})
INAPPLICABLE_LIMITATION_PREFIX = "alteration_class_mismatch:"

AA3 = {"Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C", "Gln": "Q", "Glu": "E", "Gly": "G", "His": "H",
       "Ile": "I", "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P", "Ser": "S", "Thr": "T", "Trp": "W",
       "Tyr": "Y", "Val": "V", "Ter": "*"}

PROTEIN_RE = re.compile(r"^(?:p\.)?([A-Z])(\d+)([A-Za-z*=_\d]*)$")
PROTEIN_3_RE = re.compile(r"^(?:p\.)?([A-Z][a-z]{2})(\d+)(.*)$")
EMBEDDED_PROTEIN_RE = re.compile(r"\(p\.([^)]+)\)")


def one_letter_protein(hgvs_p: Optional[str]) -> Optional[str]:
    """``p.Asp32Asn`` / ``p.D32N`` / ``D32N`` -> ``D32N``; None if unparseable."""
    if not hgvs_p:
        return None
    s = hgvs_p.strip()
    if s.startswith("p."):
        s = s[2:]
    s = s.replace("(", "").replace(")", "")
    m3 = PROTEIN_3_RE.match(s)
    if m3 and m3.group(1) in AA3:
        ref, pos, rest = AA3[m3.group(1)], m3.group(2), m3.group(3) or ""
        for k, v in AA3.items():
            rest = rest.replace(k, v)
        return f"{ref}{pos}{rest}"
    m1 = PROTEIN_RE.match(s)
    if m1:
        return f"{m1.group(1)}{m1.group(2)}{m1.group(3) or ''}"
    return None


def codon_label(one_letter: Optional[str]) -> Optional[str]:
    if not one_letter:
        return None
    m = re.match(r"^([A-Z])(\d+)", one_letter)
    return f"{m.group(1)}{m.group(2)}" if m else None


def _strip_gene(text: str, gene: Optional[str]) -> str:
    t = text.strip()
    if gene and t.upper().startswith(gene.upper() + " "):
        t = t[len(gene) + 1:]
    return t.strip()


def classify_component(text: str, gene: Optional[str], case_protein: Optional[str]) -> ProfileClass:
    """Classify one profile component (no OR/AND inside)."""
    raw = _strip_gene(text, gene)
    low = raw.lower()
    if "::" in raw or "fusion" in low or "rearrangement" in low:
        return "fusion"
    if "expression" in low:
        return "expression"
    if "exon" in low or "domain" in low or "intron" in low or "codon" in low and not PROTEIN_RE.match(raw):
        return "region"
    if any(k in low for k in ("truncating", "loss-of-function", "loss of function", "nonsense", "frameshift", "inactivating")):
        return "truncating_class"
    if "splice" in low:
        return "splice_class"
    if any(k in low for k in ("amplification", "copy number", "copy-number", "gain", "deletion", "loss")) and not PROTEIN_RE.match(raw):
        return "copy_number"
    if not raw or low in {"mutation", "mutations", "alteration", "alterations", "activating mutation", "oncogenic mutation",
                          "oncogenic mutations", "activating mutations", "mutant", "variant"} \
            or re.fullmatch(r"(activating|oncogenic|hotspot|kinase domain|gain[- ]of[- ]function|driver)? ?(mutation|mutations|alteration|alterations)", low):
        return "gene_wide"
    embedded = EMBEDDED_PROTEIN_RE.search(raw)
    ol = one_letter_protein(embedded.group(1)) if embedded else one_letter_protein(raw)
    if ol:
        if case_protein and ol == case_protein:
            return "exact"
        if case_protein and codon_label(ol) == codon_label(case_protein):
            return "codon"
        return "other_variant"
    return "other"


def classify_profile(description: Optional[str], gene: Optional[str], case_protein: Optional[str]) -> tuple[ProfileClass, list[ProfileClass], str]:
    """Return ``(profile_class, component_classes, combinator)`` where
    combinator is ``'or'``, ``'and'`` or ``'single'``. For ``OR`` profiles the
    profile class is the most applicable component; for ``AND`` the least."""
    text = (description or "").strip()
    if not text:
        return "gene_wide", ["gene_wide"], "single"
    if " OR " in text:
        parts, comb = text.split(" OR "), "or"
    elif " AND " in text:
        parts, comb = text.split(" AND "), "and"
    else:
        parts, comb = [text], "single"
    classes = [classify_component(p, gene, case_protein) for p in parts]
    order = ["exact", "codon", "truncating_class", "splice_class", "gene_wide", "region", "other_variant",
             "copy_number", "expression", "fusion", "other"]
    ranked = sorted(classes, key=order.index)
    return (ranked[0] if comb != "and" else ranked[-1]), classes, comb


@dataclass(frozen=True)
class Applicability:
    profile_class: ProfileClass
    applicable: bool
    variant_matched: bool
    reason: str


def applicability_for(record: EvidenceRecord, alteration: Alteration) -> Applicability:
    """Decide whether ``record`` can be used for ``alteration``.

    Exact/codon-matched records are always applicable. For small variants:
    truncating-class evidence applies only to truncating consequences,
    splice-class only to splice consequences, gene-wide evidence applies at
    gene level (not variant-matched), and fusion / expression / copy-number /
    region / other-specific-variant evidence does not apply. For CNAs only
    copy-number and gene-wide profiles apply; for fusions only fusion and
    gene-wide profiles apply.
    """
    case_protein = one_letter_protein(alteration.hgvs_p)
    if record.variant_match in (MatchSpecificity.EXACT_VARIANT, MatchSpecificity.CODON, MatchSpecificity.FUNCTIONAL_EQUIVALENT) \
            and record.source_name != "europepmc":
        cls: ProfileClass = "exact" if record.variant_match == MatchSpecificity.EXACT_VARIANT else "codon"
        return Applicability(cls, True, True, f"{record.variant_match.value} match reported by the source")
    cls, parts, comb = classify_profile(record.variant_description, record.gene_symbol or alteration.gene_symbol, case_protein)
    cclass = alteration.consequence_class()
    atype = alteration.alteration_type
    detail = f"profile class {cls}" + (f" ({comb} of {', '.join(parts)})" if comb != "single" else "")
    if cls in ("exact", "codon"):
        return Applicability(cls, True, True, detail)
    if atype in SMALL_VARIANT_TYPES:
        if cls == "truncating_class":
            ok = cclass == "truncating"
            return Applicability(cls, ok, ok, detail + (f"; case consequence {cclass or 'unknown'}" if not ok else "; case variant is truncating"))
        if cls == "splice_class":
            ok = cclass == "splice"
            return Applicability(cls, ok, ok, detail + (f"; case consequence {cclass or 'unknown'}" if not ok else "; case variant affects splicing"))
        if cls == "gene_wide":
            return Applicability(cls, True, False, detail + "; gene-level, not variant-matched")
        if cls == "region":
            return Applicability(cls, True, False, detail + "; exon/domain membership of the case variant not verifiable from the input; treated as gene-level")
        return Applicability(cls, False, False, detail + f"; does not follow from a {atype.value} ({cclass or 'consequence unknown'})")
    if atype == AlterationType.CNA:
        if cls == "copy_number":
            return Applicability(cls, True, True, detail)
        if cls == "gene_wide":
            return Applicability(cls, True, False, detail + "; gene-level, not variant-matched")
        return Applicability(cls, False, False, detail + "; does not follow from a copy-number alteration")
    if atype in (AlterationType.FUSION, AlterationType.SV):
        if cls == "fusion":
            partners = {p.gene_symbol.upper() for p in alteration.fusion_partners} | ({alteration.gene_symbol.upper()} if alteration.gene_symbol else set())
            text = (record.variant_description or "").upper()
            named = [g for g in partners if g in text]
            ok = bool(named) or not partners
            return Applicability(cls, ok, ok, detail + (f"; partner(s) {', '.join(named)} named" if named else "; case partners not named in profile"))
        if cls == "gene_wide":
            return Applicability(cls, True, False, detail + "; gene-level, not variant-matched")
        return Applicability(cls, False, False, detail + "; does not follow from a fusion/structural variant")
    if cls == "gene_wide":
        return Applicability(cls, True, False, detail)
    return Applicability(cls, False, False, detail + "; alteration type not comparable")
