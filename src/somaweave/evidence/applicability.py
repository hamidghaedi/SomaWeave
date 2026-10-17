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
    "exact", "codon", "other_variant", "truncating_class", "loss_class", "splice_class", "functional_class", "region",
    "region_indel", "gene_wide", "fusion", "expression", "copy_number", "other",
]

SMALL_VARIANT_TYPES = frozenset({AlterationType.SNV, AlterationType.MNV, AlterationType.INSERTION,
                                 AlterationType.DELETION, AlterationType.DELINS})
VARIANT_MATCHED_CLASSES = frozenset({"exact", "codon", "truncating_class", "loss_class", "splice_class"})
INDEL_WORDS = ("deletion", "insertion", "duplication", "indel", "delins")
GENE_TOKEN_RE = re.compile(r"^([A-Z][A-Z0-9orf\-]{1,14})\b")
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
    if "gain-of-function" in low or "gain of function" in low:
        return "functional_class"
    if "exon" in low or "domain" in low or "intron" in low or ("codon" in low and not PROTEIN_RE.match(raw)):
        return "region_indel" if any(w in low for w in INDEL_WORDS) else "region"
    if any(k in low for k in ("truncating", "loss-of-function", "loss of function", "nonsense", "frameshift", "inactivating")):
        return "truncating_class"
    if "splice" in low:
        return "splice_class"
    if any(k in low for k in ("amplification", "copy number", "copy-number", "copy gain", "copy loss", "deep deletion", "homozygous deletion")) \
            and not PROTEIN_RE.match(raw):
        return "copy_number"
    if low in {"loss", "deletion", "gain"} or re.fullmatch(r"(gene )?(loss|deletion)", low):
        # ambiguous wording: sources use 'Loss' for functional loss or truncation as well as copy loss
        return "loss_class"
    if not raw or low in {"mutation", "mutations", "alteration", "alterations", "activating mutation", "activation mutation",
                          "oncogenic mutation", "oncogenic mutations", "activating mutations", "mutant", "variant"} \
            or re.fullmatch(r"(activating|activation|oncogenic|hotspot|kinase domain|driver)? ?(mutation|mutations|alteration|alterations)", low):
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
    order = ["exact", "codon", "truncating_class", "loss_class", "splice_class", "functional_class", "gene_wide", "region",
             "region_indel", "other_variant", "copy_number", "expression", "fusion", "other"]
    ranked = sorted(classes, key=order.index)
    return (ranked[0] if comb != "and" else ranked[-1]), classes, comb


@dataclass(frozen=True)
class Applicability:
    profile_class: ProfileClass
    applicable: bool
    variant_matched: bool
    reason: str


def _component_gene(component: str) -> Optional[str]:
    m = GENE_TOKEN_RE.match(component.strip())
    return m.group(1) if m else None


def _component_satisfied_by(component: str, alt: Alteration) -> bool:
    """Whether one compound-profile component is produced by ``alt`` (exact/codon/class/gene-wide)."""
    cls = classify_component(component, alt.gene_symbol, one_letter_protein(alt.hgvs_p))
    sub = _single_applicability(cls, alt, [cls], "single")
    return sub.applicable


