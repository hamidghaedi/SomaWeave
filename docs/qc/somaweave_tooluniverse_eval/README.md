# ToolUniverse integration evaluation

Owner work order issued2026-10-18. Executed source:
`6269ffc27774a00135d99d9fb6cd3013b5e6dc9b`, in a clean detached worktree.
PYTHONPATH selects that worktree's src for every engine invocation; the bridge
retains its configured clean environment. The owner's concurrent main-checkout
documentation changes are preserved. No engine/report-rule changes, package
installation, environment upgrade, new reference or other ToolUniverse tool
execution occurred.

Private evaluation root **E**:
`/global/scratch/hpc6049/somaweave_dev/evaluation/tooluniverse/`.
Its `inputs.json`, submissions, native payload caches, query records, case
reports and comparisons remain external. `source_6269ffc/` contains code only;
all inputs/results/caches are outside that Git worktree. Existing environments:
`~/.conda/envs/somaweave` and isolated `~/.conda/envs/tooluniverse`1.5.7.

| Test | Status | Evidence |
|---|---|---|
| T1 | Complete: compute-node bridge and registry retrieval work | Below; E/T1 |
| T2 | Complete:115 queries, no records, all460 axis labels unchanged | Below; E/T2 |
| T3 | Executed; startup finding and exact calls follow | E/T3 |
| T4 | Executed; final gate record follows | E/T4 |

## T1 — compute-node cold provider cache

Slurm job **12363740**, node **frnt152**, COMPLETED, exit **0:0**, scheduler
elapsed **00:00:55**. A newly created, initially empty SomaWeave provider cache
was used. This is a cold provider-cache check, not a claim that remote services
or the operating-system file cache were cold.

```bash
export SOMAWEAVE_TOOLUNIVERSE_PYTHON=$HOME/.conda/envs/tooluniverse/bin/python
export SOMAWEAVE_RESULTS_ROOT=E/T1/results
export SOMAWEAVE_CACHE_ROOT=E/T1/cache_cold
export SOMAWEAVE_REFERENCE_ROOT=/global/scratch/hpc6049/somaweave_dev/reference
export PYTHONPATH=E/source_6269ffc/src
export SOMAWEAVE_INTERPRET_ARGS='--run-id tu-compute-cold-1'
sbatch --account=def-hpcg6049_cpu --time=00:20:00 --mem=2G --cpus-per-task=1 \
  --export=ALL --chdir=E/T1 --output=E/T1/slurm-%j.out \
  E/source_6269ffc/hpc/slurm/interpret_case.sbatch \
  E/source_6269ffc/examples/synthetic_case.json
```

E denotes the literal private root above; actual expanded arguments are in
the submission/log records. Both manifest and source queries bind source6269ffc.
`evidence/source_queries.json` contains two ToolUniverse gene-tier queries:
**ok1 / no_records1 / unavailable0 / error0**. Both carry
`source_version="tooluniverse 1.5.7; ClinicalTrials.gov API v2"`, confirming
the bridge handshake reached the provider. First query duration is **5,912ms**,
including catalogue startup and registry request as measured by the provider;
the subsequent query took286ms. No unavailable message exists to quote.

One trial record was returned on the synthetic case; its category is `trial`,
`is_hypothesis=true`, and its evidence ID is absent from `accepted_ids`.
No axis is cleared or promoted by that record. Native query, timing and
version evidence: E/T1/results/tu-compute-cold-1/evidence/source_queries.json;
summary: E/T1/summary.json. Existing conda entry-point warnings appeared during
activation, but the selected engine interpreter, bridge and run completed;
the verbatim diagnostics remain in the job log. No package fix was attempted.

The full unit, structure and schema gates pass before each evaluation-document
commit; per-commit commands and exit codes are retained in E/validation/.

## T2 — unchanged private inputs with trial retrieval enabled

All three case-v2 input SHA-256 values equal the eval-5 manifests. Each new
manifest records the same executed source6269ffc. Results are named
`<private-case>-eval-6-trials` under E/T2/results; study identifiers and payloads
remain external. No case fields or query terms were adjusted to obtain matches.

Non-ToolUniverse provider payloads were snapshotted into E/T2/cache using hard
links in new provider directories: civic231, clinvar81, europepmc380,
gnomad95 and oncokb96 cache files. The ToolUniverse subdirectory initially did
not exist; no previous ToolUniverse response was reused. The shared original
cache was not purged. Available pre-existing source evidence was reused rather
than refreshed to manufacture label agreement.

