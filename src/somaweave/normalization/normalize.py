"""Case normalization: structured views over a validated ``Case``.

``normalize_case`` never mutates or replaces recorded values. The original
``Case`` is carried inside the ``NormalizedCase`` unchanged, and every derived
field (parsed HGVS, normalized gene symbol, disease context, treatment
intervals) sits alongside it with its own provenance and flags.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from somaweave.domain import Assembly, Case, SpecimenRole
from somaweave.normalization.dates import DayInterval, PartialDate, days_between, parse_partial_date
from somaweave.normalization.disease import BUILTIN_ONCOTREE, DiseaseContext, OncoTreeTable, build_disease_context
from somaweave.normalization.genes import NormalizedGeneSymbol, normalize_gene_symbol
from somaweave.normalization.hgvs import ParsedCodingChange, ParsedProteinChange, parse_coding_hgvs, parse_protein_hgvs


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NormalizationFlag(_Model):
    code: str = Field(description="Machine-readable flag code.")
    severity: str = Field(description="'info', 'warning' or 'conflict'.")
    subject: str = Field(description="What the flag refers to, e.g. 'alteration:A1', 'diagnosis', 'treatment:TX1'.")
    message: str


class NormalizedAlteration(_Model):
    alteration_id: str
    gene: Optional[NormalizedGeneSymbol] = None
    protein: Optional[ParsedProteinChange] = None
    protein_parse_reason: Optional[str] = Field(default=None, description="Why hgvs_p could not be parsed, if applicable.")
    coding: Optional[ParsedCodingChange] = None
    coding_parse_reason: Optional[str] = None
    genomic: Optional[ParsedCodingChange] = None
    genomic_parse_reason: Optional[str] = None
    flags: list[NormalizationFlag] = Field(default_factory=list)


class SpecimenTiming(_Model):
    """Interval from a treatment to a specimen collection, when both dates exist."""

    specimen_id: str
    days_from_treatment_start: Optional[DayInterval] = None
    days_from_treatment_end: Optional[DayInterval] = None


class NormalizedTreatment(_Model):
    treatment_id: str
    start: Optional[PartialDate] = None
    end: Optional[PartialDate] = None
    duration: Optional[DayInterval] = None
    ongoing: Optional[bool] = None
    specimen_timing: list[SpecimenTiming] = Field(default_factory=list)


class NormalizedSpecimen(_Model):
    specimen_id: str
    collection: Optional[PartialDate] = None


class NormalizedCase(_Model):
    """Original case plus derived, provenance-tagged normalizations."""

    case: Case = Field(description="The validated input case, unchanged.")
    assembly: Assembly
    disease: DiseaseContext
    alterations: list[NormalizedAlteration] = Field(default_factory=list)
    treatments: list[NormalizedTreatment] = Field(default_factory=list)
    specimens: list[NormalizedSpecimen] = Field(default_factory=list)
    flags: list[NormalizationFlag] = Field(default_factory=list, description="All flags, including disease and per-alteration ones.")

    def alteration(self, alteration_id: str) -> NormalizedAlteration:
        for a in self.alterations:
            if a.alteration_id == alteration_id:
                return a
        raise KeyError(alteration_id)


def _normalize_alteration(alt, hgnc_previous: Optional[dict[str, str]]) -> NormalizedAlteration:
    subject = f"alteration:{alt.alteration_id}"
    flags: list[NormalizationFlag] = []
    gene = normalize_gene_symbol(alt.gene_symbol, hgnc_previous)
    if gene is not None and gene.alias_applied:
        flags.append(NormalizationFlag(code="gene_alias_applied", severity="info", subject=subject,
                                       message=f"gene symbol '{gene.original}' mapped to current symbol '{gene.normalized}' ({gene.alias_source})"))
    if gene is None and alt.alteration_type.value not in ("CNA", "SV", "fusion", "other"):
        flags.append(NormalizationFlag(code="gene_symbol_missing", severity="warning", subject=subject,
                                       message="small variant without a gene symbol; gene-level evidence retrieval not possible"))

    protein = coding = genomic = None
    p_reason = c_reason = g_reason = None
    if alt.hgvs_p is not None:
        protein, p_reason = parse_protein_hgvs(alt.hgvs_p)
        if protein is None:
            flags.append(NormalizationFlag(code="hgvs_p_unparsed", severity="warning", subject=subject,
                                           message=f"hgvs_p '{alt.hgvs_p}' not parsed: {p_reason}"))
        elif protein.predicted:
            flags.append(NormalizationFlag(code="hgvs_p_predicted", severity="info", subject=subject,
                                           message="protein change is stated as predicted (parentheses)"))
    if alt.hgvs_c is not None:
        coding, c_reason = parse_coding_hgvs(alt.hgvs_c)
        if coding is None:
            flags.append(NormalizationFlag(code="hgvs_c_unparsed", severity="warning", subject=subject,
                                           message=f"hgvs_c '{alt.hgvs_c}' not parsed: {c_reason}"))
        elif coding.prefix != "c":
            flags.append(NormalizationFlag(code="hgvs_c_prefix_mismatch", severity="warning", subject=subject,
                                           message=f"hgvs_c field carries a '{coding.prefix}.' expression"))
    if alt.hgvs_g is not None:
        genomic, g_reason = parse_coding_hgvs(alt.hgvs_g)
        if genomic is None:
            flags.append(NormalizationFlag(code="hgvs_g_unparsed", severity="warning", subject=subject,
                                           message=f"hgvs_g '{alt.hgvs_g}' not parsed: {g_reason}"))
        elif genomic.prefix != "g":
            flags.append(NormalizationFlag(code="hgvs_g_prefix_mismatch", severity="warning", subject=subject,
                                           message=f"hgvs_g field carries a '{genomic.prefix}.' expression"))
    if protein is not None and coding is not None and coding.prefix == "c" and coding.kind == "substitution":
        # codon arithmetic is a consistency check only; it does not alter either value
        expected_codon = (coding.start_base + 2) // 3 if coding.start_base > 0 and "+" not in coding.start and "-" not in coding.start[1:] else None
        if expected_codon is not None and expected_codon != protein.position:
            flags.append(NormalizationFlag(code="hgvs_c_p_codon_mismatch", severity="conflict", subject=subject,
                                           message=f"c.{coding.start} falls in codon {expected_codon} but hgvs_p states residue {protein.position}"))
    if alt.hgvs_p is None and alt.hgvs_c is None and alt.hgvs_g is None and alt.position is None \
            and alt.alteration_type.value in ("SNV", "MNV", "insertion", "deletion", "delins"):
        flags.append(NormalizationFlag(code="no_variant_description", severity="warning", subject=subject,
                                       message="no HGVS or genomic position available"))
    if alt.hgvs_p is not None and alt.transcript is None:
        flags.append(NormalizationFlag(code="transcript_missing", severity="info", subject=subject,
                                       message="protein change given without a transcript; residue numbering cannot be verified"))

    return NormalizedAlteration(
        alteration_id=alt.alteration_id, gene=gene, protein=protein, protein_parse_reason=p_reason,
        coding=coding, coding_parse_reason=c_reason, genomic=genomic, genomic_parse_reason=g_reason, flags=flags,
    )


def normalize_case(case: Case, oncotree: OncoTreeTable = BUILTIN_ONCOTREE,
                   hgnc_previous: Optional[dict[str, str]] = None) -> NormalizedCase:
    """Normalize a validated case.

    ``oncotree`` and ``hgnc_previous`` are optional external tables (see
    ``disease.load_oncotree_json`` and ``genes.load_hgnc_previous_symbols``);
    with the defaults only the built-in subsets are used.
    """
    flags: list[NormalizationFlag] = []

    disease = build_disease_context(case, oncotree)
    for f in disease.flags:
        flags.append(NormalizationFlag(code=f.code, severity=f.severity, subject="diagnosis", message=f.message))

    specimens: list[NormalizedSpecimen] = []
    for s in case.specimens:
        pd, _ = parse_partial_date(s.collection_date)
        specimens.append(NormalizedSpecimen(specimen_id=s.specimen_id, collection=pd))
        if pd is None:
            flags.append(NormalizationFlag(code="specimen_date_missing", severity="info", subject=f"specimen:{s.specimen_id}",
                                           message="no collection date; treatment-to-specimen chronology unavailable"))

    treatments: list[NormalizedTreatment] = []
    tumor_specimens = [sp for sp in specimens if case.specimen(sp.specimen_id).role == SpecimenRole.TUMOR]
    for t in case.treatments:
        start, _ = parse_partial_date(t.start_date)
        end, _ = parse_partial_date(t.end_date)
        duration = days_between(start, end) if start and end else None
        timing: list[SpecimenTiming] = []
        for sp in tumor_specimens:
            if sp.collection is None:
                continue
            timing.append(SpecimenTiming(
                specimen_id=sp.specimen_id,
                days_from_treatment_start=days_between(start, sp.collection) if start else None,
                days_from_treatment_end=days_between(end, sp.collection) if end else None,
            ))
        subj = f"treatment:{t.treatment_id}"
        if start is None:
            flags.append(NormalizationFlag(code="treatment_start_missing", severity="warning", subject=subj,
                                           message=f"treatment '{t.name}' has no start date"))
        if end is None and not t.ongoing:
            flags.append(NormalizationFlag(code="treatment_end_unknown", severity="info", subject=subj,
                                           message=f"treatment '{t.name}' has no end date and is not marked ongoing"))
        if end is not None and t.ongoing:
            flags.append(NormalizationFlag(code="treatment_end_vs_ongoing", severity="conflict", subject=subj,
                                           message=f"treatment '{t.name}' has an end date but is marked ongoing"))
        treatments.append(NormalizedTreatment(treatment_id=t.treatment_id, start=start, end=end, duration=duration,
                                              ongoing=t.ongoing, specimen_timing=timing))

    alterations = [_normalize_alteration(a, hgnc_previous) for a in case.alterations]
    for a in alterations:
        flags.extend(a.flags)

    return NormalizedCase(case=case, assembly=case.assembly, disease=disease, alterations=alterations,
                          treatments=treatments, specimens=specimens, flags=flags)
