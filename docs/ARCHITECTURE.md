# Architecture

## Pipeline

```
case JSON
  -> domain.io.load_case            canonical case.v2 model; explicit case.v1 inputs remain compatible
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
| `ingest` | Explicit upstream-to-case.v2 conversion, source hashes, clinical and measurement binding; never interpretation | `domain`, standard library |
| `normalization` | HGVS, gene symbol, OncoTree index (built-in subset or full tumorTypes JSON), ICD-O context, partial dates; `NormalizedCase` | `domain` |
| `technical` | Allele fractions, expected VAF scenarios, FFPE/strand/depth/MAPQ flags, treatment chronology, `AnalyticalReliability` | `domain` |
| `providers` | `Provider` interface, rate limiting, transport injection; CIViC, OncoKB, ClinVar, Europe PMC and gnomAD adapters | `domain`, `requests` |
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

## Evidence applicability (added after the first real-case evaluation)

Every retrieved record is classified by the molecular profile its source describes (`evidence/applicability.py`): exact variant, codon, other specific variant, truncating/loss-of-function class, bare 'loss' (applies only to truncating consequences or copy loss), splice class (donor/acceptor disruption only), functional class (e.g. gain-of-function; gene-level context), exon/domain region, exon indel region (applies only to indels), gene-wide, fusion, expression, copy number. Compound `AND` profiles are applicable only when every component is produced by an alteration recorded in the case; codon matches carry a 'not identical substitution' caveat. A record enters the oncogenicity and actionability pools only when that profile can be produced by the case alteration (`Alteration.consequence_class()` plus alteration type). Fusion, expression and copy-number profiles never apply to small variants; another specific variant in the same gene never applies; truncating-class evidence applies only to truncating consequences. Excluded accepted records are retained as context with the limitation `alteration_class_mismatch:<class>` and counted in `EvidenceSet.excluded_by_class`. Gene-wide profiles and unverified region profiles apply at gene level only: they are capped at Tier III and never contribute therapy names. In case v2 a matching supplied exon verifies region membership and permits class-level variant matching; a known different exon excludes the record.

Therapy and resistance lists come exclusively from variant-matched records (exact, codon, functional-equivalent, applicable class). OncoKB class-level annotations of truncating variants (`variantExist=false` with a loss-of-function effect) are mapped to `gene_alteration_class` and yield the OVS1 criterion tag (likely oncogenic). OncoKB therapeutic levels map to AMP levels as LEVEL_1/2/R1 → A, LEVEL_3A/3B/R2 → C, LEVEL_4 → D, with the disease-match gate unchanged. Multi-condition records (ClinVar) are matched on their best-matching condition; disease hypotheses produce a hypothesis-match summary that is reported but never upgrades the relevance level.

## Dates and read metrics

Clinical dates accept `YYYY`, `YYYY-MM` or full ISO dates (`domain/dates.py`). Chronology asserts a relation only when it holds at the recorded precision and reports day differences as bounded ranges otherwise. `ReadSupport` carries template-level counts (ALT/REF templates, template strand counts), median MAPQ/BQ, clipping and local-mismatch metrics and a quoted manual `review_outcome`. The technical level rule distinguishes measured failures from unmeasured metrics: a variant can be rated `high` only when every core metric is measured and passes; absent metrics are named in the rationale and cap the rating at `moderate`.

## Case v2

The v2 model adds source exon membership, explicit LOH call state, alternative
purity fits, paired structured visual review, strand-count exclusivity,
treatment modality/notes, storage and ingestion provenance. See decision0001.
Known matching exon regions are variant-matched and keep the existing disease
gate; missing membership remains gene context. Every alternative purity fit is
enumerated in source order with no model selection. Non-exclusive strand tests
are nominal only, and never raise the strand-imbalance major flag. Legacy LOH
and review fields remain quoted alongside the typed fields.

## Population and hotspots

Exact GRCh38 alleles query gnomAD v4 for joint population counts. Explicit
source hotspot flags supply OS3 instead of record-count approximations.
Population-frequency cautions keep oncogenicity uncertain without inferring
the patient's germline status or changing the other three axes. Details,
thresholds, schema additions and limitations: `POPULATION_HOTSPOTS.md`.

## Benchmark orchestration

`workflows/benchmark.py` reuses the scientific services to replay canonical
synthetic evidence and compare four axes and review gates against separate
expectations. `scripts/run_benchmark.py` is its repository QA entry point.
Fixtures/expected outcomes live in `tests/benchmark/`; runtime summaries stay
external. Default execution is offline and requires owner adjudication, with
an explicitly labelled offline draft mode for development. Live SomaWeave
retrieval cannot bypass signoff. Comparator execution is not implemented;
see `BENCHMARK.md` and `BENCHMARK_COMPARATORS_DESIGN.md`.