Submission used the same pinned `hpc/slurm/interpret_case.sbatch` template and
bridge/reference/PYTHONPATH settings as T1, with:

```bash
export SOMAWEAVE_RESULTS_ROOT=E/T2/results
export SOMAWEAVE_CACHE_ROOT=E/T2/cache
export SOMAWEAVE_INTERPRET_ARGS='--run-id <private-case>-eval-6-trials'
sbatch --account=def-hpcg6049_cpu --time=00:45:00 --mem=2G --cpus-per-task=1 \
  --export=ALL --chdir=E/T2 --output=E/T2/<neutral-label>-%j.out \
  E/source_6269ffc/hpc/slurm/interpret_case.sbatch <unchanged-private-case.json>
```

The literal commands, environment overrides, sbatch exit codes and IDs are in
E/T2/submissions.json. All jobs ran on frnt152 and completed0:0. Scheduler
wall times were53s/73s/45s for case-A/B/C respectively; first ToolUniverse query
durations were19,350ms/19,291ms/19,375ms. Every trial query records
`tooluniverse 1.5.7; ClinicalTrials.gov API v2`.

| Case | Findings / ToolUniverse gene queries | ok | no_records | unavailable / error / other | Trial records | Findings with trials | Four-axis label changes vs eval-5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| case-A | 35 | 0 | 35 | 0 | 0 | 0 | 0 / 140 labels |
| case-B | 52 | 0 | 52 | 0 | 0 | 0 | 0 / 208 labels |
| case-C | 28 | 0 | 28 | 0 | 0 | 0 | 0 / 112 labels |

**All four axes are identical for all115 findings:460 label comparisons,
zero differences.** The same identity also holds against the final
population-enriched eval-5 replay. No defect fix or interpretation-rule change
was made. A successful empty registry search is not missing/failed evidence
and is not evidence that no suitable clinical trial exists.

### Plausibility and hypothesis handling

| Case | Plausible diagnosis/parent match | Disease mismatch | Uninformative basket-only match |
|---|---:|---:|---:|
| case-A | 0 | 0 | 0 |
| case-B | 0 | 0 | 0 |
| case-C | 0 | 0 | 0 |

There are no returned trial records to assess; these zeros do **not** establish
match specificity or exclude false-positive matches in future cases. External
per-case review, including the empty record lists, is
E/T2/plausibility_review.json; aggregate counts/diffs are E/T2/aggregate.json.

For the case with the histology hypothesis, all35 recorded native requests use
exactly the recorded `diagnosis.name` as the ClinicalTrials condition argument.
No hypothesis term is merged into that primary condition. Hypotheses remain
separate planner metadata; they do not appear in the outgoing tool arguments.
The other two cases likewise use their recorded diagnosis names for all80
requests. Actual condition strings/native requests stay in the private review.
No synonym/parent expansion or molecular-hypothesis substitution was introduced.

### Reviewer wording assessment — suggestions only

The separate heading **Clinical trials (registry search; context only)** and
the positive-record statement that eligibility was not evaluated and no tier
is derived are clear. The synthetic T1 match exercises that positive view.
Two limitations remain in the current presentation:

- The real-case subsections display only `none retrieved`, omitting the
  explanatory limitation used when matches exist. Suggested empty-search text:
  **“No registry records were returned for the submitted gene and diagnosis
  text. This does not establish that no suitable trials exist; eligibility
  and biomarker requirements were not assessed.”**
- `Registry matches on gene symbol and recorded diagnosis only` can sound like
  a confirmed biomarker/disease match. Suggested positive-view wording:
  **“These records were returned by a registry free-text search using the gene
  symbol and recorded diagnosis. The gene may occur anywhere in the registry
  text; required alterations, condition applicability and eligibility were not
  assessed. No actionability tier is assigned from these records.”**

The code also renders `none retrieved` when a queried provider is unavailable;
although the coverage table preserves its unavailable status, that wording
could be mistaken for a completed negative search. Suggested separate text:
**“Registry search unavailable; trial availability was not assessed. See source
coverage for the reason.”** This failure presentation was identified by source
inspection, not observed in T1/T2 (unavailable0). These are QC suggestions only;
no report or engine rule was edited.
