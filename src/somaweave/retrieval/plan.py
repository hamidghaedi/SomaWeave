"""Progressive query planning.

``build_query_plan`` turns one case alteration into an ordered list of
``PlanItem`` objects, one per ``MatchSpecificity`` tier, from the exact variant
down to disease-only treatment/resistance literature. Each item carries
provider-neutral search terms and the names of the providers that can answer
it. The tier of the item that produced a record becomes that record's
``query_tier``; the provider decides the finer ``variant_match``.

Nothing here contacts a network or infers biology beyond deterministic string
handling: pathway membership comes from a small explicit table and is left
empty for genes not in it.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from somaweave.domain import Alteration, AlterationType, Case, MatchSpecificity

AA3_TO_1 = {
    "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C", "Gln": "Q", "Glu": "E", "Gly": "G",
    "His": "H", "Ile": "I", "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P", "Ser": "S",
    "Thr": "T", "Trp": "W", "Tyr": "Y", "Val": "V", "Ter": "*", "Sec": "U", "Pyl": "O",
}
AA1_TO_3 = {v: k for k, v in AA3_TO_1.items()}

# Small, explicit gene -> pathway table. Deliberately conservative: a gene not
# listed yields an empty pathway tier rather than a guess.
GENE_PATHWAYS: dict[str, str] = {
    "CTNNB1": "WNT", "APC": "WNT", "AXIN1": "WNT", "AXIN2": "WNT", "RNF43": "WNT", "GSK3B": "WNT",
    "KRAS": "MAPK", "NRAS": "MAPK", "HRAS": "MAPK", "BRAF": "MAPK", "MAP2K1": "MAPK", "MAP2K2": "MAPK", "NF1": "MAPK",
    "PIK3CA": "PI3K-AKT-mTOR", "PIK3R1": "PI3K-AKT-mTOR", "PTEN": "PI3K-AKT-mTOR", "AKT1": "PI3K-AKT-mTOR",
    "MTOR": "PI3K-AKT-mTOR", "TSC1": "PI3K-AKT-mTOR", "TSC2": "PI3K-AKT-mTOR",
    "EGFR": "RTK", "ERBB2": "RTK", "ERBB3": "RTK", "MET": "RTK", "ALK": "RTK", "ROS1": "RTK", "RET": "RTK",
    "FGFR1": "RTK", "FGFR2": "RTK", "FGFR3": "RTK", "KIT": "RTK", "PDGFRA": "RTK", "NTRK1": "RTK", "NTRK2": "RTK", "NTRK3": "RTK",
    "TP53": "TP53", "MDM2": "TP53", "CDKN2A": "cell cycle", "CDK4": "cell cycle", "CDK6": "cell cycle", "RB1": "cell cycle", "CCND1": "cell cycle",
    "BRCA1": "homologous recombination", "BRCA2": "homologous recombination", "PALB2": "homologous recombination",
    "ATM": "homologous recombination", "RAD51C": "homologous recombination", "RAD51D": "homologous recombination",
    "MLH1": "mismatch repair", "MSH2": "mismatch repair", "MSH6": "mismatch repair", "PMS2": "mismatch repair",
    "IDH1": "IDH", "IDH2": "IDH", "SMAD4": "TGF-beta", "TGFBR2": "TGF-beta",
    "ARID1A": "SWI/SNF", "SMARCA4": "SWI/SNF", "SMARCB1": "SWI/SNF", "PBRM1": "SWI/SNF",
    "KEAP1": "NRF2", "NFE2L2": "NRF2", "STK11": "LKB1-AMPK", "VHL": "HIF", "NOTCH1": "NOTCH", "FBXW7": "NOTCH",
}

# Sequence Ontology consequence -> coarse alteration class used as a search term.
CONSEQUENCE_CLASSES: dict[str, str] = {
    "missense_variant": "missense", "stop_gained": "truncating", "stop_lost": "stop lost",
    "frameshift_variant": "frameshift", "inframe_deletion": "in-frame deletion", "inframe_insertion": "in-frame insertion",
    "splice_acceptor_variant": "splice site", "splice_donor_variant": "splice site", "splice_region_variant": "splice region",
    "start_lost": "start lost", "synonymous_variant": "synonymous", "protein_altering_variant": "protein altering",
}
DEFAULT_OUTCOME_TERMS = ["resistance", "response", "sensitivity"]

TIER_ORDER = list(MatchSpecificity)
TIER_RANK = {tier: i for i, tier in enumerate(TIER_ORDER)}
PLAN_TIERS = [
    MatchSpecificity.EXACT_VARIANT, MatchSpecificity.CODON, MatchSpecificity.GENE_ALTERATION_CLASS,
    MatchSpecificity.GENE, MatchSpecificity.PATHWAY, MatchSpecificity.DISEASE_ONLY,
]
# Which providers can answer which tier. Providers additionally check their own
# ``supports``; this table only controls what the planner asks for.
DEFAULT_TIER_PROVIDERS: dict[MatchSpecificity, list[str]] = {
    MatchSpecificity.EXACT_VARIANT: ["civic", "clinvar", "europepmc"],
    MatchSpecificity.CODON: ["civic", "europepmc"],
    MatchSpecificity.GENE_ALTERATION_CLASS: ["europepmc"],
    MatchSpecificity.GENE: ["civic", "europepmc"],
    MatchSpecificity.PATHWAY: ["europepmc"],
    MatchSpecificity.DISEASE_ONLY: ["europepmc"],
}


class PlanItem(BaseModel):
    """One tier of the progressive query plan."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tier: MatchSpecificity
    terms: dict[str, Any] = Field(default_factory=dict, description="Provider-neutral search terms.")
    providers: list[str] = Field(default_factory=list, description="Provider names that should run this item.")
    alteration_id: str
    case_id: str
    description: str = ""

    @property
    def rank(self) -> int:
        return TIER_RANK[self.tier]


