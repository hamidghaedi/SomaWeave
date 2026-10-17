"""Read-only benchmark replay and per-axis comparison, never adjudication.

Offline mode replays explicitly synthetic canonical evidence and query states;
it does not pretend to have contacted providers. Expected outcomes are separate
owner-reviewed inputs. This module never generates or updates expectations.
Live mode delegates to the existing interpretation workflow and requires signed
expectations. Runtime summaries and live bundles must stay outside the checkout.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from somaweave import __version__
from somaweave.domain.assessment import AmpTier, OncogenicityClass, RelevanceLevel, ReliabilityLevel
from somaweave.domain.io import load_case
from somaweave.evidence import reconcile
from somaweave.interpretation import interpret
from somaweave.normalization import normalize_case
from somaweave.retrieval import RetrievalResult
from somaweave.technical import assess_alteration


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Adjudication(_Strict):
    status: Literal["pending_owner", "owner_signed_off"]
    reviewer: str | None = None
    reviewed_at: date | None = None

    def signed(self):
        return self.status == "owner_signed_off" and bool(self.reviewer and self.reviewed_at)


class ExpectedFinding(_Strict):
    analytical: ReliabilityLevel
    oncogenicity: OncogenicityClass
    actionability: AmpTier
    relevance: RelevanceLevel
    excluded_by_class: dict[str, int] = Field(default_factory=dict)
    analytical_flags: list[str] = Field(default_factory=list)
    review_flags_contains: list[str] = Field(default_factory=list)
    review_flag_count: int = Field(ge=0)
    treatment_context_contains: list[str] = Field(default_factory=list)
    treatment_context_forbidden: list[str] = Field(default_factory=list)
    reason: str


class Expectations(_Strict):
    adjudication: Adjudication
    findings: dict[str, ExpectedFinding]


class Scenario(_Strict):
    scenario_id: str
    spec_class: int = Field(ge=1, le=9)
    title: str
    case: str
    evidence: str
    expected: str


class Benchmark(_Strict):
    schema_version: Literal["benchmark.v1"]
    scenarios: list[Scenario] = Field(min_length=1)


def _input(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"invalid benchmark input: {relative}")
    return path


def _offline(case, evidence_path):
    data = json.loads(evidence_path.read_text(encoding="utf-8"))
    expected_ids = {a.alteration_id for a in case.alterations}
    if set(data) != expected_ids:
        raise ValueError("fixture alteration IDs differ from the case")
    normalized = normalize_case(case)  # built-in ontology subset, not a live reference download
    out = {}
    for alt in case.alterations:
        retrieved = RetrievalResult.model_validate(data[alt.alteration_id])
        if retrieved.case_id != case.case_id or retrieved.alteration_id != alt.alteration_id:
            raise ValueError("fixture case/alteration identity mismatch")
        es = reconcile(normalized, alt, retrieved)
        finding = interpret(normalized, alt, assess_alteration(case, alt), es)
        out[alt.alteration_id] = (finding.model_dump(mode="json"), es.excluded_by_class)
    return out


def _live(case_path, prefix, results_root, cache_root, providers_config):
    from somaweave.workflows.interpret_case import run

    result = run(case_path, run_id=prefix, results_root=results_root, cache_root=cache_root,
                 providers_config=providers_config)
    report = json.loads(result.report_json_path.read_text(encoding="utf-8"))
    return {f["assessment"]["alteration_id"]: (f["assessment"], f["excluded_by_class"]) for f in report["findings"]}


def _md(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def evaluate(case_dir, out, *, allow_draft=False, live=False, results_root=None,
             cache_root=None, providers_config=None, run_id_prefix=None):
    """Write a Markdown comparison; return 0 for agreement, 1 for mismatches.

    Unadjudicated expectations raise before retrieval unless allow_draft;
    live runs always require adjudication. Scores are per-axis agreements,
    never a composite biological/clinical confidence score.
    """
    root, output = Path(case_dir).resolve(), Path(out).resolve()
    checkout = Path(__file__).resolve().parents[3]
    if output.is_relative_to(checkout) or output.is_relative_to(root):
        raise ValueError("benchmark output must be outside the checkout and fixture directory")
    manifest_path = _input(root, "benchmark.json")
    manifest = Benchmark.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if len({s.scenario_id for s in manifest.scenarios}) != len(manifest.scenarios):
        raise ValueError("duplicate benchmark scenario ID")
    loaded = []
    hashes = {"benchmark.json": hashlib.sha256(manifest_path.read_bytes()).hexdigest()}
    for scenario in manifest.scenarios:
        paths = [_input(root, p) for p in (scenario.case, scenario.evidence, scenario.expected)]
        for p in paths:
            hashes[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
        case = load_case(paths[0])
        expected = Expectations.model_validate_json(paths[2].read_text(encoding="utf-8"))
        if set(expected.findings) != {a.alteration_id for a in case.alterations}:
            raise ValueError(f"expected allele IDs differ: {scenario.scenario_id}")
        if expected.adjudication.status == "owner_signed_off" and not expected.adjudication.signed():
            raise ValueError("signed expectations require reviewer and review date")
        loaded.append((scenario, paths, case, expected))
    draft = any(not e.adjudication.signed() for _, _, _, e in loaded)
    if draft and (live or not allow_draft):
        raise ValueError("owner-adjudicated expectations required; --allow-draft permits offline development replay only")
    if live and not run_id_prefix:
        raise ValueError("live benchmark requires an explicit run ID prefix")
    package = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        digest.update(str(path.relative_to(package)).encode() + b"\0" + path.read_bytes() + b"\0")
    lines = ["# SomaWeave benchmark comparison", "",
             "**DRAFT EXPECTATIONS — not owner-adjudicated accuracy.**" if draft else "Owner-adjudicated expectations.",
             "", "Mode: " + ("live provider retrieval" if live else "offline synthetic evidence replay; no network"), "",
             f"SomaWeave version: {__version__}. Package SHA-256: `{digest.hexdigest()}`.", "",
             "| Scenario / allele | Axis | Expected | Actual | Agreement |", "|---|---|---|---|---|"]
    agreements = {axis: [0, 0] for axis in ("analytical", "oncogenicity", "actionability", "relevance")}
    mismatches = []
    for scenario, paths, case, expected in loaded:
        actual = (_live(paths[0], f"{run_id_prefix}-{scenario.scenario_id}", results_root, cache_root, providers_config)
                  if live else _offline(case, paths[1]))
        if set(actual) != set(expected.findings):
            raise ValueError(f"actual allele IDs differ: {scenario.scenario_id}")
        for allele, target in expected.findings.items():
            finding, excluded = actual[allele]
            for axis, key in (("analytical", "level"), ("oncogenicity", "classification"), ("actionability", "tier"), ("relevance", "level")):
                observed, wanted = finding[axis][key], getattr(target, axis)
                agree = observed == wanted
                agreements[axis][0] += agree
                agreements[axis][1] += 1
                lines.append(f"| {_md(scenario.scenario_id)} / {_md(allele)} | {axis} | {wanted} | {observed} | {agree} |")
                if not agree:
                    mismatches.append(f"{scenario.scenario_id}/{allele}: {axis}: expected {wanted}, actual {observed}")
            checks = {
                "excluded_by_class": excluded == target.excluded_by_class,
                "analytical_flags": sorted(finding["analytical"]["flags"]) == sorted(target.analytical_flags),
                "review_flags": len(finding["review_flags"]) == target.review_flag_count and
                all(any(t in flag for flag in finding["review_flags"]) for t in target.review_flags_contains),
                "treatment_context": all(any(t in text for text in finding["relevance"]["treatment_context"])
                                         for t in target.treatment_context_contains) and
                not any(t in text for t in target.treatment_context_forbidden for text in finding["relevance"]["treatment_context"]),
            }
            observations = {
                "excluded_by_class": (target.excluded_by_class, excluded),
                "analytical_flags": (target.analytical_flags, finding["analytical"]["flags"]),
                "review_flags": ({"contains": target.review_flags_contains, "count": target.review_flag_count}, finding["review_flags"]),
                "treatment_context": ({"contains": target.treatment_context_contains, "forbidden": target.treatment_context_forbidden},
                                      finding["relevance"]["treatment_context"]),
            }
            for name, agree in checks.items():
                wanted, observed = observations[name]
                lines.append(f"| {_md(scenario.scenario_id)} / {_md(allele)} | {name} | {_md(json.dumps(wanted, sort_keys=True))} | "
                             f"{_md(json.dumps(observed, sort_keys=True))} | {agree} |")
                if not agree:
                    mismatches.append(f"{scenario.scenario_id}/{allele}: {name}: expected {json.dumps(wanted, sort_keys=True)}; "
                                      f"actual {json.dumps(observed, sort_keys=True)}")
    lines.extend(["", "Per-axis agreement counts (no composite score):", ""])
    lines.extend(f"- {axis}: {n}/{total}" for axis, (n, total) in agreements.items())
    lines.extend(["", "Disagreements:", ""] + ([f"- {m}" for m in mismatches] or ["- None."]))
    lines.extend(["", "Input SHA-256 (expectations are read-only):", ""])
    lines.extend(f"- `{name}`: `{digest}`" for name, digest in sorted(hashes.items()))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return int(bool(mismatches))
