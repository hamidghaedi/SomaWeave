"""End-to-end ``interpret-case`` workflow.

Stages: validate and load the case -> normalize -> technical assessment ->
build the provider registry -> progressive retrieval per alteration (all
``NOT_QUERIED`` when offline) -> reconcile -> interpret -> render -> write
``<results_root>/<run_id>/{manifest.json, evidence/, reports/, qc/, logs/}``.

Environment-specific roots (``SOMAWEAVE_RESULTS_ROOT``, ``SOMAWEAVE_WORK_ROOT``,
``SOMAWEAVE_CACHE_ROOT``, ``SOMAWEAVE_REFERENCE_ROOT``) are read only here
(``resolve_roots``, ``resolve_oncotree``) and in the CLI; nothing below this
layer reads the environment. The OncoTree index comes from ``--oncotree-json``,
else ``<SOMAWEAVE_REFERENCE_ROOT>/oncotree/tumorTypes.json`` (or the newest
``tumorTypes_*.json`` there), else the built-in subset; the manifest records
which, with file path, version stamp and sha256. The manifest records
versions, input hashes and per-source status counts but no hostname and no
environment variable values (only the names of ``SOMAWEAVE_*`` variables).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from somaweave import __version__
from somaweave.domain import AnalyticalReliability, Case
from somaweave.domain.io import CaseValidationError, dump_model, load_case
from somaweave.evidence import EvidenceSet, reconcile
from somaweave.interpretation import interpret
from somaweave.normalization import BUILTIN_ONCOTREE, load_oncotree_json, normalize_case
from somaweave.normalization.disease import OncoTreeIndex, condition_hierarchy, find_oncotree_json
from somaweave.providers import ProviderRegistry, build_registry, load_provider_configs
from somaweave.reporting import RunBundle, render_json, render_markdown
from somaweave.retrieval import RetrievalResult, build_query_plan, run_plan
from somaweave.technical import assess_alteration, technical_summary

LOGGER_NAME = "somaweave"
ENV_RESULTS = "SOMAWEAVE_RESULTS_ROOT"
ENV_WORK = "SOMAWEAVE_WORK_ROOT"
ENV_CACHE = "SOMAWEAVE_CACHE_ROOT"
ENV_REFERENCE = "SOMAWEAVE_REFERENCE_ROOT"


class RootsError(ValueError):
    """A required runtime root is missing, absent on disk or not writable."""


class Roots(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results_root: Path
    work_root: Optional[Path] = None
    cache_root: Optional[Path] = None


class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    run_dir: Path
    case_id: str
    offline: bool
    manifest_path: Path
    report_json_path: Path
    report_markdown_path: Path
    evidence_path: Path
    source_queries_path: Path
    technical_path: Path
    log_path: Path
    status_counts: dict[str, int] = Field(default_factory=dict)
    findings_summary: list[dict[str, Any]] = Field(default_factory=list)
    oncotree_source: Optional[str] = Field(default=None, description="OncoTree file path or 'builtin-subset'.")


def _check_dir(path: Path, label: str, create: bool) -> Path:
    path = Path(path).expanduser()
    if not path.exists():
        if not create:
            raise RootsError(f"{label} {path} does not exist")
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RootsError(f"{label} {path} cannot be created: {exc}") from exc
    if not path.is_dir():
        raise RootsError(f"{label} {path} is not a directory")
    if not os.access(path, os.W_OK):
        raise RootsError(f"{label} {path} is not writable")
    return path.resolve()


def resolve_roots(results_root: str | Path | None = None, work_root: str | Path | None = None,
                  cache_root: str | Path | None = None, env: dict[str, str] | None = None) -> Roots:
    """Resolve roots from explicit arguments, then ``SOMAWEAVE_*`` variables.

    ``results_root`` is required and must exist and be writable. ``work_root``
    and ``cache_root`` are optional; when given they must be writable
    directories (``cache_root`` is created if absent).
    """
    env = os.environ if env is None else env
    results = results_root or env.get(ENV_RESULTS)
    if not results:
        raise RootsError(f"results root not given; pass --results-root or set {ENV_RESULTS}")
    work = work_root or env.get(ENV_WORK)
    cache = cache_root or env.get(ENV_CACHE)
    return Roots(
        results_root=_check_dir(Path(results), "results root", create=False),
        work_root=_check_dir(Path(work), "work root", create=False) if work else None,
        cache_root=_check_dir(Path(cache), "cache root", create=True) if cache else None,
    )


def resolve_oncotree(oncotree_json: str | Path | None = None, env: dict[str, str] | None = None) -> tuple[OncoTreeIndex, dict[str, Any]]:
    """Choose the OncoTree index and describe the choice for the manifest.

    Precedence: explicit ``oncotree_json`` (must exist) > ``<SOMAWEAVE_REFERENCE_ROOT>/oncotree/``
    (``tumorTypes.json`` or newest ``tumorTypes_*.json``) > built-in subset.
    A reference root that is set but has no OncoTree file falls back to the
    built-in subset with ``note`` saying so.
    """
    env = os.environ if env is None else env
    path: Optional[Path] = None
    note: str
    if oncotree_json:
        path = Path(oncotree_json).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"OncoTree JSON {path} does not exist")
        note = "oncotree: explicit file"
    elif env.get(ENV_REFERENCE):
        path = find_oncotree_json(env[ENV_REFERENCE])
        note = f"oncotree: from {ENV_REFERENCE}" if path else f"oncotree: built-in subset ({ENV_REFERENCE} set but no oncotree/tumorTypes*.json found)"
    else:
        note = "oncotree: built-in subset"
    if path is None:
        index = BUILTIN_ONCOTREE
    else:
        index = load_oncotree_json(path)
    info = {
        "source": index.source, "path": str(path.resolve()) if path else None, "version": index.version,
        "sha256": index.sha256, "node_count": index.node_count, "note": note,
    }
    return index, info


def default_providers_config() -> Optional[Path]:
    """Locate ``configs/providers.example.json`` in the repository checkout, if any."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "configs" / "providers.example.json"
        if candidate.exists():
            return candidate
    return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> Optional[str]:
    """Commit of the checkout containing the package, if ``git`` and a repository are available."""
    repo = Path(__file__).resolve()
    for parent in repo.parents:
        if (parent / ".git").exists():
            try:
                out = subprocess.run(["git", "-C", str(parent), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=False)
            except (OSError, subprocess.SubprocessError):
                return None
            return out.stdout.strip() or None if out.returncode == 0 else None
    return None


def make_run_id(input_sha: str, now: datetime) -> str:
    return f"{now.strftime('%Y%m%dT%H%M%SZ')}-{input_sha[:8]}"


def _setup_logger(log_path: Path) -> tuple[logging.Logger, logging.Handler]:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    return logger, handler


def _write_json(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")


def _pydantic_version() -> str:
    import pydantic  # noqa: PLC0415

    return getattr(pydantic, "VERSION", getattr(pydantic, "__version__", "unknown"))


def run(case_path: str | Path, *, results_root: str | Path | None = None, work_root: str | Path | None = None,
        cache_root: str | Path | None = None, providers_config: str | Path | None = None, offline: bool = False,
        run_id: str | None = None, registry: ProviderRegistry | None = None,
        oncotree_json: str | Path | None = None) -> RunResult:
    """Run the full interpretation workflow for one case file.

    ``registry`` lets tests inject providers with a scripted transport; in
    normal use the registry is built from ``providers_config`` (default: the
    repository example config). ``oncotree_json`` overrides the OncoTree
    source (see ``resolve_oncotree``). Raises ``RootsError`` for bad roots,
    ``CaseValidationError``/``json.JSONDecodeError`` for a bad case file and
    ``FileNotFoundError`` for missing inputs.
    """
    case_path = Path(case_path)
    if not case_path.exists():
        raise FileNotFoundError(f"case file {case_path} does not exist")
    roots = resolve_roots(results_root, work_root, cache_root)
    oncotree, oncotree_info = resolve_oncotree(oncotree_json)
    started = datetime.now(timezone.utc)
    input_sha = sha256_file(case_path)
    rid = run_id or make_run_id(input_sha, started)
    run_dir = roots.results_root / rid
    if run_dir.exists() and any(run_dir.iterdir()):
        raise RootsError(f"run directory {run_dir} already exists and is not empty")
    for sub in ("evidence", "reports", "qc", "logs"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
    logger, handler = _setup_logger(run_dir / "logs" / "run.log")
    try:
        logger.info("run %s started; somaweave %s; offline=%s", rid, __version__, offline)
        logger.info("input %s sha256=%s", case_path.name, input_sha)
        logger.info("%s; source=%s version=%s nodes=%d", oncotree_info["note"], oncotree_info["source"], oncotree_info["version"],
                    oncotree_info["node_count"])
        case: Case = load_case(case_path)
        logger.info("case %s validated: %d alteration(s), %d specimen(s)", case.case_id, len(case.alterations), len(case.specimens))
        normalized = normalize_case(case, oncotree=oncotree)
        logger.info("normalization: %d flag(s)", len(normalized.flags))

        tech = technical_summary(case)
        _write_json(tech, run_dir / "qc" / "technical.json")
        logger.info("technical summary written")

        cfg_path: Optional[Path] = Path(providers_config) if providers_config else default_providers_config()
        cfg_sha: Optional[str] = None
        if registry is None:
            if cfg_path is not None and cfg_path.exists():
                registry = build_registry(load_provider_configs(cfg_path))
                cfg_sha = sha256_file(cfg_path)
                logger.info("provider registry: %s from %s", ", ".join(registry.names()), cfg_path.name)
            elif offline:
                registry = ProviderRegistry()
                logger.warning("no providers config found; offline run proceeds with an empty registry")
            else:
                raise FileNotFoundError("providers config not found; pass --providers-config or run with --offline")
        elif cfg_path is not None and cfg_path.exists():
            cfg_sha = sha256_file(cfg_path)

        retrievals: list[RetrievalResult] = []
        evidence_sets: list[EvidenceSet] = []
        findings = []
        technical_by_alt: dict[str, list[AnalyticalReliability]] = {}
        extra_terms = {"condition_hierarchy": condition_hierarchy(normalized.disease.confirmed_name,
                                                              normalized.disease.confirmed_oncotree_code, oncotree)}
        for alt in case.alterations:
            plan = build_query_plan(case, alt, extra_terms=extra_terms)
            rr = run_plan(plan, registry, offline=offline, cache_root=roots.cache_root)
            retrievals.append(rr)
            logger.info("retrieval %s: %s, %d record(s)", alt.alteration_id, rr.status_counts(), len(rr.evidence))
            es = reconcile(normalized, alt, rr, index=oncotree)
            evidence_sets.append(es)
            tech_alt = assess_alteration(case, alt)
            technical_by_alt[alt.alteration_id] = tech_alt
            fa = interpret(normalized, alt, tech_alt, es)
            findings.append(fa)
            logger.info("finding %s: analytical=%s oncogenicity=%s tier=%s relevance=%s", alt.alteration_id, fa.analytical.level,
                        fa.oncogenicity.classification, fa.actionability.tier, fa.relevance.level)

        status_counts: dict[str, int] = {}
        per_source: dict[str, dict[str, int]] = {}
        for rr in retrievals:
            for qr in rr.query_results:
                status_counts[qr.status.value] = status_counts.get(qr.status.value, 0) + 1
                src = per_source.setdefault(qr.query.source_name, {})
                src[qr.status.value] = src.get(qr.status.value, 0) + 1

        finished = datetime.now(timezone.utc)
        provenance: dict[str, Any] = {
            "somaweave_version": __version__,
            "python_version": platform.python_version(),
            "pydantic_version": _pydantic_version(),
            "git_commit": git_commit(),
            "input_path": str(case_path.resolve()),
            "input_sha256": input_sha,
            "providers_config_path": str(cfg_path) if cfg_path else None,
            "providers_config_sha256": cfg_sha,
            "offline": offline,
            "cache_root_used": roots.cache_root is not None,
            "oncotree": oncotree_info,
        }
        bundle = RunBundle(run_id=rid, generated_at=finished, somaweave_version=__version__, offline=offline, case=normalized,
                           technical_summary=tech, evidence_sets=evidence_sets, findings=findings, provenance=provenance)
        report = render_json(bundle)
        _write_json(report, run_dir / "reports" / "report.json")
        (run_dir / "reports" / "report.md").write_text(render_markdown(bundle), encoding="utf-8")
        _write_json({"case_id": case.case_id, "run_id": rid, "evidence_sets": [dump_model(es) for es in evidence_sets]},
                    run_dir / "evidence" / "evidence.json")
        _write_json({"case_id": case.case_id, "run_id": rid,
                     "alterations": [{"alteration_id": rr.alteration_id, "status_counts": rr.status_counts(),
                                      "query_results": [dump_model(q) for q in rr.query_results]} for rr in retrievals]},
                    run_dir / "evidence" / "source_queries.json")

        manifest = {
            "run_id": rid,
            "somaweave_version": __version__,
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "pydantic_version": _pydantic_version(),
            "git_commit": provenance["git_commit"],
            "input": {"path": str(case_path.resolve()), "sha256": input_sha, "case_id": case.case_id, "schema_version": case.schema_version},
            "providers_config": {"path": str(cfg_path) if cfg_path else None, "sha256": cfg_sha, "providers": registry.names()},
            "offline": offline,
            "oncotree": oncotree_info,
            "started_utc": started.isoformat(),
            "finished_utc": finished.isoformat(),
            "source_status_counts": status_counts,
            "per_source_status_counts": per_source,
            "environment_variable_names": sorted(k for k in os.environ if k.startswith("SOMAWEAVE_")),
            "roots": {"results_root": str(roots.results_root), "work_root": str(roots.work_root) if roots.work_root else None,
                      "cache_root": str(roots.cache_root) if roots.cache_root else None},
            "outputs": {
                "manifest": "manifest.json", "evidence": "evidence/evidence.json", "source_queries": "evidence/source_queries.json",
                "report_json": "reports/report.json", "report_markdown": "reports/report.md", "technical": "qc/technical.json", "log": "logs/run.log",
            },
            "findings": [{"alteration_id": f.alteration_id, "analytical": f.analytical.level, "oncogenicity": f.oncogenicity.classification,
                          "actionability_tier": f.actionability.tier, "relevance": f.relevance.level} for f in findings],
        }
        _write_json(manifest, run_dir / "manifest.json")
        logger.info("run %s finished; statuses %s", rid, status_counts)
        return RunResult(
            run_id=rid, run_dir=run_dir, case_id=case.case_id, offline=offline, manifest_path=run_dir / "manifest.json",
            report_json_path=run_dir / "reports" / "report.json", report_markdown_path=run_dir / "reports" / "report.md",
            evidence_path=run_dir / "evidence" / "evidence.json", source_queries_path=run_dir / "evidence" / "source_queries.json",
            technical_path=run_dir / "qc" / "technical.json", log_path=run_dir / "logs" / "run.log", status_counts=status_counts,
            findings_summary=manifest["findings"], oncotree_source=oncotree_info["source"],
        )
    except Exception as exc:
        logger.error("run %s failed: %s: %s", rid, type(exc).__name__, exc)
        raise
    finally:
        logger.removeHandler(handler)
        handler.close()


__all__ = ["CaseValidationError", "RootsError", "RunResult", "default_providers_config", "resolve_oncotree", "resolve_roots", "run"]
