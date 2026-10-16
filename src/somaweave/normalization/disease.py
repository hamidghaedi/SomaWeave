"""Disease context and OncoTree-based disease matching.

The full OncoTree ontology is not shipped. A small built-in lineage table
covers common codes so that disease matching and conflict detection work
out of the box; the public OncoTree ``tumorTypes`` JSON can be loaded for
complete coverage via :func:`load_oncotree_json`, which returns an
:class:`OncoTreeIndex` (code, DOID, normalised-name, synonym and main-type
lookups, ancestors and tissue). :func:`find_oncotree_json` locates the file
under a reference root; no path is hard-coded here.

Rules:
- the pathology-confirmed diagnosis and disease hypotheses are kept apart;
- ICD-O morphology that implies a different entity than the OncoTree code
  produces a conflict flag, never a corrected code;
- evidence disease labels that cannot be resolved give ``UNKNOWN``, not
  ``DIFFERENT``.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal, Optional

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
    level: Optional[int] = Field(default=None, ge=0)
    external_references: dict[str, list[str]] = Field(default_factory=dict, description="e.g. {'UMLS': [...], 'NCI': [...]} as served by the API.")


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

# Evidence disease labels that mean "any cancer".
PAN_CANCER_LABELS: frozenset[str] = frozenset({
    "all solid tumors", "all solid tumours", "solid tumor", "solid tumors", "solid tumour", "solid tumours",
    "pan-cancer", "pan cancer", "pancancer", "all tumors", "all tumours", "cancer", "any cancer",
    "all liquid tumors", "all cancers", "tissue",
})

#: Sentinel code returned when an evidence disease label means "any cancer".
PAN_CANCER_CODE = "PAN_CANCER"
#: Implicit OncoTree root; not served as a node by the public API.
ROOT_CODE = "TISSUE"

_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_SINGULAR: dict[str, str] = {
    "tumors": "tumor", "tumours": "tumor", "tumour": "tumor", "cancers": "cancer", "carcinomas": "carcinoma",
    "adenocarcinomas": "adenocarcinoma", "neoplasms": "neoplasm", "sarcomas": "sarcoma", "leukemias": "leukemia",
    "leukaemia": "leukemia", "lymphomas": "lymphoma", "melanomas": "melanoma", "gliomas": "glioma",
}
_DROP_TOKENS: frozenset[str] = frozenset({"nos", "of", "the"})


def normalize_disease_name(name: str) -> str:
    """Canonical lookup key for a disease name.

    Lower-case; hyphens and slashes become spaces; other punctuation is
    removed; ``NOS`` and the function words ``of``/``the`` are dropped;
    common plurals and British spellings are singularised/americanised.
    Example: ``"Acinar Cell Carcinoma of the Pancreas, NOS"`` ->
    ``"acinar cell carcinoma pancreas"``.
    """
    s = name.lower().replace("-", " ").replace("/", " ")
    s = _NON_ALNUM.sub(" ", s)
    tokens = [_SINGULAR.get(t, t) for t in s.split() if t not in _DROP_TOKENS]
    return " ".join(tokens)


def _carcinoma_cancer_variant(key: str) -> Optional[str]:
    """Swap the tokens ``carcinoma`` <-> ``cancer`` (one direction per key); ``None`` if neither present."""
    tokens = key.split()
    if "carcinoma" in tokens:
        return " ".join("cancer" if t == "carcinoma" else t for t in tokens)
    if "cancer" in tokens:
        return " ".join("carcinoma" if t == "cancer" else t for t in tokens)
    return None


# Disease names used by CIViC (Disease Ontology labels) and OncoKB that differ
# from OncoTree node names. Keys are ``normalize_disease_name`` outputs; values
# are candidate OncoTree codes in preference order -- the first code present in
# the loaded index is used, which absorbs code renames between OncoTree
# releases (GBM/GLIOMA/CNS_BRAIN became GB/DIFG/BRAIN in 2025). Broad
# "<organ> cancer" labels map to the organ (tissue-level) node, which is a true
# superset of every histology beneath it and therefore yields PARENT rather
# than a misleading SAME or RELATED; "Pancreatic Cancer" (DOID:1793) is the
# Disease Ontology parent of pancreatic adenocarcinoma, so it maps to PANCREAS,
# not PAAD.
DISEASE_NAME_SYNONYMS: dict[str, tuple[str, ...]] = {
    # lung
    "lung non small cell carcinoma": ("NSCLC",),
    "non small cell lung carcinoma": ("NSCLC",),
    "lung cancer": ("LUNG",),
    "lung carcinoma": ("LUNG",),
    "lung small cell carcinoma": ("SCLC",),
    "small cell lung carcinoma": ("SCLC",),
    # bowel
    "colorectal cancer": ("COADREAD",),
    "colorectal carcinoma": ("COADREAD",),
    "colon cancer": ("COAD",),
    "colon carcinoma": ("COAD",),
    "rectal cancer": ("READ",),
    "rectum cancer": ("READ",),
    # skin
    "malignant melanoma": ("MEL",),
    "skin melanoma": ("SKCM",),
    # breast
    "breast cancer": ("BREAST",),
    "breast carcinoma": ("BRCA",),
    # CNS
    "glioblastoma": ("GBM", "GB"),
    "glioblastoma multiforme": ("GBM", "GB"),
    "brain cancer": ("CNS_BRAIN", "BRAIN"),
    "cns cancer": ("CNS_BRAIN", "BRAIN"),
    "childhood medulloblastoma": ("MBL",),
    # pancreas
    "pancreatic cancer": ("PANCREAS",),
    "pancreatic carcinoma": ("PANCREAS",),
    "pancreas cancer": ("PANCREAS",),
    "pancreatic ductal adenocarcinoma": ("PAAD",),
    "pancreas adenocarcinoma": ("PAAD",),
    "pancreatic solid pseudopapillary carcinoma": ("SPN",),
    # liver / biliary
    "liver cancer": ("LIVER",),
    "biliary tract cancer": ("BILIARY_TRACT",),
    # genitourinary
    "bladder cancer": ("BLADDER",),
    "urinary bladder cancer": ("BLADDER",),
    "prostate cancer": ("PROSTATE",),
    "kidney cancer": ("KIDNEY",),
    "renal cancer": ("KIDNEY",),
    "clear cell renal cell carcinoma": ("CCRCC",),
    # gynaecologic
    "ovarian cancer": ("OVARY",),
    "endometrial cancer": ("UCEC",),
    "uterine cancer": ("UTERUS",),
    "cervical cancer": ("CERVIX",),
    # other
    "thyroid cancer": ("THYROID",),
    "head and neck cancer": ("HEAD_NECK",),
    "gastric adenocarcinoma": ("STAD",),
    "chronic myeloid leukemia": ("CML",),
    "desmoid tumor": ("DES",),
    "aggressive fibromatosis": ("DES",),
    "soft tissue sarcoma": ("SOFT_TISSUE",),
}

# Disease Ontology identifiers (as carried on CIViC disease records) -> OncoTree
# candidate codes. The public OncoTree release carries only UMLS and NCI
# cross-references, so this table is the DOID bridge; every DOID label below
# was checked against the CIViC disease list (API or live records) on 2026-10-16. ``DOID:162``
# ("Cancer") is the pan-cancer sentinel. Mapping policy as for the synonyms:
# broad organ-level terms map to the organ node.
DOID_TO_ONCOTREE: dict[str, tuple[str, ...]] = {
    "DOID:162": (PAN_CANCER_CODE,),          # Cancer
    "DOID:9256": ("COADREAD",),              # Colorectal Cancer
    "DOID:3908": ("NSCLC",),                 # Lung Non-small Cell Carcinoma
    "DOID:1324": ("LUNG",),                  # Lung Cancer
    "DOID:3905": ("LUNG",),                  # Lung Carcinoma
    "DOID:3910": ("LUAD",),                  # Lung Adenocarcinoma
    "DOID:3907": ("LUSC",),                  # Lung Squamous Cell Carcinoma
    "DOID:5409": ("SCLC",),                  # Lung Small Cell Carcinoma
    "DOID:1909": ("MEL",),                   # Melanoma
    "DOID:8923": ("SKCM",),                  # Skin Melanoma
    "DOID:3068": ("GBM", "GB"),              # Glioblastoma
    "DOID:3073": ("GBM", "GB"),              # Brain Glioblastoma Multiforme
    "DOID:1319": ("CNS_BRAIN", "BRAIN"),     # Brain Cancer
    "DOID:0050902": ("MBL",),                # Medulloblastoma
    "DOID:3869": ("MBL",),                   # Childhood Medulloblastoma
    "DOID:684": ("HCC",),                    # Hepatocellular Carcinoma
    "DOID:3571": ("LIVER",),                 # Liver Cancer
    "DOID:4947": ("CHOL",),                  # Cholangiocarcinoma
    "DOID:1793": ("PANCREAS",),              # Pancreatic Cancer
    "DOID:4074": ("PAAD",),                  # Pancreatic Adenocarcinoma
    "DOID:6827": ("SPN",),                   # Pancreatic Solid Pseudopapillary Carcinoma
    "DOID:1612": ("BREAST",),                # Breast Cancer
    "DOID:3459": ("BRCA",),                  # Breast Carcinoma
    "DOID:11054": ("BLADDER",),              # Urinary Bladder Cancer
    "DOID:10283": ("PROSTATE",),             # Prostate Cancer
    "DOID:263": ("KIDNEY",),                 # Kidney Cancer
    "DOID:4450": ("RCC",),                   # Renal Cell Carcinoma
    "DOID:4467": ("CCRCC",),                 # Clear Cell Renal Cell Carcinoma
    "DOID:2394": ("OVARY",),                 # Ovarian Cancer
    "DOID:1380": ("UCEC",),                  # Endometrial Cancer
    "DOID:363": ("UTERUS",),                 # Uterine Cancer
    "DOID:4362": ("CERVIX",),                # Cervical Cancer
    "DOID:1781": ("THYROID",),               # Thyroid Cancer
    "DOID:11934": ("HEAD_NECK",),            # Head And Neck Cancer
    "DOID:5520": ("HNSC",),                  # Head And Neck Squamous Cell Carcinoma
    "DOID:3748": ("ESCC",),                  # Esophagus Squamous Cell Carcinoma
    "DOID:9119": ("AML",),                   # Acute Myeloid Leukemia
    "DOID:8552": ("CML",),                   # Chronic Myeloid Leukemia
    "DOID:9253": ("GIST",),                  # Gastrointestinal Stromal Tumor
    "DOID:0080366": ("DES",),                # Desmoid Tumor
}

ResolutionPath = Literal["code", "doid", "pan_cancer", "name", "synonym", "main_type", "name_ambiguous", "unresolved"]


class DiseaseResolution(_Model):
    """How an evidence disease label/identifier was mapped to an OncoTree code."""

    label: Optional[str] = None
    doid: Optional[str] = None
    code: Optional[str] = Field(default=None, description="Resolved OncoTree code, PAN_CANCER sentinel, or None.")
    path: ResolutionPath
    detail: Optional[str] = None


class DiseaseMatchResult(_Model):
    """``disease_match`` outcome with the resolution path kept for provenance."""

    match: DiseaseMatch
    case_code: Optional[str] = None
    evidence_code: Optional[str] = None
    resolution_path: ResolutionPath
    detail: Optional[str] = None


def _normalize_doid(doid: Optional[str]) -> Optional[str]:
    if not doid:
        return None
    s = doid.strip().upper().replace("DOID_", "DOID:")
    if s.isdigit():
        s = f"DOID:{s}"
    return s if s.startswith("DOID:") else None


class OncoTreeIndex(OncoTreeTable):
    """OncoTree lookups over the public ``tumorTypes`` JSON or the built-in subset.

    Adds to :class:`OncoTreeTable`: normalised-name index (ambiguity-aware),
    DOID index (``externalReferences.DOID`` when present, else the built-in
    ``DOID_TO_ONCOTREE`` bridge), synonym table, main-type fallback (a
    ``mainType`` label resolves to the lowest common ancestor of its nodes
    when that ancestor is below the root), ``tissue`` (tissue-level ancestor
    code) and :meth:`resolve_disease`, which records the resolution path.
    """

    def __init__(self, nodes: list[OncoTreeNode], source: str, *, version: Optional[str] = None,
                 sha256: Optional[str] = None, path: Optional[Path] = None):
        super().__init__(nodes, source)
        self.version = version
        self.sha256 = sha256
        self.path = path
        self._by_norm_name: dict[str, list[str]] = {}
        self._by_doid: dict[str, str] = {}
        self._by_main_type: dict[str, str] = {}
        by_main: dict[str, list[str]] = {}
        for n in nodes:
            code = n.code.upper()
            key = normalize_disease_name(n.name)
            bucket = self._by_norm_name.setdefault(key, [])
            if code not in bucket:
                bucket.append(code)
            for ref in n.external_references.get("DOID", []):
                d = _normalize_doid(ref)
                if d:
                    self._by_doid.setdefault(d, code)
            if n.main_type:
                by_main.setdefault(normalize_disease_name(n.main_type), []).append(code)
        for key, codes in by_main.items():
            lca = self._lowest_common_ancestor(codes)
            if lca and lca != ROOT_CODE:
                self._by_main_type[key] = lca

    # -- structure -------------------------------------------------------
    @property
    def node_count(self) -> int:
        return len(self._nodes)

    def codes(self) -> list[str]:
        return sorted(self._nodes)

    def tissue(self, code: str) -> Optional[str]:
        """Tissue-level ancestor code (the node directly under the root), or the code itself if tissue-level."""
        c = code.upper()
        if c == ROOT_CODE or c not in self._nodes:
            return None
        chain = [c] + [a for a in self.ancestors(c) if a != ROOT_CODE]
        return chain[-1]

    def _lowest_common_ancestor(self, codes: list[str]) -> Optional[str]:
        chains = []
        for c in codes:
            c = c.upper()
            if c not in self._nodes:
                continue
            chains.append([c] + self.ancestors(c))
        if not chains:
            return None
        common = set(chains[0])
        for ch in chains[1:]:
            common &= set(ch)
        for c in chains[0]:
            if c in common:
                return c
        return None

    # -- resolution ------------------------------------------------------
    def code_for_doid(self, doid: Optional[str]) -> Optional[str]:
        """OncoTree code (or ``PAN_CANCER``) for a DOID; file cross-references first, then the built-in bridge."""
        d = _normalize_doid(doid)
        if d is None:
            return None
        if d in self._by_doid:
            return self._by_doid[d]
        for cand in DOID_TO_ONCOTREE.get(d, ()):
            if cand == PAN_CANCER_CODE or cand.upper() in self._nodes:
                return cand
        return None

    def codes_for_name(self, name: str) -> list[str]:
        """All codes whose normalised name equals the normalised ``name`` (empty if none)."""
        return list(self._by_norm_name.get(normalize_disease_name(name), []))

    def _pick(self, codes: list[str], case_code: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        if len(codes) == 1:
            return codes[0], None
        if case_code:
            case_tissue = self.tissue(case_code)
            same = [c for c in codes if case_tissue and self.tissue(c) == case_tissue]
            if len(same) == 1:
                return same[0], f"ambiguous name; chose {same[0]} by case tissue among {'/'.join(codes)}"
        return None, f"ambiguous name: {'/'.join(codes)}"

    def resolve_disease(self, label: Optional[str], doid: Optional[str] = None,
                        case_code: Optional[str] = None) -> DiseaseResolution:
        """Resolve a label and/or DOID to a code, trying code, DOID, pan-cancer label, name, synonym,
        carcinoma/cancer variant and main type in that order."""
        raw = (label or "").strip()
        d = _normalize_doid(doid)
        if raw:
            up = raw.upper()
            if up == ROOT_CODE:
                return DiseaseResolution(label=raw, doid=d, code=PAN_CANCER_CODE, path="code", detail="root code")
            if up in self._nodes:
                return DiseaseResolution(label=raw, doid=d, code=up, path="code")
        if d:
            code = self.code_for_doid(d)
            if code:
                return DiseaseResolution(label=raw or None, doid=d, code=code, path="doid",
                                         detail="file cross-reference" if d in self._by_doid else "built-in DOID bridge")
        if not raw:
            return DiseaseResolution(label=None, doid=d, code=None, path="unresolved", detail="no label")
        key = normalize_disease_name(raw)
        if raw.lower() in PAN_CANCER_LABELS or key in PAN_CANCER_LABELS or key in {normalize_disease_name(x) for x in PAN_CANCER_LABELS}:
            return DiseaseResolution(label=raw, doid=d, code=PAN_CANCER_CODE, path="pan_cancer")
        if key in self._by_norm_name:
            code, detail = self._pick(self._by_norm_name[key], case_code)
            if code:
                return DiseaseResolution(label=raw, doid=d, code=code, path="name", detail=detail)
            return DiseaseResolution(label=raw, doid=d, code=None, path="name_ambiguous", detail=detail)
        for cand in DISEASE_NAME_SYNONYMS.get(key, ()):
            if cand.upper() in self._nodes:
                return DiseaseResolution(label=raw, doid=d, code=cand.upper(), path="synonym")
        variant = _carcinoma_cancer_variant(key)
        if variant and variant in self._by_norm_name:
            code, detail = self._pick(self._by_norm_name[variant], case_code)
            if code:
                return DiseaseResolution(label=raw, doid=d, code=code, path="name", detail=f"carcinoma/cancer variant '{variant}'")
        if key in self._by_main_type:
            return DiseaseResolution(label=raw, doid=d, code=self._by_main_type[key], path="main_type",
                                     detail="main type resolved to lowest common ancestor of its nodes")
        return DiseaseResolution(label=raw, doid=d, code=None, path="unresolved")

    @classmethod
    def from_table(cls, table: "OncoTreeTable") -> "OncoTreeIndex":
        if isinstance(table, cls):
            return table
        return cls(list(table._nodes.values()), source=table.source)


BUILTIN_ONCOTREE = OncoTreeIndex(
    [OncoTreeNode(code=c, name=n, parent=p) for c, n, p in _BUILTIN_NODES], source="builtin-subset"
)

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


_VERSION_FROM_NAME = re.compile(r"tumorTypes[_-](?P<version>.+)\.json$", re.IGNORECASE)


def oncotree_version_from_filename(path: str | Path) -> Optional[str]:
    """Version stamp embedded in a ``tumorTypes_<version>.json`` file name, else ``None``."""
    m = _VERSION_FROM_NAME.search(Path(path).name)
    return m.group("version") if m else None


def load_oncotree_json(path: str | Path) -> OncoTreeIndex:
    """Load the public OncoTree ``tumorTypes`` JSON into an :class:`OncoTreeIndex`.

    Expected format: a JSON array (as served by ``/api/tumorTypes``) of
    objects with keys ``code``, ``name``, ``parent`` (code or null),
    ``mainType``, ``tissue``, optionally ``level`` and ``externalReferences``
    (``{"UMLS": [...], "NCI": [...]}``; a ``DOID`` list is indexed when
    present). Either a flat array or an object with a top-level ``data``
    array is accepted. The file's sha256 and the version stamp from its
    name (``tumorTypes_<version>.json``) are recorded on the index.
    """
    path = Path(path)
    data = path.read_bytes()
    raw = json.loads(data.decode("utf-8"))
    if isinstance(raw, dict) and "data" in raw:
        raw = raw["data"]
    if not isinstance(raw, list):
        raise ValueError("OncoTree JSON must be an array of tumor types")
    nodes = []
    for item in raw:
        if not isinstance(item, dict) or "code" not in item or "name" not in item:
            raise ValueError("each OncoTree entry needs 'code' and 'name'")
        refs_raw = item.get("externalReferences") or {}
        refs = {str(k): [str(v) for v in vals] for k, vals in refs_raw.items() if isinstance(vals, list)} if isinstance(refs_raw, dict) else {}
        level = item.get("level")
        nodes.append(OncoTreeNode(code=str(item["code"]), name=str(item["name"]), parent=item.get("parent"),
                                  main_type=item.get("mainType"), tissue=item.get("tissue"),
                                  level=int(level) if isinstance(level, int) else None, external_references=refs))
    return OncoTreeIndex(nodes, source=str(path), version=oncotree_version_from_filename(path),
                         sha256=hashlib.sha256(data).hexdigest(), path=path)


def find_oncotree_json(reference_root: str | Path) -> Optional[Path]:
    """Locate the OncoTree file under ``<reference_root>/oncotree/``.

    ``tumorTypes.json`` wins if present; otherwise the newest
    ``tumorTypes_*.json`` by file name (version stamps such as
    ``oncotree_2025_10_03`` sort chronologically). ``None`` if nothing is there.
    """
    folder = Path(reference_root).expanduser() / "oncotree"
    if not folder.is_dir():
        return None
    plain = folder / "tumorTypes.json"
    if plain.is_file():
        return plain
    stamped = sorted(p for p in folder.glob("tumorTypes_*.json") if p.is_file())
    return stamped[-1] if stamped else None


def disease_match_detail(case_code: Optional[str], evidence_disease: Optional[str],
                         index: Optional[OncoTreeTable] = None, doid: Optional[str] = None) -> DiseaseMatchResult:
    """Relate an evidence disease (label and/or DOID) to the case OncoTree code, keeping the resolution path.

    Resolution order: OncoTree code, DOID, pan-cancer label, exact
    normalised name, synonym table, carcinoma/cancer variant, main type.
    Then: identical codes -> ``SAME`` (``PARENT`` when the evidence label was
    a main-type category rather than a node name); evidence code is an
    ancestor of the case code -> ``PARENT``; evidence code is a descendant of the case code,
    or both share a tissue-level ancestor -> ``RELATED``; pan-cancer sentinel
    -> ``PAN_CANCER``; both resolve with no shared tissue -> ``DIFFERENT``;
    anything unresolvable (either side) -> ``UNKNOWN``, never ``DIFFERENT``.
    """
    idx = OncoTreeIndex.from_table(index) if index is not None else BUILTIN_ONCOTREE
    case = case_code.strip().upper() if case_code and case_code.strip() else None
    if case is None:
        return DiseaseMatchResult(match=DiseaseMatch.UNKNOWN, resolution_path="unresolved", detail="case has no OncoTree code")
    if not (evidence_disease and evidence_disease.strip()) and not doid:
        return DiseaseMatchResult(match=DiseaseMatch.UNKNOWN, case_code=case, resolution_path="unresolved", detail="no evidence disease")
    res = idx.resolve_disease(evidence_disease, doid=doid, case_code=case)
    if res.code is None:
        return DiseaseMatchResult(match=DiseaseMatch.UNKNOWN, case_code=case, resolution_path=res.path, detail=res.detail)
    if res.code == PAN_CANCER_CODE:
        return DiseaseMatchResult(match=DiseaseMatch.PAN_CANCER, case_code=case, evidence_code=res.code, resolution_path=res.path, detail=res.detail)
    if res.code == case:
        if res.path == "main_type":
            # a main-type label is a category, never a specific entity: the strongest honest claim is containment
            return DiseaseMatchResult(match=DiseaseMatch.PARENT, case_code=case, evidence_code=res.code, resolution_path=res.path,
                                      detail="main-type category contains the case disease; reported as PARENT, not SAME")
        return DiseaseMatchResult(match=DiseaseMatch.SAME, case_code=case, evidence_code=res.code, resolution_path=res.path, detail=res.detail)
    if case not in idx:
        return DiseaseMatchResult(match=DiseaseMatch.UNKNOWN, case_code=case, evidence_code=res.code, resolution_path=res.path,
                                  detail=f"case code {case} not in OncoTree index ({idx.source})")
    if res.code in idx.ancestors(case):
        return DiseaseMatchResult(match=DiseaseMatch.PARENT, case_code=case, evidence_code=res.code, resolution_path=res.path, detail=res.detail)
    if case in idx.ancestors(res.code):
        return DiseaseMatchResult(match=DiseaseMatch.RELATED, case_code=case, evidence_code=res.code, resolution_path=res.path,
                                  detail="evidence disease is a descendant of the case disease")
    case_tissue = idx.tissue(case)
    if case_tissue is not None and case_tissue == idx.tissue(res.code):
        return DiseaseMatchResult(match=DiseaseMatch.RELATED, case_code=case, evidence_code=res.code, resolution_path=res.path,
                                  detail=f"same tissue ({case_tissue})")
    return DiseaseMatchResult(match=DiseaseMatch.DIFFERENT, case_code=case, evidence_code=res.code, resolution_path=res.path, detail=res.detail)


def disease_match(case_code: Optional[str], evidence_disease: Optional[str],
                  index: Optional[OncoTreeTable] = None, doid: Optional[str] = None) -> DiseaseMatch:
    """Relate an evidence disease label (code or name) to the case OncoTree code.

    Thin wrapper over :func:`disease_match_detail` returning only the
    :class:`DiseaseMatch`; see there for the rules. ``index`` defaults to the
    built-in subset.
    """
    return disease_match_detail(case_code, evidence_disease, index, doid=doid).match


def build_disease_context(case: Case, table: OncoTreeTable = BUILTIN_ONCOTREE) -> DiseaseContext:
    """Derive the disease context for a case without altering any recorded value."""
    table = OncoTreeIndex.from_table(table)
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
