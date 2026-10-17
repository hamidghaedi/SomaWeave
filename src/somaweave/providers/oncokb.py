"""OncoKB adapter (REST API v1, https://www.oncokb.org/api/v1).

One request per exact-variant plan item:
``GET /annotate/mutations/byProteinChange?hugoSymbol=<gene>&alteration=<one-letter change>&referenceGenome=<GRCh37|GRCh38>[&tumorType=<OncoTree code>]``.

Mapping of the ``IndicatorQueryResp`` payload:

* ``oncogenic`` + ``mutationEffect``            -> one ``ONCOGENIC`` record (``kind`` = ``oncogenic``);
* each entry of ``treatments``                   -> one ``PREDICTIVE`` record (``kind`` = ``treatment``);
* each entry of ``diagnosticImplications`` /
  ``prognosticImplications``                     -> one ``DIAGNOSTIC`` / ``PROGNOSTIC`` record.

``evidence_id`` is ``oncokb:<gene>:<alteration>:<kind>:<index>``. ``disease_match``
is always left ``UNKNOWN``; the reconciliation layer owns it.

Credentials. The bearer token is read at query time from the environment
variable named in ``api_key_env`` (default ``ONCOKB_API_TOKEN``) or, failing
that, from the file named in ``token_file`` (default ``~/.oncokb_token``). The
token is never stored on the provider, never written to results, cache keys,
``native_request`` strings or recordings (``TransportRequest.native_request``
omits headers by design). Without a token the query returns
``SourceStatus.NO_CREDENTIALS`` -- missing evidence, never negative evidence.

Licence. OncoKB content requires an institutional licence (academic research
use is no-fee after registration). Payloads are cached only in the caller
supplied cache directory and must not be redistributed.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import Field

from somaweave.domain import (
    AlterationType,
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
from somaweave.providers.base import (
    HTTPStatusError,
    PayloadCache,
    Provider,
    ProviderConfig,
    TransportRequest,
    utc_date_version,
)

DEFAULT_TOKEN_ENV = "ONCOKB_API_TOKEN"
DEFAULT_TOKEN_FILE = "~/.oncokb_token"
ENDPOINT = "/annotate/mutations/byProteinChange"
SMALL_VARIANT_TYPES = frozenset({
    AlterationType.SNV.value, AlterationType.MNV.value, AlterationType.INSERTION.value,
    AlterationType.DELETION.value, AlterationType.DELINS.value,
})
SENSITIVITY_LEVELS = ("LEVEL_1", "LEVEL_2", "LEVEL_3A", "LEVEL_3B", "LEVEL_4")
RESISTANCE_LEVELS = ("LEVEL_R1", "LEVEL_R2")
BIOLOGICAL_ONLY_LEVELS = frozenset({"LEVEL_4"})
SUPPORTIVE_ONCOGENIC = frozenset({"oncogenic", "likely oncogenic", "resistance"})
NEUTRAL_ONCOGENIC = frozenset({"likely neutral"})
CURATED_ONCOGENIC = SUPPORTIVE_ONCOGENIC | NEUTRAL_ONCOGENIC | frozenset({"inconclusive"})
UNKNOWN_TOKENS = frozenset({"", "unknown", "none"})
_CODON_RE = re.compile(r"^[A-Z*]\d+")
_TRUNCATING_PC_RE = re.compile(r"(fs|\*|Ter|X)\d*$|^[A-Z]\d+\*$")
LOF_EFFECTS = frozenset({"loss-of-function", "likely loss-of-function"})
CLASS_LEVEL_LIMITATION = "oncokb_class_level_annotation"
HIGHEST_LEVEL_FIELDS = (
    "highestSensitiveLevel", "highestResistanceLevel", "highestDiagnosticImplicationLevel",
    "highestPrognosticImplicationLevel", "highestFdaLevel",
)


class OncoKBConfig(ProviderConfig):
    """``ProviderConfig`` plus OncoKB-specific, secret-free settings."""

    api_key_env: Optional[str] = Field(default=DEFAULT_TOKEN_ENV, description="Environment variable holding the bearer token; the value is never stored.")
    token_file: Optional[str] = Field(default=DEFAULT_TOKEN_FILE, description="Fallback token file (user-expanded); contents are never stored or logged.")
    reference_genome: str = Field(default="GRCh38", pattern=r"^GRCh3[78]$", description="Used when the plan item carries no assembly term.")
    licence: Optional[str] = Field(default=None, description="Free-text licence note for the deployment (no secrets).")


class OncoKBProvider(Provider):
    name = "oncokb"
    requires_api_key = False  # credential presence is checked here so the message is OncoKB-specific
    config_model = OncoKBConfig

    def __init__(self, config: ProviderConfig, transport: Any = None, **kwargs: Any):
        if not isinstance(config, OncoKBConfig):
            config = OncoKBConfig.model_validate(config.model_dump(exclude_unset=True))
        super().__init__(config, transport=transport, **kwargs)
        self.config: OncoKBConfig = config

    # -- credentials ---------------------------------------------------------
    def api_key(self) -> Optional[str]:
        """Token from the configured environment variable, else the token file. Never cached."""
        env_name = self.config.api_key_env
        if env_name:
            value = (os.environ.get(env_name) or "").strip()
            if value:
                return value
        if self.config.token_file:
            path = Path(os.path.expanduser(self.config.token_file))
            try:
                if path.is_file():
                    value = path.read_text(encoding="utf-8").strip()
                    if value:
                        return value
            except OSError:
                return None
        return None

    # -- plan support ----------------------------------------------------------
    @staticmethod
    def query_terms(plan_item: Any) -> Optional[dict[str, str]]:
        """``{gene, alteration[, tumor_type]}`` for an exact-variant small-variant item, else ``None``."""
        if plan_item.tier != MatchSpecificity.EXACT_VARIANT:
            return None
        t = plan_item.terms
        gene, pc = t.get("gene"), t.get("protein_change")
        if not gene or not pc:
            return None
        if t.get("alteration_type") not in SMALL_VARIANT_TYPES:
            return None
        out = {"gene": str(gene), "alteration": str(pc)}
        if t.get("oncotree_code"):
            out["tumor_type"] = str(t["oncotree_code"])
        return out

    def supports(self, plan_item: Any) -> bool:
        return self.query_terms(plan_item) is not None

    def version(self) -> Optional[str]:
        return None  # resolved from ``dataVersion`` in the response

    def _reference_genome(self, plan_item: Any) -> str:
        assembly = str(plan_item.terms.get("assembly") or "")
        return assembly if assembly in ("GRCh37", "GRCh38") else self.config.reference_genome

    def _request(self, terms: dict[str, str], reference_genome: str, token: str) -> TransportRequest:
        params: dict[str, Any] = {"hugoSymbol": terms["gene"], "alteration": terms["alteration"], "referenceGenome": reference_genome}
        if terms.get("tumor_type"):
            params["tumorType"] = terms["tumor_type"]
        headers = {**self._headers(), "Authorization": f"Bearer {token}"}
        return TransportRequest(method="GET", url=self.config.base_url.rstrip("/") + ENDPOINT, params=params,
                                headers=headers, timeout_s=self.config.timeout_s)

    # -- execution ---------------------------------------------------------------
    def _execute(self, plan_item: Any, query: SourceQuery, retrieved_at: datetime,
                 cache: PayloadCache | None) -> tuple[SourceQueryResult, list[EvidenceRecord]]:
        terms = self.query_terms(plan_item)
        assert terms is not None
        token = self.api_key()
        if not token:
            return self._result(query, SourceStatus.NO_CREDENTIALS, retrieved_at, message="OncoKB token not configured"), []
        request = self._request(terms, self._reference_genome(plan_item), token)
        native = request.native_request()  # params only; the Authorization header is not part of it
        query = query.model_copy(update={"native_request": native})
        cache_key = PayloadCache.key_for(native)
        notes: list[str] = []
        raw_ref: Optional[str] = None
        cached = cache.get(self.name, cache_key) if cache else None
        if cached is not None and cached.get("payloads"):
            payload = cached["payloads"][0]
            raw_ref = cache.reference(self.name, cache_key)  # type: ignore[union-attr]
            notes.append(f"served from cache written {cached.get('cached_at')}")
        else:
            try:
                response = self._send(request)
            except HTTPStatusError as exc:
                if exc.status_code == 401:
                    return self._result(query, SourceStatus.ERROR, retrieved_at,
                                        message="HTTP 401: OncoKB rejected the configured token (unauthorized); token value not logged"), []
                raise
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("unexpected OncoKB payload: expected a JSON object")
            if cache is not None:
                raw_ref = cache.put(self.name, cache_key, native, [payload])
        del token, request

        data_version = payload.get("dataVersion")
        version = f"oncokb-data:{data_version}" if data_version else utc_date_version(retrieved_at)
        if not data_version:
            notes.append("dataVersion absent from response; retrieval date recorded as version")
        gene_exist = bool(payload.get("geneExist"))
        variant_exist = bool(payload.get("variantExist"))
        allele_exist = bool(payload.get("alleleExist"))
        if not terms.get("tumor_type"):
            notes.append("queried without tumorType; levels are not restricted to the case disease")
        records = self._map_payload(payload, plan_item, terms, version, retrieved_at, raw_ref)
        flags = f"geneExist={str(gene_exist).lower()}, variantExist={str(variant_exist).lower()}, alleleExist={str(allele_exist).lower()}"
        if records:
            status = SourceStatus.OK
            notes.append(flags)
        else:
            status = SourceStatus.NO_RECORDS
            if not gene_exist:
                notes.append(f"{terms['gene']} is not an OncoKB-curated gene ({flags})")
            else:
                notes.append(f"no curated OncoKB assertion for {terms['gene']} {terms['alteration']} ({flags}; oncogenic={payload.get('oncogenic') or 'n/a'})")
        return self._result(query, status, retrieved_at, records=records, source_version=version, message="; ".join(notes) or None), records

    # -- mapping ----------------------------------------------------------------
    def _map_payload(self, payload: dict[str, Any], plan_item: Any, terms: dict[str, str], version: str,
                     retrieved_at: datetime, raw_ref: Optional[str]) -> list[EvidenceRecord]:
        gene, alt = terms["gene"], terms["alteration"]
        gene_exist = bool(payload.get("geneExist"))
        variant_exist = bool(payload.get("variantExist"))
        allele_exist = bool(payload.get("alleleExist"))
        if not gene_exist:
            return []
        base_match = MatchSpecificity.EXACT_VARIANT if variant_exist else (MatchSpecificity.CODON if allele_exist else MatchSpecificity.GENE)
        flag_limits: list[str] = []
        oncogenic = str(payload.get("oncogenic") or "").strip()
        effect = payload.get("mutationEffect") or {}
        known_effect = str(effect.get("knownEffect") or "").strip()
        class_level = False
        if not variant_exist:
            flag_limits.append("oncokb_variant_not_curated (variantExist=false)")
            if allele_exist:
                flag_limits.append("oncokb_other_alteration_at_same_position (alleleExist=true)")
            # OncoKB annotates uncurated truncating variants from its gene-level "Truncating Mutations"
            # entry. When the queried change is truncating and the returned effect is loss-of-function
            # (or the description says so), the annotation is class-level evidence, not gene-wide.
            is_truncating = (plan_item.terms.get("consequence_class") == "truncating") or bool(_TRUNCATING_PC_RE.search(alt))
            desc_l = str(effect.get("description") or "").lower()
            if is_truncating and (known_effect.lower() in LOF_EFFECTS or "truncating mutations" in desc_l):
                class_level = True
                base_match = MatchSpecificity.GENE_ALTERATION_CLASS
                flag_limits.append(CLASS_LEVEL_LIMITATION)
        if not terms.get("tumor_type"):
            flag_limits.append("queried_without_tumor_type")

        treatments = payload.get("treatments") or []
        dx = payload.get("diagnosticImplications") or []
        px = payload.get("prognosticImplications") or []
        has_assertion = oncogenic.lower() not in UNKNOWN_TOKENS or known_effect.lower() not in UNKNOWN_TOKENS or treatments or dx or px
        if not has_assertion:
            return []

        common = dict(source_name=self.name, source_version=version, retrieved_at=retrieved_at, query_tier=plan_item.tier,
                      disease_match=DiseaseMatch.UNKNOWN, gene_symbol=gene,
                      variant_description=(f"{gene} Truncating Mutations (class-level annotation for {alt})" if class_level else f"{gene} {alt}"),
                      source_url=f"https://www.oncokb.org/gene/{gene}/{alt}", raw_reference=raw_ref)
        records: list[EvidenceRecord] = []

        # 1. oncogenicity / mutation effect summary record
        onc_l = oncogenic.lower()
        if onc_l in SUPPORTIVE_ONCOGENIC:
            direction = EvidenceDirection.SUPPORTS
        elif onc_l in NEUTRAL_ONCOGENIC:
            direction = EvidenceDirection.DOES_NOT_SUPPORT
        else:
            direction = EvidenceDirection.NOT_APPLICABLE
        assertion = f"OncoKB oncogenicity: {oncogenic or 'Unknown'}; mutation effect: {known_effect or 'Unknown'}"
        description = str(effect.get("description") or "").strip()
        if description:
            assertion += f". {description}"
        limits = list(flag_limits)
        if onc_l not in CURATED_ONCOGENIC:
            limits.append(f"oncokb_oncogenicity_not_curated ({oncogenic or 'Unknown'})")
        if payload.get("hotspot"):
            limits.append("oncokb_hotspot_flag=true")
        highest = "; ".join(f"{k}={payload.get(k) or 'none'}" for k in HIGHEST_LEVEL_FIELDS)
        if payload.get("lastUpdate"):
            highest += f"; lastUpdate={payload['lastUpdate']}"
        records.append(EvidenceRecord(
            evidence_id=f"oncokb:{gene}:{alt}:oncogenic:0", source_native_id=f"{gene} {alt}",
            variant_match=base_match, evidence_category=EvidenceCategory.ONCOGENIC, assertion=assertion, direction=direction,
            source_native_status=oncogenic or None, source_native_rating=highest,
            citations=_citations(effect.get("citations") or {}), limitations=limits,
            is_hypothesis=onc_l not in CURATED_ONCOGENIC, **common,
        ))

        # 2. treatments -> predictive records
        for i, tx in enumerate(treatments):
            level = str(tx.get("level") or "").strip().upper()
            drugs = [str(d.get("drugName")) for d in tx.get("drugs") or [] if d.get("drugName")]
            cancer = tx.get("levelAssociatedCancerType") or {}
            limits = list(flag_limits)
            if level in RESISTANCE_LEVELS:
                direction = EvidenceDirection.DOES_NOT_SUPPORT
                limits.append(f"resistance level {level}: alteration confers resistance to the listed agent(s)")
            elif level in SENSITIVITY_LEVELS:
                direction = EvidenceDirection.SUPPORTS
            else:
                direction = EvidenceDirection.NOT_APPLICABLE
                limits.append(f"unrecognised OncoKB level {level or 'n/a'}")
            matched = [str(a) for a in tx.get("alterations") or []]
            limits.append(f"oncokb_alteration_match: {', '.join(matched) or 'n/a'}")
            excluded = [c.get("name") or c.get("code") for c in tx.get("levelExcludedCancerTypes") or []]
            if excluded:
                limits.append("level excludes cancer types: " + ", ".join(str(e) for e in excluded))
            fda_level = tx.get("fdaLevel")
            approved = [str(a) for a in tx.get("approvedIndications") or []]
            if level in BIOLOGICAL_ONLY_LEVELS:
                limits.append("oncokb_level_4_biological_evidence_only (not a validated clinical biomarker)")
            design_parts = [f"OncoKB {level}" if level else "OncoKB level n/a"]
            if fda_level:
                design_parts.append(f"FDA level {fda_level}")
            if approved:
                design_parts.append("approved indications: " + "; ".join(approved))
            desc = str(tx.get("description") or "").strip()
            disease = _disease(cancer)
            cancer_name = disease.name if disease else "unspecified cancer type"
            if disease is None:
                limits.append("level_associated_cancer_type_not_stated_by_api"
                              + (" (LEVEL_3B: standard-care biomarker in another indication; indication not named for the queried tumour type)" if level == "LEVEL_3B" else ""))
            records.append(EvidenceRecord(
                evidence_id=f"oncokb:{gene}:{alt}:treatment:{i}", source_native_id=f"{gene} {alt} treatment {i}",
                variant_match=_treatment_match(alt, matched, base_match), evidence_category=EvidenceCategory.PREDICTIVE,
                assertion=desc or f"{level or 'level n/a'}: {', '.join(drugs) or 'no drug listed'} in {cancer_name}",
                direction=direction, drugs=drugs, source_native_level=level or None,
                source_native_status=oncogenic or None, study_design="; ".join(design_parts),
                disease=disease,
                citations=_citations({"pmids": tx.get("pmids") or [], "abstracts": tx.get("abstracts") or []}),
                limitations=limits, is_hypothesis=level in BIOLOGICAL_ONLY_LEVELS or direction == EvidenceDirection.NOT_APPLICABLE,
                **common,
            ))

        # 3. diagnostic / prognostic implications
        for kind, category, items in (("diagnostic", EvidenceCategory.DIAGNOSTIC, dx), ("prognostic", EvidenceCategory.PROGNOSTIC, px)):
            for i, imp in enumerate(items):
                level = str(imp.get("levelOfEvidence") or "").strip().upper()
                disease = _disease(imp.get("tumorType") or {})
                matched = [str(a) for a in imp.get("alterations") or []]
                name = disease.name if disease else "unspecified cancer type"
                desc = str(imp.get("description") or "").strip()
                records.append(EvidenceRecord(
                    evidence_id=f"oncokb:{gene}:{alt}:{kind}:{i}", source_native_id=f"{gene} {alt} {kind} {i}",
                    variant_match=_treatment_match(alt, matched, base_match), evidence_category=category,
                    assertion=desc or f"{level or 'level n/a'} {kind} implication in {name}", direction=EvidenceDirection.SUPPORTS,
                    source_native_level=level or None, source_native_status=oncogenic or None,
                    disease=disease,
                    citations=_citations({"pmids": imp.get("pmids") or [], "abstracts": imp.get("abstracts") or []}),
                    limitations=flag_limits + [f"oncokb_alteration_match: {', '.join(matched) or 'n/a'}"],
                    is_hypothesis=False, **common,
                ))
        return records[: self.config.max_records]


def _disease(block: dict[str, Any]) -> Optional[DiseaseReference]:
    """``DiseaseReference`` from an OncoKB tumour-type block; ``None`` when the API names nothing."""
    name = str(block.get("name") or "").strip()
    code = str(block.get("code") or "").strip()
    main = block.get("mainType") or {}
    main_name = str(main.get("name") or "").strip() if isinstance(main, dict) else ""
    if not (name or code or main_name):
        return None
    if name or code:
        ids = {"oncokb_main_type": main_name} if main_name and main_name != name else {}
        return DiseaseReference(name=name or code, oncotree_code=code or None, other_identifiers=ids)
    # OncoKB attaches some levels to an OncoTree *main type* (e.g. "Non-Small Cell Lung Cancer"), which has no code.
    return DiseaseReference(name=main_name, oncotree_code=None, other_identifiers={"oncokb_cancer_type_level": "main_type"})


def _treatment_match(alt: str, matched: list[str], base: MatchSpecificity) -> MatchSpecificity:
    """Variant match for a treatment/implication from its ``alterations`` list.

    ``G719S`` -> exact; ``G719`` (OncoKB codon-level alteration) -> codon;
    ``Oncogenic Mutations``-style categories -> gene alteration class; else the
    payload-level match.
    """
    if not matched:
        return base
    up = [m.strip().upper() for m in matched]
    if alt.upper() in up:
        return MatchSpecificity.EXACT_VARIANT
    codon = _CODON_RE.match(alt.upper())
    if codon and codon.group(0) in up:
        return MatchSpecificity.CODON
    if any("MUTATION" in m or "ONCOGENIC" in m for m in up):
        return MatchSpecificity.GENE_ALTERATION_CLASS
    return base


def _citations(block: dict[str, Any]) -> list[Citation]:
    out: list[Citation] = []
    seen: set[str] = set()
    for pmid in block.get("pmids") or []:
        p = str(pmid).strip()
        if p and p not in seen:
            seen.add(p)
            out.append(Citation(pmid=p, url=f"https://pubmed.ncbi.nlm.nih.gov/{p}/", source_label="PubMed"))
    for ab in block.get("abstracts") or []:
        if isinstance(ab, dict):
            link, title = ab.get("link"), ab.get("abstract")
        else:
            link, title = None, str(ab)
        key = f"abstract:{link or title}"
        if key not in seen and (link or title):
            seen.add(key)
            out.append(Citation(url=link or None, title=str(title) if title else None, source_label="abstract"))
    return out