_P_RE = re.compile(r"^(?:p\.)?\(?(?P<rest>.+?)\)?$")
_SIMPLE_SUB_1 = re.compile(r"^(?P<ref>[A-Z\*])(?P<pos>\d+)(?P<alt>[A-Z\*=]|fs.*|del|dup|ins.*)$")
_SIMPLE_SUB_3 = re.compile(r"^(?P<ref>[A-Z][a-z]{2})(?P<pos>\d+)(?P<alt>[A-Z][a-z]{2}|\*|=|fs.*|del|dup|ins.*)$")
_THREE_LETTER = re.compile("|".join(sorted(AA3_TO_1, key=len, reverse=True)))


def to_one_letter(protein_change: str) -> str:
    """Convert three-letter residue codes in a protein change to one-letter codes.

    ``p.Asp32Asn`` -> ``D32N``; ``p.Asp32_Gly34del`` -> ``D32_G34del``. Strings
    already in one-letter form are returned without the ``p.`` prefix.
    """
    core = _P_RE.match(protein_change.strip()).group("rest")  # type: ignore[union-attr]
    return _THREE_LETTER.sub(lambda m: AA3_TO_1[m.group(0)], core)


def to_three_letter(protein_change: str) -> Optional[str]:
    """Convert a simple one-letter substitution (``D32N``) to three-letter form (``Asp32Asn``).

    Returns ``None`` for forms that are not simple substitutions/truncations,
    rather than guessing.
    """
    core = _P_RE.match(protein_change.strip()).group("rest")  # type: ignore[union-attr]
    m = _SIMPLE_SUB_1.match(core)
    if not m:
        return None
    ref = AA1_TO_3.get(m.group("ref"))
    if ref is None:
        return None
    alt = m.group("alt")
    if len(alt) == 1 and alt in AA1_TO_3:
        alt = AA1_TO_3[alt]
    return f"{ref}{m.group('pos')}{alt}"


def protein_change_terms(hgvs_p: str) -> dict[str, Any]:
    """Derive one-letter/three-letter synonyms and the codon term from a protein HGVS.

    Returns keys ``protein_change`` (one-letter, no prefix), ``variant_terms``
    (ordered unique synonyms) and ``codon`` / ``codon_terms`` when the residue
    position can be read.
    """
    raw = hgvs_p.strip()
    one = to_one_letter(raw)
    three = to_three_letter(one)
    if three is None:
        core = _P_RE.match(raw).group("rest")  # type: ignore[union-attr]
        three = core if _SIMPLE_SUB_3.match(core) else None
    terms: list[str] = []
    for t in (one, f"p.{one}", three, f"p.{three}" if three else None, raw):
        if t and t not in terms:
            terms.append(t)
    out: dict[str, Any] = {"protein_change": one, "variant_terms": terms}
    m = _SIMPLE_SUB_1.match(one)
    if m and m.group("ref") in AA1_TO_3:
        codon = f"{m.group('ref')}{m.group('pos')}"
        out["codon"] = codon
        out["codon_position"] = int(m.group("pos"))
        out["codon_terms"] = [codon, f"{AA1_TO_3[m.group('ref')]}{m.group('pos')}"]
    return out


def alteration_class(alteration: Alteration) -> Optional[str]:
    """Coarse alteration class term; ``None`` when it cannot be stated without guessing."""
    if alteration.alteration_type == AlterationType.CNA:
        return alteration.copy_number_call or "copy number alteration"
    if alteration.alteration_type == AlterationType.FUSION:
        return "fusion"
    if alteration.alteration_type == AlterationType.SV:
        return "structural variant"
    if alteration.consequence:
        return CONSEQUENCE_CLASSES.get(alteration.consequence, alteration.consequence.replace("_", " "))
    return None


