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
| T2 | Executed; aggregate handoff follows | E/T2 |
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
