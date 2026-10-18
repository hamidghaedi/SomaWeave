"""ToolUniverse-backed clinical-trial registry adapter.

ToolUniverse (Apache-2.0; https://github.com/mims-harvard/ToolUniverse) wraps
several thousand scientific tools behind one JSON tool-call interface. SomaWeave
uses it as a *data-access layer* for sources that have no dedicated adapter —
first the ClinicalTrials.gov v2 registry — not as an agent.

Design constraints honoured here:

* ``tooluniverse`` is never imported by SomaWeave. It runs in its own
  environment; this module starts ``tooluniverse_bridge.py`` with that
  environment's interpreter and exchanges newline-delimited JSON with it
  through :class:`ToolUniverseBridgeTransport`, a regular ``Transport`` so the
  payload cache, ``RecordingTransport`` and ``ScriptedTransport`` work unchanged.
* Trial records are context, not evidence. Every record carries
  ``evidence_category=trial`` and ``is_hypothesis=True``; reconciliation never
  accepts them, so no axis (analytical, oncogenicity, actionability, relevance)
  can be influenced by trial availability. They are reported in a separate
  section with the registry's own wording.
* Matching is a registry free-text search on the gene symbol plus a condition
  term taken from a hierarchy (recorded diagnosis -> OncoTree node -> lineage ->
  tumour-class basket); the level is stamped on every record. Eligibility
  criteria and biomarker requirements are not evaluated.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import Field

from somaweave.domain import DiseaseReference, EvidenceCategory, EvidenceDirection, EvidenceRecord, MatchSpecificity, SourceStatus
from somaweave.providers.base import (
    PayloadCache,
    Provider,
    ProviderConfig,
    TransportError,
    TransportRequest,
    TransportResponse,
    requests_transport,
)

BRIDGE_SCRIPT = Path(__file__).with_name("tooluniverse_bridge.py")
PYTHON_ENV_VAR = "SOMAWEAVE_TOOLUNIVERSE_PYTHON"
URL_SCHEME = "tooluniverse://"
PASSTHROUGH_ENV = ("HOME", "PATH", "LANG", "LC_ALL", "TMPDIR", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
                   "http_proxy", "https_proxy", "no_proxy", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE")


class ToolUniverseConfig(ProviderConfig):
    """Secret-free settings for the ToolUniverse bridge. ``base_url`` is nominal (``tooluniverse://local``)."""

    base_url: str = Field(default="tooluniverse://local")
    python_executable: Optional[str] = Field(default=None, description=f"Interpreter of the environment where tooluniverse is installed; default: ${PYTHON_ENV_VAR}.")
    clean_environment: bool = Field(default=True, description="Start the bridge with a minimal environment (drops PYTHONPATH and site customisations of the calling shell).")
    startup_timeout_s: float = Field(default=180.0, gt=0, description="Time allowed for the bridge to load the tool catalogue.")
    search_tool: str = Field(default="ClinicalTrials_search_studies")
    statuses: list[str] = Field(default_factory=lambda: ["RECRUITING", "NOT_YET_RECRUITING"], description="ClinicalTrials.gov overall-status filter.")
    page_size: int = Field(default=25, ge=1, le=100)
    condition_levels: list[str] = Field(default_factory=lambda: ["diagnosis", "oncotree", "lineage", "basket"],
                                        description="Condition-hierarchy levels to query, most specific first (see normalization.disease.condition_hierarchy).")


class ToolUniverseBridgeTransport:
    """``Transport`` that forwards ``tooluniverse://<tool>`` requests to a persistent bridge process.

    The bridge is started lazily on the first request and reused; one instance
    per provider. Any failure to start or talk to it raises ``TransportError``
    (mapped to ``unavailable`` by ``Provider.query``). Tool-level failures are
    returned as HTTP-like 502 responses with the bridge's error text.
    """

    def __init__(self, config: ToolUniverseConfig):
        self.config = config
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self.ready_info: dict[str, Any] = {}

    # -- lifecycle -------------------------------------------------------------
    def python_executable(self) -> Optional[str]:
        return self.config.python_executable or os.environ.get(PYTHON_ENV_VAR) or None

    def _environment(self) -> dict[str, str]:
        if not self.config.clean_environment:
            return dict(os.environ)
        env = {k: os.environ[k] for k in PASSTHROUGH_ENV if k in os.environ}
        env.setdefault("PATH", "/usr/bin:/bin")
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def _start(self) -> None:
        exe = self.python_executable()
        if not exe:
            raise TransportError(f"tooluniverse interpreter not configured ({PYTHON_ENV_VAR} unset and python_executable empty)")
        if not Path(exe).exists():
            raise TransportError(f"tooluniverse interpreter not found: {exe}")
        if not BRIDGE_SCRIPT.exists():  # pragma: no cover - packaging error
            raise TransportError(f"bridge script missing: {BRIDGE_SCRIPT}")
        try:
            proc = subprocess.Popen([exe, str(BRIDGE_SCRIPT)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=self._environment(), bufsize=1)
        except OSError as exc:
            raise TransportError(f"cannot start tooluniverse bridge: {exc}") from exc
        line = self._readline(proc, self.config.startup_timeout_s)
        try:
            info = json.loads(line) if line else {}
        except ValueError:
            info = {}
        if not info.get("ready"):
            proc.kill()
            raise TransportError(f"tooluniverse bridge failed to start: {info.get('error') or (line or 'no handshake')[:200]}")
        self.ready_info = info
        self._proc = proc

    @staticmethod
    def _readline(proc: subprocess.Popen[str], timeout_s: float) -> str:
        box: dict[str, str] = {}

        def reader() -> None:
            box["line"] = proc.stdout.readline() if proc.stdout else ""

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        t.join(timeout_s)
        if t.is_alive():
            proc.kill()
            raise TransportError(f"tooluniverse bridge timed out after {timeout_s:g} s")
        return box.get("line", "")

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                if proc.stdin:
                    proc.stdin.close()
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001 - best effort shutdown
                proc.kill()

    def __del__(self) -> None:  # pragma: no cover - interpreter shutdown ordering
        try:
            self.close()
        except Exception:  # noqa: BLE001
            pass

    # -- Transport protocol ------------------------------------------------------
    def __call__(self, request: TransportRequest) -> TransportResponse:
        if not request.url.startswith(URL_SCHEME):
            raise TransportError(f"ToolUniverse transport only handles {URL_SCHEME}<tool> urls, got {request.url}")
        tool = request.url[len(URL_SCHEME):]
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._proc = None
                self._start()
            proc = self._proc
            assert proc is not None and proc.stdin is not None
            rid = uuid.uuid4().hex
            try:
                proc.stdin.write(json.dumps({"id": rid, "tool": tool, "arguments": request.json_body or {}}) + "\n")
                proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self.close()
                raise TransportError(f"tooluniverse bridge pipe closed: {exc}") from exc
            line = self._readline(proc, request.timeout_s)
        if not line:
            self.close()
            raise TransportError("tooluniverse bridge closed without answering")
        try:
            reply = json.loads(line)
        except ValueError as exc:
            raise TransportError(f"tooluniverse bridge sent non-JSON output: {line[:120]!r}") from exc
        if reply.get("id") != rid:
            raise TransportError("tooluniverse bridge reply id mismatch")
        if not reply.get("ok"):
            return TransportResponse(status_code=502, text=str(reply.get("error") or "tool error"))
        return TransportResponse(status_code=200, text=json.dumps(reply.get("result")))


class ToolUniverseProvider(Provider):
    """Clinical-trial registry context via ToolUniverse's ClinicalTrials.gov tools (gene tier only)."""

    name = "tooluniverse"
    config_model = ToolUniverseConfig
    source_label = "ClinicalTrials.gov API v2"

    def __init__(self, config, **kwargs):
        if not isinstance(config, ToolUniverseConfig):
            config = ToolUniverseConfig.model_validate(config.model_dump(exclude_unset=True))
        transport = kwargs.pop("transport", None)
        if transport is None or transport is requests_transport:
            transport = ToolUniverseBridgeTransport(config)
        super().__init__(config, transport=transport, **kwargs)

    # -- planner contract --------------------------------------------------------
    def supports(self, plan_item) -> bool:
        return plan_item.tier == MatchSpecificity.GENE and bool(plan_item.terms.get("gene")) and bool(plan_item.terms.get("disease"))

    def version(self) -> Optional[str]:
        transport = self.transport
        info = getattr(transport, "ready_info", None)
        if info is None:  # e.g. RecordingTransport wrapping the bridge
            info = getattr(getattr(transport, "_inner", None), "ready_info", None)
        if not info:
            return None
        return f"tooluniverse {info.get('tooluniverse_version') or 'unknown'}; {self.source_label}"

    # -- execution -------------------------------------------------------------
    def _levels(self, plan_item) -> list[dict[str, str]]:
        """Condition terms to query, most specific first; falls back to the recorded diagnosis alone."""
        hierarchy = plan_item.terms.get("condition_hierarchy") or [{"level": "diagnosis", "term": plan_item.terms["disease"]}]
        allowed = set(self.config.condition_levels)
        return [h for h in hierarchy if isinstance(h, dict) and h.get("term") and h.get("level") in allowed]

    def _arguments(self, plan_item, condition: str) -> dict[str, Any]:
        return {"query_term": plan_item.terms["gene"], "condition": condition,
                "status": ",".join(self.config.statuses), "page_size": self.config.page_size}

    def _fetch(self, plan_item, condition: str, cache: PayloadCache | None) -> tuple[dict[str, Any], str, Optional[str], Optional[str]]:
        """One registry request; returns (payload, native_request, raw_reference, cached_at)."""
        request = TransportRequest(method="POST", url=f"{URL_SCHEME}{self.config.search_tool}", json_body=self._arguments(plan_item, condition),
                                   headers=self._headers(), timeout_s=self.config.timeout_s)
        native = request.native_request()
        key = PayloadCache.key_for(native)
        cached = cache.get(self.name, key) if cache else None
        raw_ref = cache.reference(self.name, key) if cached else None
        if cached and cached.get("payloads"):
            payload = cached["payloads"][0]
        else:
            payload = self._send(request).json()
        if not isinstance(payload, dict):
            raise ValueError("ToolUniverse response is not an object")
        if payload.get("status") not in (None, "success"):
            raise ValueError(f"ToolUniverse tool status {payload.get('status')!r}: {str(payload.get('error') or payload.get('message') or '')[:200]}")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        if not isinstance(data.get("studies"), list):
            raise ValueError("ToolUniverse response missing data.studies")
        if cache and not cached:
            raw_ref = cache.put(self.name, key, native, [payload])
        return data, native, raw_ref, (cached or {}).get("cached_at")

    def _execute(self, plan_item, query, retrieved_at: datetime, cache: PayloadCache | None):
        levels = self._levels(plan_item)
        if not levels:
            raise ValueError("no condition terms available for the trial search")
        natives: list[str] = []
        notes: list[str] = []
        records: list[EvidenceRecord] = []
        seen: set[str] = set()
        first_error: Exception | None = None
        succeeded = 0
        for lv in levels:
            level, term = lv["level"], lv["term"]
            try:
                data, native, raw_ref, cached_at = self._fetch(plan_item, term, cache)
            except Exception as exc:  # noqa: BLE001 - keep results of other levels; re-raised below if nothing succeeded
                first_error = first_error or exc
                notes.append(f"{level} '{term}': unavailable ({type(exc).__name__})")
                continue
            succeeded += 1
            natives.append(native)
            version = self.version() or self.source_label
            total = data.get("total_count")
            new = 0
            for study in data["studies"]:
                if not isinstance(study, dict):
                    continue
                nct = str(study.get("nct_id") or "").strip()
                if not nct or nct in seen or len(records) >= self.config.max_records:
                    continue
                seen.add(nct)
                records.append(self._record(study, plan_item, retrieved_at, version, raw_ref, level, term))
                new += 1
            count = total if isinstance(total, int) else len(data["studies"])
            notes.append(f"{level} '{term}': {count} match(es), {new} reported" + (" [cache]" if cached_at else ""))
        if succeeded == 0 and first_error is not None:
            raise first_error
        query = query.model_copy(update={"native_request": "\n".join(natives)})
        version = self.version() or self.source_label
        message = "; ".join(notes)
        if not records:
            return self._result(query, SourceStatus.NO_RECORDS, retrieved_at, source_version=version,
                                message=f"no {'/'.join(self.config.statuses).lower()} trials at any condition level ({message}); absence is not evidence"), []
        if len(records) >= self.config.max_records:
            message += f"; capped at {self.config.max_records} records"
        return self._result(query, SourceStatus.OK, retrieved_at, records=records, source_version=version, message=message), records

    def _record(self, study: dict[str, Any], plan_item, retrieved_at: datetime, version: str, raw_ref: Optional[str],
                level: str, term: str) -> EvidenceRecord:
        nct = str(study["nct_id"]).strip()
        gene = plan_item.terms.get("gene")
        disease = plan_item.terms.get("disease")
        conditions = [str(c) for c in (study.get("conditions") or []) if c]
        interventions = [str(i) for i in (study.get("interventions") or []) if i]
        phases = [str(p) for p in (study.get("phases") or []) if p]
        status = str(study.get("status") or "unknown status")
        title = str(study.get("brief_title") or study.get("official_title") or nct)
        enrollment = study.get("enrollment") if isinstance(study.get("enrollment"), int) and study.get("enrollment", -1) >= 0 else None
        parts = [f"{status} {str(study.get('study_type') or 'study').lower()} {nct}: {title}"]
        if phases:
            parts.append("phases " + "/".join(phases))
        if conditions:
            parts.append("registered conditions: " + "; ".join(conditions[:8]))
        if interventions:
            parts.append("registered interventions: " + "; ".join(interventions[:10]) + (" (truncated)" if study.get("interventions_truncated") else ""))
        if study.get("sponsor"):
            parts.append(f"sponsor {study['sponsor']}")
        parts.append(f"registry text matched {gene!r} with condition {term!r} ({level} level; recorded diagnosis {disease!r})")
        limitations = [
            f"Registry free-text match on gene symbol and the {level}-level condition term {term!r}; eligibility criteria and biomarker requirements were not evaluated",
            "Trial availability is not evidence of efficacy, oncogenicity or actionability; no tier is derived from this record",
            "Interventions and conditions are listed as registered and may be truncated; verify on ClinicalTrials.gov",
        ]
        if level == "basket":
            limitations.append("Basket-level match: the registered conditions do not name this diagnosis; applicability to this cancer type is unverified")
        return EvidenceRecord(
            evidence_id=f"tooluniverse:clinicaltrials:{nct}", source_name=self.name, source_native_id=nct,
            source_url=f"https://clinicaltrials.gov/study/{nct}", source_version=version, retrieved_at=retrieved_at,
            query_tier=plan_item.tier, variant_match=MatchSpecificity.GENE, gene_symbol=gene,
            variant_description=f"{gene} (registry text match, not variant-specific)",
            disease=DiseaseReference(name=conditions[0]) if conditions else None,
            conditions=[DiseaseReference(name=c) for c in conditions],
            evidence_category=EvidenceCategory.TRIAL, assertion="; ".join(parts), direction=EvidenceDirection.NOT_APPLICABLE,
            drugs=interventions, source_native_level="/".join(phases) or None, source_native_status=status,
            source_native_rating=f"{level}: {term}",
            sample_size=enrollment, limitations=limitations, is_hypothesis=True, raw_reference=raw_ref,
        )


__all__ = ["BRIDGE_SCRIPT", "PYTHON_ENV_VAR", "ToolUniverseBridgeTransport", "ToolUniverseConfig", "ToolUniverseProvider"]
