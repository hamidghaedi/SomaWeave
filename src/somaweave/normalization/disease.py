"""Disease context and OncoTree-based disease matching.

The full OncoTree ontology is not shipped. A small built-in lineage table
covers common codes so that disease matching and conflict detection work
out of the box; the public OncoTree ``tumorTypes`` JSON can be loaded for
complete coverage via :func:`load_oncotree_json`.

Rules:
- the pathology-confirmed diagnosis and disease hypotheses are kept apart;
- ICD-O morphology that implies a different entity than the OncoTree code
  produces a conflict flag, never a corrected code;
- evidence disease labels that cannot be resolved give ``UNKNOWN``, not
  ``DIFFERENT``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from somaweave.domain import Case, DiseaseMatch


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OncoTreeNode(_Model):
    code: str
    name: str
    parent: Optional[str] = Field(default=None, description="Parent code; None for the root 'TISSUE'.")
    main_type: Optional[str] = None
    tissue: Optional[str] = None


class OncoTreeTable:
    """Minimal OncoTree lookup: parent chain and name -> code resolution."""

    def __init__(self, nodes: list[OncoTreeNode], source: str):
        self.source = source
        self._nodes: dict[str, OncoTreeNode] = {n.code.upper(): n for n in nodes}
        self._by_name: dict[str, str] = {}
        for n in nodes:
            key = n.name.strip().lower()
            # names are not guaranteed unique in OncoTree; keep the first and drop ambiguous ones
            if key in self._by_name and self._by_name[key] != n.code:
                self._by_name[key] = ""
            else:
                self._by_name.setdefault(key, n.code)

    def __contains__(self, code: str) -> bool:
        return code.upper() in self._nodes

    def node(self, code: str) -> Optional[OncoTreeNode]:
        return self._nodes.get(code.upper())

    def name(self, code: str) -> Optional[str]:
        n = self.node(code)
        return n.name if n else None

    def ancestors(self, code: str) -> list[str]:
        """Parent chain from the immediate parent upward (excluding ``code``)."""
        out: list[str] = []
        seen = {code.upper()}
        cur = self.node(code)
        while cur is not None and cur.parent:
            p = cur.parent.upper()
            if p in seen:
                break
            out.append(p)
            seen.add(p)
            cur = self.node(p)
        return out

    def resolve(self, label: Optional[str]) -> Optional[str]:
        """Resolve a code or a disease name to a code; ``None`` if unknown/ambiguous."""
        if not label:
            return None
        s = label.strip()
        if s.upper() in self._nodes:
            return s.upper()
        code = self._by_name.get(s.lower())
        return code or None


# (code, name, parent) -- a subset of OncoTree, enough for development and tests.
_BUILTIN_NODES: list[tuple[str, str, Optional[str]]] = [
    ("TISSUE", "Tissue", None),
    ("PANCREAS", "Pancreas", "TISSUE"),
    ("PAAD", "Pancreatic Adenocarcinoma", "PANCREAS"),
    ("PAAC", "Acinar Cell Carcinoma of the Pancreas", "PANCREAS"),
    ("PANET", "Pancreatic Neuroendocrine Tumor", "PANCREAS"),
    ("SPN", "Solid Pseudopapillary Neoplasm of the Pancreas", "PANCREAS"),
    ("IPMN", "Intraductal Papillary Mucinous Neoplasm", "PANCREAS"),
    ("LUNG", "Lung", "TISSUE"),
    ("NSCLC", "Non-Small Cell Lung Cancer", "LUNG"),
    ("LUAD", "Lung Adenocarcinoma", "NSCLC"),
    ("LUSC", "Lung Squamous Cell Carcinoma", "NSCLC"),
    ("SCLC", "Small Cell Lung Cancer", "LUNG"),
    ("BOWEL", "Bowel", "TISSUE"),
    ("COADREAD", "Colorectal Adenocarcinoma", "BOWEL"),
    ("COAD", "Colon Adenocarcinoma", "COADREAD"),
    ("READ", "Rectal Adenocarcinoma", "COADREAD"),
    ("BLADDER", "Bladder/Urinary Tract", "TISSUE"),
    ("BLCA", "Bladder Urothelial Carcinoma", "BLADDER"),
    ("SKIN", "Skin", "TISSUE"),
    ("MEL", "Melanoma", "SKIN"),
    ("SKCM", "Cutaneous Melanoma", "MEL"),
    ("CNS_BRAIN", "CNS/Brain", "TISSUE"),
    ("GLIOMA", "Glioma", "CNS_BRAIN"),
    ("GBM", "Glioblastoma", "GLIOMA"),
    ("BREAST", "Breast", "TISSUE"),
    ("BRCA", "Invasive Breast Carcinoma", "BREAST"),
    ("IDC", "Breast Invasive Ductal Carcinoma", "BRCA"),
    ("ILC", "Breast Invasive Lobular Carcinoma", "BRCA"),
    ("OVARY", "Ovary/Fallopian Tube", "TISSUE"),
    ("HGSOC", "High-Grade Serous Ovarian Cancer", "OVARY"),
    ("PROSTATE", "Prostate", "TISSUE"),
    ("PRAD", "Prostate Adenocarcinoma", "PROSTATE"),
    ("LIVER", "Liver", "TISSUE"),
    ("HCC", "Hepatocellular Carcinoma", "LIVER"),
    ("BILIARY_TRACT", "Biliary Tract", "TISSUE"),
    ("CHOL", "Cholangiocarcinoma", "BILIARY_TRACT"),
    ("STOMACH", "Esophagus/Stomach", "TISSUE"),
    ("STAD", "Stomach Adenocarcinoma", "STOMACH"),
    ("KIDNEY", "Kidney", "TISSUE"),
    ("CCRCC", "Renal Clear Cell Carcinoma", "KIDNEY"),
    ("THYROID", "Thyroid", "TISSUE"),
    ("THPA", "Papillary Thyroid Cancer", "THYROID"),
    ("SOFT_TISSUE", "Soft Tissue", "TISSUE"),
    ("GIST", "Gastrointestinal Stromal Tumor", "SOFT_TISSUE"),
    ("MYELOID", "Myeloid", "TISSUE"),
    ("AML", "Acute Myeloid Leukemia", "MYELOID"),
    ("UTERUS", "Uterus", "TISSUE"),
    ("UEC", "Uterine Endometrioid Carcinoma", "UTERUS"),
]

BUILTIN_ONCOTREE = OncoTreeTable(
    [OncoTreeNode(code=c, name=n, parent=p) for c, n, p in _BUILTIN_NODES], source="builtin-subset"
)

# Evidence disease labels that mean "any cancer".
PAN_CANCER_LABELS: frozenset[str] = frozenset({
    "all solid tumors", "all solid tumours", "solid tumor", "solid tumors", "solid tumour", "solid tumours",
    "pan-cancer", "pan cancer", "pancancer", "all tumors", "all tumours", "cancer", "any cancer",
    "all liquid tumors", "all cancers", "tissue",
})

# ICD-O-3 morphology code -> OncoTree codes it is consistent with.
# This map covers a few codes relevant to development cases; absence of a code
# means "not assessed", never "consistent".
ICDO_MORPHOLOGY_TO_ONCOTREE: dict[str, tuple[str, ...]] = {
    "8452/3": ("SPN",),
    "8452/1": ("SPN",),
    "8453/3": ("IPMN",),       # intraductal papillary-mucinous carcinoma, invasive
    "8550/3": ("PAAC",),       # acinar cell carcinoma
    "8140/3": ("PAAD", "LUAD", "COAD", "READ", "COADREAD", "PRAD", "STAD", "IDC", "BRCA", "UEC"),  # adenocarcinoma NOS
    "8070/3": ("LUSC",),       # squamous cell carcinoma NOS; other squamous sites not in the builtin subset
    "8120/3": ("BLCA",),       # transitional/urothelial carcinoma
    "8720/3": ("MEL", "SKCM"), # melanoma NOS
    "9440/3": ("GBM",),
    "8170/3": ("HCC",),
    "8041/3": ("SCLC",),
    "8936/3": ("GIST",),
    "8310/3": ("CCRCC",),
}

ICDO_MORPHOLOGY_NAMES: dict[str, str] = {
    "8452/3": "solid pseudopapillary neoplasm, malignant",
    "8452/1": "solid pseudopapillary neoplasm, uncertain behaviour",
    "8453/3": "intraductal papillary-mucinous carcinoma, invasive",
    "8550/3": "acinar cell carcinoma",
    "8140/3": "adenocarcinoma, NOS",
    "8070/3": "squamous cell carcinoma, NOS",
    "8120/3": "transitional (urothelial) cell carcinoma, NOS",
    "8720/3": "malignant melanoma, NOS",
    "9440/3": "glioblastoma, NOS",
    "8170/3": "hepatocellular carcinoma, NOS",
    "8041/3": "small cell carcinoma, NOS",
    "8936/3": "gastrointestinal stromal tumor, malignant",
    "8310/3": "clear cell adenocarcinoma, NOS",
}


class DiseaseFlag(_Model):
    code: str = Field(description="Machine-readable flag, e.g. 'morphology_oncotree_conflict'.")
    severity: str = Field(description="'info', 'warning' or 'conflict'.")
    message: str


class HypothesisContext(_Model):
    name: str
    oncotree_code: Optional[str] = None
    code_known: bool = Field(description="True if the code resolves in the available OncoTree table.")
    relation_to_confirmed: DiseaseMatch = Field(description="How the hypothesis relates to the confirmed code.")
    rationale: Optional[str] = None
    proposed_by: Optional[str] = None


class DiseaseContext(_Model):
    """Confirmed diagnosis, separate hypotheses, and explicit conflict flags."""

    confirmed_name: str
    confirmed_oncotree_code: Optional[str] = None
    confirmed_code_known: bool = False
    confirmed_lineage: list[str] = Field(default_factory=list, description="Ancestor codes of the confirmed code, nearest first.")
    confirmed_by_pathology: bool = True
    icd_o_morphology: Optional[str] = None
    icd_o_morphology_name: Optional[str] = None
    icd_o_topography: Optional[str] = None
    hypotheses: list[HypothesisContext] = Field(default_factory=list)
    flags: list[DiseaseFlag] = Field(default_factory=list)
    oncotree_source: str

    def has_conflicts(self) -> bool:
        return any(f.severity == "conflict" for f in self.flags)


def load_oncotree_json(path: str | Path) -> OncoTreeTable:
    """Load the public OncoTree ``tumorTypes`` JSON.

    Expected format: a JSON array (as served by
    ``/api/tumorTypes``) of objects with keys ``code``, ``name``, ``parent``
    (code or null), ``mainType`` and ``tissue``. Either a flat array or an
    object with a top-level ``data`` array is accepted.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "data" in raw:
        raw = raw["data"]
    if not isinstance(raw, list):
        raise ValueError("OncoTree JSON must be an array of tumor types")
    nodes = []
    for item in raw:
        if not isinstance(item, dict) or "code" not in item or "name" not in item:
            raise ValueError("each OncoTree entry needs 'code' and 'name'")
        nodes.append(OncoTreeNode(code=str(item["code"]), name=str(item["name"]), parent=item.get("parent"),
                                  main_type=item.get("mainType"), tissue=item.get("tissue")))
    return OncoTreeTable(nodes, source=str(path))


