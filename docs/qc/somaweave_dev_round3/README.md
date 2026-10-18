# Development work-order evaluation, 2026-10-17

Runtime root: `/global/scratch/hpc6049/somaweave_dev/`. Inputs, live payloads,
case diffs and run results remain external. This directory contains technical
evaluation narratives only. No environments/packages were installed.

| Item | Implementation commit | Report / status |
|---|---|---|
| 1 | `4c53bc267a45db9dfaaefa4fca750bffd6c759fd` | [Compute-node checks](item1.md): complete |
| 2 | `59d0fae3aa1b9b23c6278c347e5bb6e71c804675` | [Case v2](item2.md): complete |
| 3 | `3c2014916d51713e028769528d58bbbd9e497804` | [Ingestion](item3.md): complete |
| 4 | `176579f8c893d7e3ed9061ce1c7f9f465718155b` | [Population/hotspots](item4.md): complete |
| 5 | Commit introducing `scripts/run_benchmark.py` and this index | [Benchmark](item5.md): implementation complete, owner adjudication pending |
| 6 | `3ef0035ae55c3678d32ebb8e2ad53eecb4c2e5b9` | [Hygiene](item6.md): complete; current Europe PMC full terms could not be fetched |

Item6 was explicitly allowed at any time and committed independently between
items3 and4. Each commit passed the unit, structure and schema gates before
push. Resolve the exact item5 SHA with
`git log -1 --format=%H -- scripts/run_benchmark.py`; the final external
`validation_round3/completion.json` also maps all six items to commits and
lists every touched document. This avoids embedding a commit's own hash into
its content. Final suite: 352 tests, with no network in unit tests.

## Final real-case replay

All three `<case>-eval-5-population-final` runs completed from clean source
commit `176579f`, with unchanged `cases_v2/` inputs and no scientific tuning.
All 115 rows are compared with eval-5 in
`validation_round3/item4/axes_vs_eval5.tsv`, including reviewed decisions,
categories and separately reported upstream/current OncoKB classification.
No four-axis labels changed. Source cautions are additions, not reportability
decisions or new germline calls.

Final gnomAD statuses: case-A `{ok:29,no_records:6}`,
case-B `{ok:35,no_records:17}`, case-C `{ok:27,no_records:1}`. The two temporary
initial failures recovered. All final manifests bind the committed code;
commands/exit codes and source hashes are in item4's `final_runs/` audit.
Other sources' full counters remain in the manifests, not copied into Git.

## Outstanding decisions

The [nine-class proposed benchmark outcomes](../../BENCHMARK.md) remain
`pending_owner`; no reviewer/date or approval was invented. Default and live
benchmark scoring refuse unsigned expectations. The explicitly labelled draft
offline replay agrees on all four axes for 11 findings and passes flag/class
checks, but this is not adjudicated scientific accuracy.

One chronology narrative check deliberately fails: month-precision treatment
context prints "None days after" even though the technical layer retains day
ranges. The failing expectation remains visible; no engine rule was tuned to
the benchmark. This rendering defect remains open.

The [external-comparator design](../../BENCHMARK_COMPARATORS_DESIGN.md) is
provided for approval. No PCGR, BioMCP or ToolUniverse installation/execution
occurred. Protein-only fixtures need reviewed genomic mappings before PCGR;
AI/ML comparison using OncoKB additionally needs the source's permission.
