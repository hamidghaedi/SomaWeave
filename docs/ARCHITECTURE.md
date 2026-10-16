# Architecture

## Pipeline

```
case JSON
  -> domain.io.load_case            validation against the canonical model (schemas/case.v1)
  -> normalization.normalize_case   HGVS parsing, gene symbols, disease context, partial dates
  -> technical.assess               VAF + CI, expected-VAF scenarios, FFPE/strand/depth flags, chronology
  -> retrieval.plan + retrieval.run six-tier progressive queries through provider adapters
  -> evidence.reconcile             disease match, grouping, conflicts, per-source coverage
  -> interpretation.interpret       four independent axes -> FindingAssessment
  -> reporting.render_json/markdown cited JSON evidence object and Markdown research report
  -> workflows.interpret_case.run   run directory, manifest, logs
```

Scientific calculations are deterministic and separate from prose generation. Provider adapters translate external data to canonical `EvidenceRecord` objects and retain raw source references. Optional analysis frameworks (PCGR, MOAlmanac, BioMCP, ToolUniverse) may be added behind the same adapter interface; they do not determine the directory layout.

## Components and boundaries

| Package | Responsibility | Depends on |
|---|---|---|
| `domain` | Canonical pydantic models and enums; JSON Schema generation | pydantic only |
| `normalization` | HGVS, gene symbol, OncoTree index (built-in subset or full tumorTypes JSON), ICD-O context, partial dates; `NormalizedCase` | `domain` |
| `technical` | Allele fractions, expected VAF scenarios, FFPE/strand/depth/MAPQ flags, treatment chronology, `AnalyticalReliability` | `domain` |
| `providers` | `Provider` interface, rate limiting, transport injection; CIViC, OncoKB, ClinVar, Europe PMC adapters | `domain`, `requests` |
| `retrieval` | `build_query_plan` (six `MatchSpecificity` tiers) and `run_plan` (dedup, offline mode, raw-payload cache) | `domain`, `providers`, `normalization` |
| `evidence` | Disease matching, grouping, conflict detection, source coverage states | `domain`, `normalization` |
| `interpretation` | Rule tables for oncogenicity (VICC-style tags), actionability (AMP/ASCO/CAP tiers with disease-match gate), relevance | `domain`, `technical`, `evidence` |
| `reporting` | JSON and Markdown rendering; every claim cites evidence ids | `domain` |
| `workflows` | Orchestration, run directory, manifest, logging | all of the above |
| `cli.py` | Argument parsing and dispatch only | `workflows`, `domain.io` |

Dependency direction is CLI/workflows -> services -> domain and provider interfaces. Providers never import interpretation or reporting. Technical assessment never consumes language-model output.

## Evidence states

`SourceStatus` distinguishes `ok`, `no_records` (successful query, nothing curated), `unavailable`, `error`, `not_queried`, `no_credentials` and `not_supported`. Only `no_records` may be read as absence of curated evidence in that source; every other non-`ok` state is reported as missing evidence.

## Interpretation axes

`FindingAssessment` carries four independent assessments: `AnalyticalReliability`, `OncogenicityAssessment` (classification + criterion tags), `ActionabilityAssessment` (tier, level, disease match, cross-cancer flag) and `CaseRelevance`. There is no composite score field and none should be added.

## Run layout

`<SOMAWEAVE_RESULTS_ROOT>/<run_id>/{manifest.json, evidence/, reports/, qc/, logs/}`. The manifest records software versions, input hashes, provider configuration hash, per-source status counts and the repository commit when available. Raw provider payloads are cached under `<SOMAWEAVE_CACHE_ROOT>` keyed by request hash and referenced from `EvidenceRecord.raw_reference`.

## Credentials

Providers that need a key read it at query time from an environment variable named in the provider configuration (`api_key_env`) or, for OncoKB, from a token file path (`token_file`, default `~/.oncokb_token`). Key values are never written to configuration, fixtures, logs, manifests or reports; a missing key yields `SourceStatus.no_credentials` for that source.