def disease_match(case_code: Optional[str], evidence_disease: Optional[str],
                  table: OncoTreeTable = BUILTIN_ONCOTREE) -> DiseaseMatch:
    """Relate an evidence disease label (code or name) to the case OncoTree code.

    - identical codes -> ``SAME``
    - evidence code is an ancestor of the case code -> ``PARENT``
    - evidence code is a descendant of, or shares a non-root ancestor with,
      the case code -> ``RELATED``
    - pan-cancer labels -> ``PAN_CANCER``
    - both resolve but share no lineage -> ``DIFFERENT``
    - either side missing or unresolvable -> ``UNKNOWN``
    """
    if not case_code or not evidence_disease:
        return DiseaseMatch.UNKNOWN
    ev = evidence_disease.strip()
    if ev.lower() in PAN_CANCER_LABELS:
        return DiseaseMatch.PAN_CANCER
    case = case_code.strip().upper()
    ev_code = table.resolve(ev)
    if ev_code is None:
        return DiseaseMatch.UNKNOWN
    if ev_code == "TISSUE":
        return DiseaseMatch.PAN_CANCER
    if ev_code == case:
        return DiseaseMatch.SAME
    if case not in table:
        return DiseaseMatch.UNKNOWN
    case_anc = table.ancestors(case)
    if ev_code in case_anc:
        return DiseaseMatch.PARENT
    ev_anc = table.ancestors(ev_code)
    if case in ev_anc:
        return DiseaseMatch.RELATED
    shared = (set(case_anc) & set(ev_anc)) - {"TISSUE"}
    if shared:
        return DiseaseMatch.RELATED
    return DiseaseMatch.DIFFERENT


