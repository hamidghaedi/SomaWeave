"""gnomAD v4 GraphQL exact GRCh38 allele frequencies (joint adjusted counts).

The browser dataset selector is ``gnomad_r4``; the API does not pin a minor
release, so the dataset and retrieval date are recorded without inventing one.
Never sum overlapping exome/genome cohorts. Preserve the joint counts in the
canonical record and the full response in cache. Major ancestry populations
are the nine named v4 groups below; sex strata and 'remaining' are not popmax.
No hit, zero AC, or missing joint counts never supplies oncogenic evidence.
No liftover, indel normalisation or REF substitution is performed here.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field

from somaweave.domain import EvidenceCategory, EvidenceRecord, MatchSpecificity, SourceStatus
from somaweave.domain.evidence import PopulationFrequency
from somaweave.providers.base import PayloadCache, Provider, ProviderConfig, TransportRequest

QUERY = """query Variant($variantId: String!, $dataset: DatasetId!) {
  variant(variantId: $variantId, dataset: $dataset) {
    ref alt variantId joint { ac an populations { id ac an } }
  }
}"""
MAJOR_POPULATIONS = frozenset({"afr", "amr", "asj", "ami", "eas", "fin", "mid", "nfe", "sas"})


class GnomADConfig(ProviderConfig):
    dataset: Literal["gnomad_r4"] = "gnomad_r4"
    rate_limit_per_s: float = Field(default=1 / 6, gt=0, le=1 / 6)
    burst: int = Field(default=1, ge=1, le=1)


class GnomADProvider(Provider):
    name = "gnomad"
    config_model = GnomADConfig

    def __init__(self, config, **kwargs):
        if not isinstance(config, GnomADConfig):
            config = GnomADConfig.model_validate(config.model_dump(exclude_unset=True))
        super().__init__(config, **kwargs)

    @staticmethod
    def variant_id(item):
        t = item.terms
        if item.tier != MatchSpecificity.EXACT_VARIANT or t.get("assembly") != "GRCh38":
            return None
        if t.get("alteration_type") not in {"SNV", "MNV", "insertion", "deletion", "delins"}:
            return None
        chrom = str(t.get("chromosome") or "").removeprefix("chr")
        pos, ref, alt = t.get("position"), t.get("ref"), t.get("alt")
        if chrom not in {str(i) for i in range(1, 23)} | {"X", "Y"} or not isinstance(pos, int) or pos < 1:
            return None
        if not all(isinstance(a, str) and re.fullmatch("[ACGT]+", a) for a in (ref, alt)) or ref == alt:
            return None
        return f"{chrom}-{pos}-{ref}-{alt}"

    def supports(self, plan_item):
        return self.variant_id(plan_item) is not None

    def version(self):
        return self.config.dataset

    def _execute(self, plan_item, query, retrieved_at, cache: PayloadCache | None):
        variant_id = self.variant_id(plan_item)
        request = TransportRequest(method="POST", url=self.config.base_url,
                                   json_body={"query": QUERY, "variables": {"variantId": variant_id, "dataset": self.config.dataset}},
                                   headers=self._headers(), timeout_s=self.config.timeout_s)
        native = request.native_request()
        query = query.model_copy(update={"native_request": native})
        key = PayloadCache.key_for(native)
        cached = cache.get(self.name, key) if cache else None
        raw_ref = cache.reference(self.name, key) if cached else None
        if cached and cached.get("payloads"):
            payload = cached["payloads"][0]
        else:
            payload = self._send(request).json()
        if not isinstance(payload, dict):
            raise ValueError("gnomAD response is not an object")
        errors = payload.get("errors") or []
        if errors and all(e.get("message") == "Service overloaded" for e in errors):
            return self._result(query, SourceStatus.UNAVAILABLE, retrieved_at, source_version=self.version(),
                                message="gnomAD GraphQL service overloaded; frequency evidence missing"), []
        # The v4 service represents true absence as a GraphQL UserVisibleError.
        # Match only its exact documented messages; never turn arbitrary errors
        # or partial data into no_records, and never cache failure payloads.
        absent = {"Variant not found", "Variant not found in selected subset."}
        if errors and not all(e.get("message") in absent for e in errors):
            raise ValueError("gnomAD GraphQL errors: " + "; ".join(str(e.get("message")) for e in errors))
        if cache and not cached:
            raw_ref = cache.put(self.name, key, native, [payload])
        variant = (payload.get("data") or {}).get("variant")
        if variant is None:
            if not errors and "variant" not in (payload.get("data") or {}):
                raise ValueError("gnomAD response missing data.variant")
            return self._result(query, SourceStatus.NO_RECORDS, retrieved_at, source_version=self.version(),
                                message="Exact allele absent from this dataset; absence is not evidence of oncogenicity"), []
        if errors:
            raise ValueError("gnomAD returned partial data with errors")
        expected_ref, expected_alt = variant_id.split("-")[2:]
        if (variant.get("variantId"), variant.get("ref"), variant.get("alt")) != (variant_id, expected_ref, expected_alt):
            raise ValueError("gnomAD returned a different genomic allele")
        joint = variant.get("joint")
        if not joint:
            raise ValueError("Exact allele found but joint counts unavailable; frequency unassessed")
        ac, an = joint.get("ac"), joint.get("an")
        if not isinstance(ac, int) or not isinstance(an, int) or an <= 0 or not 0 <= ac <= an:
            raise ValueError("Invalid or missing joint allele counts")
        populations = {}
        for pop in joint.get("populations") or []:
            if pop.get("id") not in MAJOR_POPULATIONS:
                continue
            pa, pn = pop.get("ac"), pop.get("an")
            if isinstance(pa, int) and isinstance(pn, int) and pn > 0 and 0 <= pa <= pn:
                populations[pop["id"]] = pa / pn
            elif pn not in (None, 0):
                raise ValueError("Invalid ancestry population counts")
        maximum = max(populations, key=populations.get) if populations else None
        freq = PopulationFrequency(dataset=self.version(), allele_count=ac, allele_number=an, overall_af=ac / an,
                                   populations=populations, max_population=maximum,
                                   max_population_af=populations.get(maximum))
        pop_text = f"{freq.max_population_af:.8g} ({maximum})" if maximum else "unavailable"
        record = EvidenceRecord(
            evidence_id=f"gnomad:{self.version()}:{variant_id}:frequency", source_name=self.name,
            source_native_id=variant_id, source_url=f"https://gnomad.broadinstitute.org/variant/{variant_id}?dataset={self.version()}",
            source_version=self.version(), retrieved_at=retrieved_at, query_tier=plan_item.tier,
            variant_match=MatchSpecificity.EXACT_VARIANT, gene_symbol=plan_item.terms.get("gene"),
            variant_description=f"GRCh38 {variant_id}", evidence_category=EvidenceCategory.EPIDEMIOLOGIC,
            population_frequency=freq, assertion=f"gnomAD AF {freq.overall_af:.8g} (AC={ac}, AN={an}); "
            f"maximum major-population AF {pop_text}; dataset {self.version()}",
            limitations=["Population frequency is context, not proof of germline origin or somatic oncogenicity",
                         "Browser v4 selector does not pin minor releases; raw payload and retrieval timestamp retained"],
            raw_reference=raw_ref)
        return self._result(query, SourceStatus.OK, retrieved_at, records=[record], source_version=self.version(),
                            message=f"served from cache written {cached.get('cached_at')}" if cached else None), [record]
