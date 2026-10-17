"""Genomic alteration models.

Raw tumour and normal counts, template-level support and QC flags are kept
separately from any derived allele fraction. Derived values (VAF, expected VAF,
clonality) are computed in ``somaweave.technical`` and never stored here as if
they were measurements.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from somaweave.domain.enums import AlterationType, Assembly
from somaweave.domain.dates import FlexibleDate


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GenomicPosition(_Model):
    assembly: Assembly
    chromosome: str = Field(description="Chromosome name as reported (e.g. '7' or 'chr7').")
    position: int = Field(ge=1, description="1-based start position of the reference allele.")
    reference: str = Field(description="Reference allele; '-' is not allowed, use VCF-style anchoring.")
    alternate: str = Field(description="Alternate allele; VCF-style anchoring.")
    end: Optional[int] = Field(default=None, ge=1, description="End position for CNA/SV intervals.")


class VisualReview(_Model):
    """Upstream visual observation, quoted without reclassifying its wording."""

    outcome: str
    reviewer_role: Optional[str] = None
    note: Optional[str] = None
    reviewed_at: Optional[FlexibleDate] = None


class ReadSupport(_Model):
    """Raw read/template support for one allele in one specimen."""

    ref_count: Optional[int] = Field(default=None, ge=0)
    alt_count: Optional[int] = Field(default=None, ge=0)
    depth: Optional[int] = Field(default=None, ge=0, description="Total depth at the site if reported separately.")
    alt_forward: Optional[int] = Field(default=None, ge=0)
    alt_reverse: Optional[int] = Field(default=None, ge=0)
    ref_forward: Optional[int] = Field(default=None, ge=0)
    ref_reverse: Optional[int] = Field(default=None, ge=0)
    unique_templates_alt: Optional[int] = Field(default=None, ge=0, description="Independent (deduplicated) templates supporting ALT.")
    unique_templates_ref: Optional[int] = Field(default=None, ge=0, description="Independent templates supporting REF.")
    unique_templates_total: Optional[int] = Field(default=None, ge=0, description="Independent templates covering the site, if reported separately.")
    alt_templates_forward: Optional[int] = Field(default=None, ge=0, description="ALT-supporting templates on the forward strand (template-level, may be non-exclusive with reverse).")
    alt_templates_reverse: Optional[int] = Field(default=None, ge=0)
    alt_templates_strand_exclusive: Optional[bool] = Field(default=None, description="False when a template may contribute to both strand counts; the binomial p-value is then nominal, not independent evidence.")
    duplex_templates_alt: Optional[int] = Field(default=None, ge=0)
    mean_mapq: Optional[float] = Field(default=None, ge=0)
    median_mapq: Optional[float] = Field(default=None, ge=0, description="Median MAPQ of ALT reads when a mean is not reported.")
    mean_baseq_alt: Optional[float] = Field(default=None, ge=0)
    median_baseq_alt: Optional[float] = Field(default=None, ge=0)
    clipped_fraction_alt: Optional[float] = Field(default=None, ge=0, le=1, description="Fraction of ALT templates (or reads) clipped near the site, as measured upstream; the measurement window and unit are the source's.")
    local_mismatch_alt: Optional[float] = Field(default=None, ge=0, description="Additional mismatches per ALT template/read near the site (statistic as reported; see local_mismatch_statistic).")
    local_mismatch_statistic: Optional[str] = Field(default=None, description="Which statistic local_mismatch_alt is: 'mean', 'median' or another label as reported.")
    review_outcome: Optional[str] = Field(default=None, description="Outcome of manual read review as recorded upstream (e.g. 'artifact', 'supported'); quoted, not interpreted.")
    visual_review: Optional[VisualReview] = None
    reported_vaf: Optional[float] = Field(default=None, ge=0, le=1, description="Caller-reported VAF, retained as-is; not used in place of counts.")

    @model_validator(mode="after")
    def _counts_consistent(self) -> "ReadSupport":
        if self.depth is not None and self.ref_count is not None and self.alt_count is not None:
            if self.ref_count + self.alt_count > self.depth:
                raise ValueError("ref_count + alt_count cannot exceed depth")
        return self


class CopyNumberState(_Model):
    """Caller-reported copy-number context for the alteration locus."""

    total_copy_number: Optional[float] = Field(default=None, ge=0)
    minor_allele_copy_number: Optional[float] = Field(default=None, ge=0)
    major_allele_copy_number: Optional[float] = Field(default=None, ge=0)
    caller_reported_loh: Optional[bool] = Field(default=None, description="Deprecated: use loh_call and loh_source. Original caller Boolean retained for v1 compatibility; never inferred from VAF.")
    loh_call: Optional[Literal['loh', 'no_loh', 'not_called']] = None
    loh_source: Optional[str] = None
    source_tool: Optional[str] = None


class AlterationMeasurement(_Model):
    """Measurements for one alteration in one specimen."""

    specimen_id: str
    tumor: Optional[ReadSupport] = None
    normal: Optional[ReadSupport] = None
    copy_number: Optional[CopyNumberState] = None
    caller: Optional[str] = Field(default=None, description="Variant caller name and version.")
    caller_filters: list[str] = Field(default_factory=list, description="FILTER values as emitted by the caller.")
    qc_flags: list[str] = Field(default_factory=list, description="Free-form upstream QC flags (e.g. 'orientation_bias', 'low_mapq').")


class FusionPartner(_Model):
    gene_symbol: str
    breakpoint: Optional[GenomicPosition] = None
    exon: Optional[int] = None


class Alteration(_Model):
    alteration_id: str
    alteration_type: AlterationType
    gene_symbol: Optional[str] = Field(default=None, description="HGNC symbol as reported.")
    hgnc_id: Optional[str] = None
    transcript: Optional[str] = Field(default=None, description="Transcript accession with version, e.g. NM_001904.4.")
    exon: Optional[int] = Field(default=None, ge=1)
    exon_count: Optional[int] = Field(default=None, ge=1)
    region_source: Optional[str] = Field(default=None, description="Transcript and annotation source that supplied the exon assignment; preserve source numbering.")
    hgvs_g: Optional[str] = None
    hgvs_c: Optional[str] = None
    hgvs_p: Optional[str] = Field(default=None, description="Protein HGVS, three-letter preferred, e.g. p.Asp32Asn.")
    consequence: Optional[str] = Field(default=None, description="Sequence Ontology term as reported, e.g. missense_variant.")
    position: Optional[GenomicPosition] = None
    fusion_partners: list[FusionPartner] = Field(default_factory=list)
    copy_number_call: Optional[str] = Field(default=None, description="For CNA: amplification, gain, loss, deep_deletion, etc.")
    measurements: list[AlterationMeasurement] = Field(default_factory=list)
    annotations: dict[str, str] = Field(default_factory=dict, description="Upstream annotations retained verbatim (key -> value).")
    notes: Optional[str] = None

    def consequence_class(self) -> Optional[str]:
        """Coarse functional class derived from the reported consequence term
        and protein HGVS: 'truncating', 'splice', 'missense', 'inframe',
        'synonymous', 'other', or None when nothing is reported. Used to judge
        whether class-level evidence (e.g. 'truncating mutations') applies."""
        c = (self.consequence or "").lower()
        p = (self.hgvs_p or "")
        if any(k in c for k in ("stop_gained", "frameshift", "start_lost", "stop_lost", "nonsense")) or "fs" in p or p.endswith("*") or "Ter" in p:
            return "truncating"
        # Only donor/acceptor disruption counts as splice; 'splice_region_variant' alongside a coding term is not.
        if "splice_acceptor" in c or "splice_donor" in c or ("splice" in c and "missense" not in c and "synonymous" not in c and "splice_region" not in c):
            return "splice"
        if "synonymous" in c or p.endswith("="):
            return "synonymous"
        if "missense" in c:
            return "missense"
        if "splice_region" in c:
            return "other"
        if "inframe" in c or ("del" in p or "dup" in p or "ins" in p):
            return "inframe"
        if c or p:
            return "other"
        return None

    @model_validator(mode="after")
    def _identity_present(self) -> "Alteration":
        if self.exon is not None and self.exon_count is not None and self.exon > self.exon_count:
            raise ValueError('exon cannot exceed exon_count')
        if self.alteration_type in {AlterationType.SNV, AlterationType.MNV, AlterationType.INSERTION,
                                    AlterationType.DELETION, AlterationType.DELINS}:
            if self.position is None and not (self.hgvs_g or self.hgvs_c or self.hgvs_p):
                raise ValueError("small variants need a genomic position or at least one HGVS expression")
        if self.alteration_type == AlterationType.FUSION and len(self.fusion_partners) < 1 and not self.gene_symbol:
            raise ValueError("fusions need fusion_partners or a gene_symbol")
        return self