def build_disease_context(case: Case, table: OncoTreeTable = BUILTIN_ONCOTREE) -> DiseaseContext:
    """Derive the disease context for a case without altering any recorded value."""
    dx = case.diagnosis
    flags: list[DiseaseFlag] = []
    code = dx.oncotree_code.strip().upper() if dx.oncotree_code else None
    known = bool(code and code in table)
    if code is None:
        flags.append(DiseaseFlag(code="oncotree_code_missing", severity="warning",
                                 message="diagnosis has no OncoTree code; disease matching will return UNKNOWN"))
    elif not known:
        flags.append(DiseaseFlag(code="oncotree_code_not_in_table", severity="warning",
                                 message=f"OncoTree code '{code}' is not in the loaded table ({table.source}); lineage unavailable"))
    if not dx.confirmed_by_pathology:
        flags.append(DiseaseFlag(code="diagnosis_not_pathology_confirmed", severity="warning",
                                 message="diagnosis is recorded as not pathology-confirmed"))

    morph = dx.icd_o_morphology.strip() if dx.icd_o_morphology else None
    morph_name = ICDO_MORPHOLOGY_NAMES.get(morph) if morph else None
    if morph and code:
        consistent = ICDO_MORPHOLOGY_TO_ONCOTREE.get(morph)
        if consistent is None:
            flags.append(DiseaseFlag(code="morphology_not_assessed", severity="info",
                                     message=f"ICD-O morphology {morph} is not in the built-in map; consistency with {code} not assessed"))
        elif code in consistent:
            flags.append(DiseaseFlag(code="morphology_oncotree_consistent", severity="info",
                                     message=f"ICD-O morphology {morph} ({morph_name}) is consistent with OncoTree {code}"))
        else:
            flags.append(DiseaseFlag(
                code="morphology_oncotree_conflict", severity="conflict",
                message=(f"ICD-O morphology {morph} ({morph_name}) implies {'/'.join(consistent)}, "
                         f"but OncoTree code is {code}; no automatic correction applied, pathology review required"),
            ))

    hyps: list[HypothesisContext] = []
    for h in case.disease_hypotheses:
        hcode = h.oncotree_code.strip().upper() if h.oncotree_code else None
        rel = disease_match(code, hcode, table) if hcode else DiseaseMatch.UNKNOWN
        hyps.append(HypothesisContext(name=h.name, oncotree_code=hcode, code_known=bool(hcode and hcode in table),
                                      relation_to_confirmed=rel, rationale=h.rationale, proposed_by=h.proposed_by))
        label = hcode or h.name
        if rel == DiseaseMatch.SAME:
            flags.append(DiseaseFlag(code="hypothesis_matches_confirmed", severity="info",
                                     message=f"hypothesis {label} matches the confirmed diagnosis code"))
        else:
            flags.append(DiseaseFlag(
                code="hypothesis_unconfirmed", severity="warning",
                message=(f"disease hypothesis {label} ({h.name}) is not pathology-confirmed; relation to confirmed "
                         f"{code or 'unknown code'}: {rel.value}. Evidence retrieved for it must be labelled as hypothesis-driven."),
            ))

    return DiseaseContext(
        confirmed_name=dx.name,
        confirmed_oncotree_code=code,
        confirmed_code_known=known,
        confirmed_lineage=table.ancestors(code) if known else [],
        confirmed_by_pathology=dx.confirmed_by_pathology,
        icd_o_morphology=morph,
        icd_o_morphology_name=morph_name,
        icd_o_topography=dx.icd_o_topography,
        hypotheses=hyps,
        flags=flags,
        oncotree_source=table.source,
    )
