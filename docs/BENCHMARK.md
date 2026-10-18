# Benchmark contract and proposed adjudication

Status: implementation ready for offline development replay; **expected
outcomes await owner signoff**. This is not an independently validated clinical
accuracy result. All nine scenarios are newly authored synthetic inputs,
covering the nine SPEC section4 classes. No patient data, development KQ inputs,
live payloads, OncoTree/HGNC reference export or SPN development example is used.
Counts, dates, responses and evidence statements are fictional. Source-shaped
evidence is marked `synthetic-offline-v1` and is not a literature assertion.

`tests/benchmark/benchmark.json` lists three read-only files per scenario:
`*.case.json`, canonical synthetic `*.evidence.json`, and separate
`*.expected.json`. Expected files contain the four axes, exact analytical flag
sets, required review-flag phrases plus exact review-flag count, excluded-class
counts, required/forbidden treatment-context phrases and a rationale. Every file has an
adjudication block currently set to `pending_owner`, with blank reviewer/date.
No script generates or updates expected outcomes from observed results.

The following is the concrete proposed adjudication for review. Labels describe
the explicitly supplied synthetic evidence, not independently established
patient biology. `likely_oncogenic` below reflects the deliberately limited
single-source evidence; it is not a statement about the entire literature on
those alleles.

| SPEC class / scenario | Finding | Analytical | Oncogenicity | Tier | Relevance | Critical checks |
|---|---|---|---|---|---|---|
| 1 / `01_driver` | BRAF V600E, melanoma | high | likely_oncogenic | I | high | clean paired metrics; same-disease level A |
| 2 / `02_rare_tumour` | KIT W557_K558del, GIST | high | likely_oncogenic | II | high | rare tumour independent of the SPN development fixture |
| 3 / `03_recurrence` | TERT promoter, glioblastoma | high | likely_oncogenic | II | high | synthetic prognostic association; no invented individual recurrence probability |
| 4 / `04_resistance_timing` | EGFR T790M, lung adenocarcinoma | high | likely_oncogenic | I | high | erlotinib ends before collection; resistance distinct from alternative-agent evidence |
| 5 / `05_vaf_cn` | BRAF V600E with competing fits | high | uncertain_significance | IV | none | no curated evidence; unresolved fits and uncalled LOH remain unchosen |
| 6 / `06_ffpe_artifact` | BRAF V600E in FFPE material | unreliable | likely_oncogenic | IV | none | upstream artefact, low templates and strand imbalance do not erase independent biology |
| 7 / `07_discordant_pathology` | KRAS G12C with discordant disease context | high | likely_oncogenic | III | low | hypothesis does not replace diagnosis; cross-cancer cap and pathology flag |
| 8 / `08_insufficient_conflicting`, A1 | APC truncation with opposing statements | high | uncertain_significance | IV | none | conflict; fusion/expression evidence excluded (one each) |
| 8 / `08_insufficient_conflicting`, A2 | separate CTNNA1 allele | high | not_assessed | not_assessed | not_assessable | source outage stays missing, not negative |
| 9 / `09_genome_findings`, A1 | ERBB2 amplification | not_assessable | uncertain_significance | I | high | clinical class-level evidence; no invented read metrics or intrinsic-oncogenicity assertion |
| 9 / `09_genome_findings`, A2 | KIF5B::RET fusion | not_assessable | uncertain_significance | I | high | clinical evidence remains separate from measured technical reliability |

Class9 covers CNVs and fusions, not signatures. Class6 tests explicit artefact
review and FFPE read-quality concerns; it has no genomic substitution and does
not simulate measured cytosine-deamination chemistry. Exact flags and source
states are in the expected/evidence JSON files. These narrow fixtures test the
specified evidence contracts; they are not a substitute for an independent
clinical validation cohort or comprehensive performance estimates.

Owner review should approve or revise each proposed outcome, flags and evidence
scope before marking the corresponding expectation `owner_signed_off` and
recording the reviewer/date. The runner checks those fields, not the identity
of the reviewer; the recorded owner decision and Git history provide signoff.
No owner decision has been recorded by this implementation.

## Adjudication procedure

