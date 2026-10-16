"""CIViC adapter (GraphQL API v2, https://civicdb.org/api/graphql).

Evidence items are retrieved through the ``evidenceItems`` connection filtered
by molecular-profile name. CIViC molecular profiles are named
``"<GENE> <VARIANT>"`` (e.g. ``CTNNB1 S45F``) and the filter is a substring
match, so:

* exact tier   -> ``"<gene> <protein_change>"``   (e.g. ``CTNNB1 D32N``)
* codon tier   -> ``"<gene> <codon>"``            (e.g. ``CTNNB1 D32`` matches D32Y, D32G ...)
* gene tier    -> ``"<gene>"``                    (all profiles mentioning the gene, incl. complex profiles)

``variant_match`` is ``EXACT_VARIANT`` only when the returned molecular profile
name equals ``"<gene> <protein_change>"``; otherwise the query tier is used.
The newest named data release is recorded as ``source_version``.
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

EVIDENCE_QUERY = """query SomaWeaveEvidence($mp: String!, $first: Int!, $after: String) {
  dataReleases { name }
  evidenceItems(molecularProfileName: $mp, first: $first, after: $after) {
    totalCount
    pageInfo { hasNextPage endCursor }
    nodes {
      id name link status evidenceType evidenceLevel evidenceDirection significance evidenceRating variantOrigin description
      molecularProfile { id name }
      disease { id name doid }
      therapies { id name ncitId }
      source { id citation citationId sourceType pmcId publicationYear title sourceUrl ascoAbstractId }
    }
  }
}"""

EVIDENCE_TYPE_MAP = {
    "PREDICTIVE": EvidenceCategory.PREDICTIVE,
    "PROGNOSTIC": EvidenceCategory.PROGNOSTIC,
    "DIAGNOSTIC": EvidenceCategory.DIAGNOSTIC,
    "ONCOGENIC": EvidenceCategory.ONCOGENIC,
    "PREDISPOSING": EvidenceCategory.OTHER,
    "FUNCTIONAL": EvidenceCategory.FUNCTIONAL,
}
DIRECTION_MAP = {
    "SUPPORTS": EvidenceDirection.SUPPORTS,
    "DOES_NOT_SUPPORT": EvidenceDirection.DOES_NOT_SUPPORT,
}
CLINICAL_TYPES = {"PREDICTIVE", "PROGNOSTIC", "DIAGNOSTIC"}
PAGE_SIZE = 50


class CivicProvider(Provider):
    name = "civic"
    requires_api_key = False

    def version(self) -> Optional[str]:
        return None  # resolved from dataReleases in the same request

    @staticmethod
    def molecular_profile_name(plan_item: Any) -> Optional[str]:
        t = plan_item.terms
        gene = t.get("gene")
        if not gene:
            return None
        if plan_item.tier == MatchSpecificity.EXACT_VARIANT:
            pc = t.get("protein_change")
            return f"{gene} {pc}" if pc else None
        if plan_item.tier == MatchSpecificity.CODON:
            codon = t.get("codon")
            return f"{gene} {codon}" if codon else None
        if plan_item.tier == MatchSpecificity.GENE:
            return str(gene)
        return None

    def supports(self, plan_item: Any) -> bool:
        return self.molecular_profile_name(plan_item) is not None

    def _request(self, mp: str, after: Optional[str]) -> TransportRequest:
        return TransportRequest(
            method="POST", url=self.config.base_url, headers=self._headers(), timeout_s=self.config.timeout_s,
            json_body={"query": EVIDENCE_QUERY, "variables": {"mp": mp, "first": min(PAGE_SIZE, self.config.max_records), "after": after}},
        )

    def _execute(self, plan_item: Any, query: SourceQuery, retrieved_at: datetime,
                 cache: PayloadCache | None) -> tuple[SourceQueryResult, list[EvidenceRecord]]:
        mp = self.molecular_profile_name(plan_item)
        assert mp is not None
        first_request = self._request(mp, None)
        native = first_request.native_request()
        query = query.model_copy(update={"native_request": native})
        cache_key = PayloadCache.key_for(native)
        raw_ref: Optional[str] = None
        payloads: list[Any] = []
        cached = cache.get(self.name, cache_key) if cache else None
        notes: list[str] = []
        if cached is not None:
            payloads = list(cached.get("payloads", []))
            raw_ref = cache.reference(self.name, cache_key)  # type: ignore[union-attr]
            notes.append(f"served from cache written {cached.get('cached_at')}")
        else:
            after: Optional[str] = None
            while True:
                response = self._send(self._request(mp, after))
                payload = response.json()
                payloads.append(payload)
                if payload.get("errors"):
                    raise ValueError(f"GraphQL errors: {payload['errors'][0].get('message', 'unknown')}")
                conn = payload["data"]["evidenceItems"]
                total = sum(len(p["data"]["evidenceItems"]["nodes"]) for p in payloads)
                if not conn["pageInfo"]["hasNextPage"] or total >= self.config.max_records:
                    break
                after = conn["pageInfo"]["endCursor"]
            if cache is not None:
                raw_ref = cache.put(self.name, cache_key, native, payloads)

        version = _release_name(payloads[0]) or utc_date_version(retrieved_at)
        total_count = int(payloads[0]["data"]["evidenceItems"].get("totalCount") or 0)
        nodes: list[dict[str, Any]] = []
        for p in payloads:
            nodes.extend(p["data"]["evidenceItems"]["nodes"])
        nodes = nodes[: self.config.max_records]
        records = [self._map_item(n, plan_item, mp, version, retrieved_at, raw_ref) for n in nodes]
        if total_count > len(records):
            notes.append(f"{total_count} items available, {len(records)} returned (max_records={self.config.max_records})")
        status = SourceStatus.OK if records else SourceStatus.NO_RECORDS
        if not records:
            notes.append(f"no CIViC evidence items for molecular profile filter {mp!r}")
        result = self._result(query, status, retrieved_at, records=records, source_version=version,
                              message="; ".join(notes) or None)
        return result, records

    def _map_item(self, node: dict[str, Any], plan_item: Any, mp: str, version: str,
                  retrieved_at: datetime, raw_ref: Optional[str]) -> EvidenceRecord:
        etype = (node.get("evidenceType") or "").upper()
        status = (node.get("status") or "").lower()
        profile_name = (node.get("molecularProfile") or {}).get("name") or ""
        gene = plan_item.terms.get("gene")
        exact_name = f"{gene} {plan_item.terms.get('protein_change')}" if plan_item.terms.get("protein_change") else None
        variant_match = MatchSpecificity.EXACT_VARIANT if exact_name and profile_name == exact_name else (
            plan_item.tier if plan_item.tier != MatchSpecificity.EXACT_VARIANT else MatchSpecificity.GENE)
        limitations: list[str] = []
        if status and status != "accepted":
            limitations.append("submitted_not_accepted" if status == "submitted" else f"civic_status_{status}")
        if " OR " in profile_name or " AND " in profile_name:
            limitations.append("complex_molecular_profile")
        origin = node.get("variantOrigin")
        if origin and "GERMLINE" in str(origin).upper():
            limitations.append("germline_variant_origin")
        disease = node.get("disease") or {}
        therapies = [t.get("name") for t in node.get("therapies") or [] if t.get("name")]
        source = node.get("source") or {}
        citation = _citation(source)
        significance = node.get("significance") or ""
        assertion = (node.get("description") or "").strip() or f"{etype.title()} evidence: {significance}"
        is_hypothesis = not (status == "accepted" and etype in CLINICAL_TYPES)
        return EvidenceRecord(
            evidence_id=f"civic:eid:{node['id']}",
            source_name=self.name,
            source_native_id=str(node["id"]),
            source_url=_absolute_link(node.get("link"), node["id"]),
            source_version=version,
            retrieved_at=retrieved_at,
            query_tier=plan_item.tier,
            variant_match=variant_match,
            disease_match=DiseaseMatch.UNKNOWN,
            gene_symbol=gene,
            variant_description=profile_name or None,
            disease=DiseaseReference(name=disease["name"], doid=(f"DOID:{disease['doid']}" if disease.get("doid") else None)) if disease.get("name") else None,
            evidence_category=EVIDENCE_TYPE_MAP.get(etype, EvidenceCategory.OTHER),
            assertion=assertion,
            direction=DIRECTION_MAP.get((node.get("evidenceDirection") or "").upper(), EvidenceDirection.NOT_APPLICABLE),
            drugs=therapies,
            source_native_level=node.get("evidenceLevel"),
            source_native_rating=str(node["evidenceRating"]) if node.get("evidenceRating") is not None else None,
            source_native_status=f"{status}; significance={significance}" if significance else (status or None),
            citations=[citation] if citation else [],
            limitations=limitations,
            is_hypothesis=is_hypothesis,
            raw_reference=raw_ref,
        )


def _absolute_link(link: Optional[str], evidence_id: Any) -> str:
    """CIViC returns ``link`` as a site-relative path; make it absolute."""
    if not link:
        return f"https://civicdb.org/evidence/{evidence_id}"
    if link.startswith("/"):
        return f"https://civicdb.org{link}"
    return link


def _release_name(payload: dict[str, Any]) -> Optional[str]:
    releases = (payload.get("data") or {}).get("dataReleases") or []
    for rel in releases:
        name = rel.get("name")
        if name and name.lower() != "nightly":
            return f"civic-release:{name}"
    return None


def _citation(source: dict[str, Any]) -> Optional[Citation]:
    if not source:
        return None
    stype = (source.get("sourceType") or "").upper()
    cid = source.get("citationId")
    pmid = str(cid) if stype == "PUBMED" and cid else None
    label = {"PUBMED": "PubMed", "ASCO": "ASCO abstract", "ASH": "ASH abstract"}.get(stype, stype or None)
    pmcid = source.get("pmcId")
    year = source.get("publicationYear")
    url = source.get("sourceUrl") or (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None)
    return Citation(pmid=pmid, pmcid=(f"PMC{pmcid}" if pmcid and not str(pmcid).startswith("PMC") else pmcid) if pmcid else None,
                    url=url, title=source.get("title") or source.get("citation"), year=int(year) if year else None,
                    source_label=label if label else None)
