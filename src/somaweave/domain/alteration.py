"""Genomic alteration models.

Raw tumour and normal counts, template-level support and QC flags are kept
separately from any derived allele fraction. Derived values (VAF, expected VAF,
clonality) are computed in ``somaweave.technical`` and never stored here as if
they were measurements.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from somaweave.domain.enums import AlterationType, Assembly


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GenomicPosition(_Model):
    assembly: Assembly
    chromosome: str = Field(description="Chromosome name as reported (e.g. '7' or 'chr7').")
    position: int = Field(ge=1, description="1-based start position of the reference allele.")
    reference: str = Field(description="Reference allele; '-' is not allowed, use VCF-style anchoring.")
    alternate: str = Field(description="Alternate allele; VCF-style anchoring.")
    end: Optional[int] = Field(default=None, ge=1, description="End position for CNA/SV intervals.")


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
    duplex_templates_alt: Optional[int] = Field(default=None, ge=0)
    mean_mapq: Optional[float] = Field(default=None, ge=0)
    mean_baseq_alt: Optional[float] = Field(default=None, ge=0)
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
    caller_reported_loh: Optional[bool] = Field(default=None, description="LOH as called by the CNA tool. Never inferred from VAF.")
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

    @model_validator(mode="after")
    def _identity_present(self) -> "Alteration":
        if self.alteration_type in {AlterationType.SNV, AlterationType.MNV, AlterationType.INSERTION,
                                    AlterationType.DELETION, AlterationType.DELINS}:
            if self.position is None and not (self.hgvs_g or self.hgvs_c or self.hgvs_p):
                raise ValueError("small variants need a genomic position or at least one HGVS expression")
        if self.alteration_type == AlterationType.FUSION and len(self.fusion_partners) < 1 and not self.gene_symbol:
            raise ValueError("fusions need fusion_partners or a gene_symbol")
        return self