def disease_terms(case: Case) -> dict[str, Any]:
    """Disease vocabulary from the pathology-confirmed diagnosis only.

    Disease hypotheses are listed separately and are never merged into the
    primary disease term.
    """
    d = case.diagnosis
    terms = [d.name]
    if d.primary_site and d.primary_site.lower() not in d.name.lower():
        terms.append(d.primary_site)
    return {
        "disease": d.name,
        "disease_terms": terms,
        "oncotree_code": d.oncotree_code,
        "disease_hypotheses": [h.name for h in case.disease_hypotheses],
    }


def treatment_terms(case: Case) -> dict[str, Any]:
    agents: list[str] = []
    for tx in case.treatments:
        for a in tx.agents or [tx.name]:
            if a and a not in agents:
                agents.append(a)
    return {"treatments": agents, "treatment_names": [tx.name for tx in case.treatments], "outcome_terms": list(DEFAULT_OUTCOME_TERMS)}


def build_query_plan(case: Case, alteration: Alteration,
                     tier_providers: dict[MatchSpecificity, list[str]] | None = None) -> list[PlanItem]:
    """Build the six-tier progressive plan for one alteration of a case.

    Tiers whose terms cannot be formed (no HGVS p. for the codon tier, gene not
    in the pathway table, no treatments for the disease-only tier) are still
    emitted with an empty provider list so the gap is visible downstream.
    """
    tier_providers = tier_providers or DEFAULT_TIER_PROVIDERS
    gene = alteration.gene_symbol
    dz = disease_terms(case)
    tx = treatment_terms(case)
    common = {"gene": gene, "alteration_type": alteration.alteration_type.value, **dz}

    prot = protein_change_terms(alteration.hgvs_p) if alteration.hgvs_p else {}
    exact_terms: dict[str, Any] = {**common, **prot}
    variant_terms = list(prot.get("variant_terms", []))
    if alteration.hgvs_c and alteration.hgvs_c not in variant_terms:
        variant_terms.append(alteration.hgvs_c)
    if alteration.alteration_type == AlterationType.FUSION:
        partners = [p.gene_symbol for p in alteration.fusion_partners]
        if partners:
            variant_terms.append("-".join(partners) + " fusion" if len(partners) > 1 else f"{partners[0]} fusion")
            exact_terms["fusion_partners"] = partners
    if alteration.alteration_type == AlterationType.CNA and alteration.copy_number_call:
        variant_terms.append(f"{gene} {alteration.copy_number_call}")
    exact_terms["variant_terms"] = variant_terms
    exact_terms["hgvs_c"] = alteration.hgvs_c
    exact_terms["hgvs_p"] = alteration.hgvs_p

    items: list[PlanItem] = []

    def add(tier: MatchSpecificity, terms: dict[str, Any], ok: bool, description: str) -> None:
        items.append(PlanItem(
            tier=tier, terms={k: v for k, v in terms.items() if v not in (None, [], "")},
            providers=list(tier_providers.get(tier, [])) if ok else [],
            alteration_id=alteration.alteration_id, case_id=case.case_id, description=description,
        ))

    add(MatchSpecificity.EXACT_VARIANT, exact_terms, bool(gene and variant_terms),
        f"{gene} {prot.get('protein_change') or alteration.hgvs_c or alteration.alteration_type.value}")

    codon_terms = {**common, "codon": prot.get("codon"), "codon_terms": prot.get("codon_terms"), "codon_position": prot.get("codon_position")}
    add(MatchSpecificity.CODON, codon_terms, bool(gene and prot.get("codon")),
        f"{gene} codon {prot.get('codon')}" if prot.get("codon") else "codon tier not applicable")

    cls = alteration_class(alteration)
    add(MatchSpecificity.GENE_ALTERATION_CLASS, {**common, "alteration_class": cls}, bool(gene and cls),
        f"{gene} {cls} in {dz['disease']}" if cls else "alteration class unknown")

    add(MatchSpecificity.GENE, dict(common), bool(gene), f"{gene} in {dz['disease']}")

    pathway = GENE_PATHWAYS.get(gene or "")
    pathway_genes = sorted(g for g, p in GENE_PATHWAYS.items() if p == pathway) if pathway else []
    add(MatchSpecificity.PATHWAY, {**common, "pathway": pathway, "pathway_genes": pathway_genes}, bool(pathway),
        f"{pathway} pathway in {dz['disease']}" if pathway else f"no pathway assignment for {gene}")

    add(MatchSpecificity.DISEASE_ONLY, {**dz, **tx, "gene": gene}, bool(tx["treatments"]),
        f"{dz['disease']} treatment/resistance literature" if tx["treatments"] else "no treatments recorded")

    items.sort(key=lambda it: it.rank)
    return items