Only the owner performs this procedure. The agent does not sign expectations.
Review the [round4 line-by-line sheet](qc/somaweave_dev_round4/benchmark_review_sheet.md):
it separates supplied evidence, the proposed expected labels, engine rule
names and advisory assessments. Agreement with the current replay is not
accuracy and is not the criterion for approving an expected label.

1. Review each finding and record the owner decision in the sheet. A scenario
   with two findings needs a decision on both before its expectation file is
   signed. The table alone does not enable scoring.
2. The owner edits that scenario's `tests/benchmark/<scenario>.expected.json`.
   If an expected label/check changes, revise the relevant finding and its
   `reason` to record the scientific rationale. Preserve unrelated fields and
   source fixtures; do not copy current outputs into expectations automatically.
3. In the same file, the owner sets only the adjudication block's `status` to
   `owner_signed_off`, `reviewer` to their name, and `reviewed_at` to the actual
   ISO day (`YYYY-MM-DD`). Commit the label/rationale changes and signature in
   the same commit. Review `git diff -- tests/benchmark/*.expected.json` before
   committing. Unreviewed scenarios remain `pending_owner` with blank metadata.
4. After all scenarios are signed, use the existing SomaWeave Python to run
   the normal command below **without** `--allow-draft`. Save the report and
   actual command/exit code outside Git. Exit0 means agreement with the signed
   expectations; exit1 is a discrepancy to investigate; exit2 indicates invalid
   inputs or incomplete signoff. Disagreement never authorizes tuning engine
   rules or rewriting expected labels merely to obtain agreement.

```bash
python scripts/run_benchmark.py \
  --out "$SOMAWEAVE_RESULTS_ROOT/benchmark-owner-adjudicated.md"
```

The output directory must be outside the checkout. No helper is required:
manual JSON edits and the reviewed commit provide the decision record. This
procedure does not sign the separate genomic-map review or comparator crosswalk.

## Running

Reusable logic belongs to `workflows/benchmark.py`; the repository QA command
is `scripts/run_benchmark.py`. Default mode never contacts a provider. It
replays synthetic query states, reconciles/assesses through the actual engine,
compares each axis independently and writes Markdown **outside the checkout**.
It does not write into inputs or expected files. Input SHA-256 values are
included. A mismatch exits1; invalid input or absent required signoff exits2;
agreement exits0. There is no composite confidence score.

```bash
python scripts/run_benchmark.py --allow-draft \
  --out "$SOMAWEAVE_RESULTS_ROOT/benchmark-draft.md"
```

Without `--allow-draft`, pending expectations fail before retrieval. A draft
comparison is prominently labelled as unadjudicated, even if every value agrees.
Live mode also requires signed expectations and an explicit run-ID prefix:

```bash
python scripts/run_benchmark.py --live --run-id-prefix benchmark-approved-v1 \
  --results-root "$SOMAWEAVE_RESULTS_ROOT" \
  --cache-root "$SOMAWEAVE_CACHE_ROOT" \
  --out "$SOMAWEAVE_RESULTS_ROOT/benchmark-live.md"
```

`--allow-draft` cannot bypass live signoff. Live mode runs **SomaWeave's existing
providers only**, records normal bundles/manifests and reports source failures
honestly. No PCGR, ToolUniverse or BioMCP execution is implemented or implied.
Live source contents can differ from the fixed synthetic fixtures, so live
disagreement is a review result, not permission to rewrite expectations. Most
fixtures deliberately have protein-only identity; exact genomic retrieval is
then unsupported. Their present form is not a ready-made PCGR input.

Next stage: [comparator design](BENCHMARK_COMPARATORS_DESIGN.md), awaiting
separate owner approval. Development evidence: item5 under
`docs/qc/somaweave_dev_round3/`.

## Disagreement found during development replay (resolved)

The first replay found all 11 findings agreeing on each proposed axis, with
analytical/review flags and excluded classes agreeing. Scenario04 failed the
narrative chronology check: the technical module retained bounded day ranges
for month-precision dates, but `interpretation/interpret.py` formatted the
exact-day field as "None days after" in treatment context. The expectation
forbidding that wording was kept; the interpretation module now renders the
bounded range ("32-89 days (recorded date precision) after the end of ...")
whenever the exact day count is unavailable, and a unit regression test covers
month-precision treatment dates. The replay now reports no disagreements.
