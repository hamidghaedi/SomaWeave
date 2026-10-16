"""Europe PMC adapter (REST search, https://www.ebi.ac.uk/europepmc/webservices/rest/search).

Literature hits are *citations*, not curated assertions. Every record is
therefore ``is_hypothesis=True`` with ``assertion`` equal to the article title
and a ``literature_text_match_not_curated`` limitation. The query string is
built per tier:

* exact variant : gene AND (variant synonyms)
* codon         : gene AND (codon terms)
* gene class    : gene AND alteration class AND disease
* gene          : gene AND disease
* pathway       : pathway AND disease
* disease only  : disease AND (treatment agents) AND (resistance/response terms)

``variant_match`` equals the tier that produced the hit. ``evidence_category``
is ``MECHANISTIC`` for variant/codon/pathway tiers and ``OTHER`` otherwise;
this labels the search tier, not the article content. The total hit count is
recorded in ``SourceQueryResult.message``; returned records are capped by
``max_records`` (default 25).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from somaweave.domain import (
    Citation,
    DiseaseMatch,
    DiseaseReference,
    EvidenceCategory,
    EvidenceDirection,
    EvidenceRecord,
    MatchSpecificity,
    SourceQuery,
    SourceQueryResult,
    SourceStatus,
)
from somaweave.providers.base import PayloadCache, Provider, TransportRequest, utc_date_version

LITERATURE_LIMITATION = "literature_text_match_not_curated"
MECHANISTIC_TIERS = {MatchSpecificity.EXACT_VARIANT, MatchSpecificity.CODON, MatchSpecificity.PATHWAY}


def _phrase(term: str) -> str:
    term = str(term).replace('"', "")
    return f'"{term}"'


def _any_of(terms: list[str]) -> str:
    uniq: list[str] = []
    for t in terms:
        if t and t not in uniq:
            uniq.append(t)
    return "(" + " OR ".join(_phrase(t) for t in uniq) + ")"


def build_epmc_query(plan_item: Any) -> Optional[str]:
    """Deterministic Europe PMC query string for a plan item, or ``None`` if not formable."""
    t = plan_item.terms
    gene = t.get("gene")
    disease_terms = list(t.get("disease_terms") or ([t["disease"]] if t.get("disease") else []))
    tier = plan_item.tier
    if tier == MatchSpecificity.EXACT_VARIANT:
        variants = list(t.get("variant_terms") or [])
        if not (gene and variants):
            return None
        return f"{_phrase(gene)} AND {_any_of(variants)}"
    if tier == MatchSpecificity.CODON:
        codons = list(t.get("codon_terms") or ([t["codon"]] if t.get("codon") else []))
        if not (gene and codons):
            return None
        pos = t.get("codon_position")
        if pos:
            codons.append(f"codon {pos}")
        return f"{_phrase(gene)} AND {_any_of(codons)}"
    if tier == MatchSpecificity.GENE_ALTERATION_CLASS:
        cls = t.get("alteration_class")
        if not (gene and cls and disease_terms):
            return None
        return f"{_phrase(gene)} AND {_phrase(cls)} AND {_any_of(disease_terms)}"
    if tier == MatchSpecificity.GENE:
        if not (gene and disease_terms):
            return None
        return f"{_phrase(gene)} AND {_any_of(disease_terms)}"
    if tier == MatchSpecificity.PATHWAY:
        pathway = t.get("pathway")
        if not (pathway and disease_terms):
            return None
        return f"{_phrase(pathway + ' pathway')} AND {_any_of(disease_terms)}"
    if tier == MatchSpecificity.DISEASE_ONLY:
        treatments = list(t.get("treatments") or [])
        outcomes = list(t.get("outcome_terms") or ["resistance", "response"])
        if not (disease_terms and treatments):
            return None
        return f"{_any_of(disease_terms)} AND {_any_of(treatments)} AND {_any_of(outcomes)}"
    return None


class EuropePMCProvider(Provider):
    name = "europepmc"
    requires_api_key = False

    def version(self) -> Optional[str]:
        return None  # taken from the response 'version' field

    def supports(self, plan_item: Any) -> bool:
        return build_epmc_query(plan_item) is not None

    def _execute(self, plan_item: Any, query: SourceQuery, retrieved_at: datetime,
                 cache: PayloadCache | None) -> tuple[SourceQueryResult, list[EvidenceRecord]]:
        q = build_epmc_query(plan_item)
        assert q is not None
        request = TransportRequest(
            method="GET", url=self.config.base_url, headers=self._headers(), timeout_s=self.config.timeout_s,
            params={"query": q, "format": "json", "resultType": "lite", "pageSize": self.config.max_records, "sort": "CITED desc"},
        )
        native = request.native_request()
        query = query.model_copy(update={"native_request": native})
        cache_key = PayloadCache.key_for(native)
        notes: list[str] = []
        raw_ref: Optional[str] = None
        cached = cache.get(self.name, cache_key) if cache else None
        if cached is not None:
            payload = cached["payloads"][0]
            raw_ref = cache.reference(self.name, cache_key)  # type: ignore[union-attr]
            notes.append(f"served from cache written {cached.get('cached_at')}")
        else:
            payload = self._send(request).json()
            if cache is not None:
                raw_ref = cache.put(self.name, cache_key, native, [payload])
        api_version = payload.get("version")
        version = f"europepmc-api:{api_version}" if api_version else utc_date_version(retrieved_at)
        hit_count = int(payload.get("hitCount") or 0)
        results = ((payload.get("resultList") or {}).get("result") or [])[: self.config.max_records]
        records = [self._map_hit(h, plan_item, version, retrieved_at, raw_ref) for h in results]
        notes.insert(0, f"total_hits={hit_count}; returned={len(records)}; query={q}")
        status = SourceStatus.OK if records else SourceStatus.NO_RECORDS
        return self._result(query, status, retrieved_at, records=records, source_version=version, message="; ".join(notes)), records

    def _map_hit(self, hit: dict[str, Any], plan_item: Any, version: str, retrieved_at: datetime,
                 raw_ref: Optional[str]) -> EvidenceRecord:
        src = hit.get("source") or "MED"
        native_id = f"{src}:{hit.get('id')}"
        pmid = hit.get("pmid")
        pmcid = hit.get("pmcid")
        year = hit.get("pubYear")
        url = f"https://europepmc.org/article/{src}/{hit.get('id')}"
        title = (hit.get("title") or "").strip().rstrip(".") or "(untitled)"
        t = plan_item.terms
        disease = DiseaseReference(name=t["disease"], oncotree_code=t.get("oncotree_code")) if t.get("disease") else None
        limitations = [LITERATURE_LIMITATION]
        if plan_item.tier in (MatchSpecificity.EXACT_VARIANT, MatchSpecificity.CODON):
            limitations.append("disease_not_constrained_in_query")
        if plan_item.tier in (MatchSpecificity.PATHWAY, MatchSpecificity.DISEASE_ONLY):
            limitations.append("not_gene_specific")
        return EvidenceRecord(
            evidence_id=f"europepmc:{native_id}",
            source_name=self.name,
            source_native_id=native_id,
            source_url=url,
            source_version=version,
            retrieved_at=retrieved_at,
            query_tier=plan_item.tier,
            variant_match=plan_item.tier,
            disease_match=DiseaseMatch.UNKNOWN,
            gene_symbol=t.get("gene"),
            variant_description=t.get("protein_change") if plan_item.tier == MatchSpecificity.EXACT_VARIANT else t.get("codon"),
            disease=disease,
            evidence_category=EvidenceCategory.MECHANISTIC if plan_item.tier in MECHANISTIC_TIERS else EvidenceCategory.OTHER,
            assertion=title,
            direction=EvidenceDirection.NOT_APPLICABLE,
            citations=[Citation(pmid=str(pmid) if pmid else None, pmcid=pmcid, doi=hit.get("doi"), url=url, title=title,
                                year=int(year) if year and str(year).isdigit() else None,
                                source_label=f"Europe PMC ({src})")],
            limitations=limitations,
            is_hypothesis=True,
            raw_reference=raw_ref,
        )
