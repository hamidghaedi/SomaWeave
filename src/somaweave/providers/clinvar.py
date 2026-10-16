"""ClinVar adapter via NCBI E-utilities (esearch + esummary, ``db=clinvar``).

The search term is ``"<gene>[gene] AND <protein_change>"``. Each ClinVar
variation record (VCV) carries up to three independent classification blocks
in the esummary payload:

* ``germline_classification``         -> ``EvidenceCategory.OTHER`` (germline oriented)
* ``clinical_impact_classification``  -> ``EvidenceCategory.OTHER`` (somatic clinical impact; AMP tier text kept natively)
* ``oncogenicity_classification``     -> ``EvidenceCategory.ONCOGENIC``

One ``EvidenceRecord`` is emitted per non-empty block. ``source_native_id`` is
``"<VCV accession>#<block>"`` so the three axes survive de-duplication.
``variant_match`` is ``EXACT_VARIANT`` only when the query protein change (or
its three-letter form) appears in the record title or ``protein_change``
field. ClinVar exposes no release id in esummary, so the retrieval date is the
version. An optional NCBI API key is read from the configured environment
variable; without it the rate limit is capped at 3 requests/s as NCBI requires.
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
from somaweave.providers.base import PayloadCache, Provider, ProviderConfig, TokenBucket, Transport, TransportRequest, utc_date_version

NCBI_RATE_WITHOUT_KEY = 3.0
GERMLINE_LIMITATION = "clinvar_is_germline_oriented"
BLOCKS = (
    ("germline_classification", EvidenceCategory.OTHER, "germline classification"),
    ("clinical_impact_classification", EvidenceCategory.OTHER, "somatic clinical impact classification"),
    ("oncogenicity_classification", EvidenceCategory.ONCOGENIC, "oncogenicity classification"),
)


class ClinVarProvider(Provider):
    name = "clinvar"
    requires_api_key = False

    def __init__(self, config: ProviderConfig, transport: Transport | None = None, **kwargs: Any):
        if config.rate_limit_per_s > NCBI_RATE_WITHOUT_KEY and not (config.api_key_env and _env_set(config.api_key_env)):
            config = config.model_copy(update={"rate_limit_per_s": NCBI_RATE_WITHOUT_KEY})
        super().__init__(config, transport, **kwargs)

    def version(self) -> Optional[str]:
        return None

    @staticmethod
    def search_term(plan_item: Any) -> Optional[str]:
        t = plan_item.terms
        if plan_item.tier != MatchSpecificity.EXACT_VARIANT or not t.get("gene") or not t.get("protein_change"):
            return None
        return f"{t['gene']}[gene] AND {t['protein_change']}"

    def supports(self, plan_item: Any) -> bool:
        return self.search_term(plan_item) is not None

    def _base_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {"db": "clinvar", "retmode": "json", "tool": "somaweave"}
        key = self.api_key()
        if key:
            params["api_key"] = key
        return params

    def _execute(self, plan_item: Any, query: SourceQuery, retrieved_at: datetime,
                 cache: PayloadCache | None) -> tuple[SourceQueryResult, list[EvidenceRecord]]:
        term = self.search_term(plan_item)
        assert term is not None
        base = self.config.base_url.rstrip("/")
        search_req = TransportRequest(method="GET", url=f"{base}/esearch.fcgi", headers=self._headers(), timeout_s=self.config.timeout_s,
                                      params={**self._base_params(), "term": term, "retmax": self.config.max_records})
        native = search_req.native_request(redact={"api_key": "<redacted>"})
        query = query.model_copy(update={"native_request": native})
        cache_key = PayloadCache.key_for(native)
        payloads: list[Any] = []
        raw_ref: Optional[str] = None
        notes: list[str] = []
        cached = cache.get(self.name, cache_key) if cache else None
        if cached is not None:
            payloads = list(cached.get("payloads", []))
            raw_ref = cache.reference(self.name, cache_key)  # type: ignore[union-attr]
            notes.append(f"served from cache written {cached.get('cached_at')}")
        else:
            search = self._send(search_req).json()
            payloads.append(search)
            ids = list((search.get("esearchresult") or {}).get("idlist") or [])
            if ids:
                summary_req = TransportRequest(method="GET", url=f"{base}/esummary.fcgi", headers=self._headers(), timeout_s=self.config.timeout_s,
                                               params={**self._base_params(), "id": ",".join(ids)})
                payloads.append(self._send(summary_req).json())
            if cache is not None:
                raw_ref = cache.put(self.name, cache_key, native, payloads)

        version = utc_date_version(retrieved_at)
        es = payloads[0].get("esearchresult") or {}
        if "ERROR" in es:
            raise ValueError(f"esearch error: {es['ERROR']}")
        total = int(es.get("count") or 0)
        records: list[EvidenceRecord] = []
        if len(payloads) > 1:
            result = payloads[1].get("result") or {}
            for uid in result.get("uids") or []:
                records.extend(self._map_variation(result[uid], plan_item, version, retrieved_at, raw_ref))
        if total > len(es.get("idlist") or []):
            notes.append(f"{total} ClinVar variations matched, {len(es.get('idlist') or [])} retrieved (max_records={self.config.max_records})")
        status = SourceStatus.OK if records else SourceStatus.NO_RECORDS
        if not records:
            notes.append(f"no ClinVar variations for term {term!r}" if total == 0 else "ClinVar variations found but no classification blocks populated")
        return self._result(query, status, retrieved_at, records=records, source_version=version, message="; ".join(notes) or None), records

    def _map_variation(self, rec: dict[str, Any], plan_item: Any, version: str, retrieved_at: datetime,
                       raw_ref: Optional[str]) -> list[EvidenceRecord]:
        accession = rec.get("accession") or f"uid{rec.get('uid')}"
        title = rec.get("title") or ""
        protein_field = rec.get("protein_change") or ""
        pc = plan_item.terms.get("protein_change") or ""
        synonyms = {s for s in plan_item.terms.get("variant_terms", []) if s} | {pc}
        exact = any(s and (s in title or s in [x.strip() for x in protein_field.split(",")]) for s in synonyms)
        variant_match = MatchSpecificity.EXACT_VARIANT if exact else MatchSpecificity.GENE
        genes = [g.get("symbol") for g in rec.get("genes") or [] if g.get("symbol")]
        gene = plan_item.terms.get("gene") if plan_item.terms.get("gene") in genes else (genes[0] if genes else plan_item.terms.get("gene"))
        url = f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{rec.get('uid')}/"
        out: list[EvidenceRecord] = []
        for block, category, label in BLOCKS:
            data = rec.get(block) or {}
            desc = (data.get("description") or "").strip()
            if not desc:
                continue
            traits = [t.get("trait_name") for t in data.get("trait_set") or [] if t.get("trait_name")]
            disease = DiseaseReference(name=traits[0], other_identifiers=_trait_xrefs((data.get("trait_set") or [{}])[0])) if traits else None
            limitations = [GERMLINE_LIMITATION] if block == "germline_classification" else []
            if not exact:
                limitations.append("protein_change_not_in_record_title")
            if len(traits) > 1:
                limitations.append(f"multiple_conditions:{len(traits)}")
            out.append(EvidenceRecord(
                evidence_id=f"clinvar:{accession}:{block.split('_')[0]}",
                source_name=self.name,
                source_native_id=f"{accession}#{block}",
                source_url=url,
                source_version=version,
                retrieved_at=retrieved_at,
                query_tier=plan_item.tier,
                variant_match=variant_match,
                disease_match=DiseaseMatch.UNKNOWN,
                gene_symbol=gene,
                variant_description=title or None,
                disease=disease,
                evidence_category=category,
                assertion=f"ClinVar {label}: {desc}" + (f" (conditions: {', '.join(traits)})" if traits else ""),
                direction=EvidenceDirection.NOT_APPLICABLE,
                source_native_level=data.get("review_status") or None,
                source_native_status=desc,
                citations=[Citation(url=url, title=title or None, source_label="ClinVar variation record")],
                limitations=limitations,
                is_hypothesis=False,
                raw_reference=raw_ref,
            ))
        return out


def _trait_xrefs(trait: dict[str, Any]) -> dict[str, str]:
    return {x["db_source"]: str(x["db_id"]) for x in trait.get("trait_xrefs") or [] if x.get("db_source") and x.get("db_id")}


def _env_set(name: str) -> bool:
    import os  # noqa: PLC0415

    return bool(os.environ.get(name))