def applicability_for(record: EvidenceRecord, alteration: Alteration,
                      case_alterations: Optional[list[Alteration]] = None) -> Applicability:
    """Decide whether ``record`` can be used for ``alteration``.

    Exact/codon-matched single profiles are always applicable. For small
    variants: truncating/loss-class evidence applies only to truncating
    consequences, splice-class only to splice-disrupting consequences,
    gene-wide and bare exon/domain region evidence applies at gene level (not
    variant-matched), and fusion / expression / copy-number / exon-indel /
    other-specific-variant evidence does not apply. For CNAs only copy-number,
    loss-class and gene-wide profiles apply; for fusions only fusion and
    gene-wide profiles apply.

    Compound ``AND`` profiles (e.g. ``PIK3CA E545K AND FGFR3 N540K``) are never
    short-cut on the source's variant match: every component must be produced
    by this alteration or by another alteration recorded in the same case
    (``case_alterations``); otherwise the record is inapplicable.
    """
    case_protein = one_letter_protein(alteration.hgvs_p)
    description = record.variant_description or ""
    compound_and = " AND " in description
    if not compound_and and record.variant_match in (MatchSpecificity.EXACT_VARIANT, MatchSpecificity.CODON, MatchSpecificity.FUNCTIONAL_EQUIVALENT) \
            and record.source_name != "europepmc":
        cls: ProfileClass = "exact" if record.variant_match == MatchSpecificity.EXACT_VARIANT else "codon"
        return Applicability(cls, True, True, f"{record.variant_match.value} match reported by the source")
    cls, parts, comb = classify_profile(description, record.gene_symbol or alteration.gene_symbol, case_protein)
    if comb == "and":
        components = description.split(" AND ")
        others = [a for a in (case_alterations or []) if a.alteration_id != alteration.alteration_id]
        unmet: list[str] = []
        matched_here = False
        for comp, ccls in zip(components, parts):
            own_gene = _component_gene(comp)
            same_gene = own_gene is None or (alteration.gene_symbol and own_gene.upper() == alteration.gene_symbol.upper())
            if same_gene and _single_applicability(ccls, alteration, [ccls], "single").applicable:
                matched_here = matched_here or ccls in VARIANT_MATCHED_CLASSES
                continue
            if any((a.gene_symbol or "").upper() == (own_gene or "").upper() and _component_satisfied_by(comp, a) for a in others):
                continue
            unmet.append(comp.strip())
        if unmet:
            return Applicability("other", False, False,
                                 f"compound AND profile: component(s) not established in this case: {', '.join(unmet)}")
        best = min(parts, key=["exact", "codon", "truncating_class", "loss_class", "splice_class", "functional_class", "gene_wide",
                               "region", "region_indel", "other_variant", "copy_number", "expression", "fusion", "other"].index)
        return Applicability(best, True, matched_here, f"compound AND profile satisfied by case alterations ({', '.join(parts)})")
    return _single_applicability(cls, alteration, parts, comb, record)


def _single_applicability(cls: ProfileClass, alteration: Alteration, parts: list[ProfileClass], comb: str,
                          record: Optional[EvidenceRecord] = None) -> Applicability:
    cclass = alteration.consequence_class()
    atype = alteration.alteration_type
    detail = f"profile class {cls}" + (f" ({comb} of {', '.join(parts)})" if comb != "single" else "")
    if cls in ("exact", "codon"):
        return Applicability(cls, True, True, detail)
    if atype in SMALL_VARIANT_TYPES:
        if cls in ("truncating_class", "loss_class"):
            ok = cclass == "truncating"
            label = "truncating/loss-of-function" if cls == "truncating_class" else "'loss' (functional or copy loss; wording ambiguous)"
            return Applicability(cls, ok, ok, detail + (f"; {label} evidence requires a truncating consequence, case consequence is {cclass or 'unknown'}" if not ok
                                                         else "; case variant is truncating"))
        if cls == "splice_class":
            ok = cclass == "splice"
            return Applicability(cls, ok, ok, detail + (f"; case consequence {cclass or 'unknown'}" if not ok else "; case variant disrupts a splice donor/acceptor"))
        if cls == "functional_class":
            return Applicability(cls, True, False, detail + "; functional-effect class (e.g. gain-of-function) not established for the case variant; gene-level context only")
        if cls == "gene_wide":
            return Applicability(cls, True, False, detail + "; gene-level, not variant-matched")
        if cls == "region":
            return Applicability(cls, True, False, detail + "; exon/domain membership of the case variant not verifiable from the input; treated as gene-level")
        if cls == "region_indel":
            is_indel = atype in (AlterationType.INSERTION, AlterationType.DELETION, AlterationType.DELINS)
            if is_indel:
                return Applicability(cls, True, False, detail + "; exon membership not verifiable; indel class matches; treated as gene-level")
            return Applicability(cls, False, False, detail + f"; exon deletion/insertion class does not follow from a {atype.value}")
        return Applicability(cls, False, False, detail + f"; does not follow from a {atype.value} ({cclass or 'consequence unknown'})")
    if atype == AlterationType.CNA:
        if cls == "copy_number":
            return Applicability(cls, True, True, detail)
        if cls == "loss_class":
            is_loss = (alteration.copy_number_call or "").lower() in ("loss", "deletion", "deep_deletion", "homozygous_deletion", "deep deletion")
            return Applicability(cls, is_loss, is_loss, detail + ("; copy loss recorded" if is_loss else "; case CNA is not a loss"))
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
