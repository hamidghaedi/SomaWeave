# Item 1 — compute-node validation

Completed 2026-10-17 against main `bd92e73fed8d992dee34c464fb3418506d348c58`.
No package, environment or scheduler-template modification was needed.

| Submission | Job | State / exit | Elapsed |
|---|---|---|---|
| `sbatch --account=def-hpcg6049_cpu --time=00:10:00 --mem=2G --cpus-per-task=1 hpc/slurm/run_tests.sbatch` | 12363467 | COMPLETED / 0:0 | 16s |
| `sbatch --account=def-hpcg6049_cpu --time=00:30:00 --mem=2G --cpus-per-task=1 --export=ALL hpc/slurm/interpret_case.sbatch examples/synthetic_case.json` | 12363468 | COMPLETED / 0:0 | 45s |

Actual submissions also directed stdout to external scratch logs and exported
`PYTHONNOUSERSITE=1`, `CONDA_NO_PLUGINS=true`, and the existing environment path.
The interpretation exported the requested results/reference roots and a new,
empty `SOMAWEAVE_CACHE_ROOT`. `SOMAWEAVE_INTERPRET_ARGS` supplied the run ID.

Runtime root: `/global/scratch/hpc6049/somaweave_dev/`.
Cache: `cache_cold_20261017_bd92e73/`.
Evidence: `results/cold-cache-bd92e73-20261017/manifest.json`, reports, queries
and logs; scheduler stdout: `validation_round3/{tests-12363467,cold-12363468}.txt`.
No token was printed or copied.

Manifest `per_source_status_counts`:

| Source | ok | no_records | error / unavailable |
|---|---:|---:|---:|
| civic | 5 | 1 | 0 |
| clinvar | 2 | 0 | 0 |
| oncokb | 2 | 0 | 0 |
| europepmc | 11 | 1 | 0 |

All four sources are reachable over HTTPS from the tested compute node. A
fetch-only CLI is therefore not required to resolve a network block and was
not implemented. Future source failures still remain missing evidence.

Files changed: `docs/HPC.md`, `hpc/README.md`, this report. No runtime artifacts
entered Git. Pre-commit checks use the existing Python: unit discovery,
`scripts/check_structure.py`, and `scripts/export_schemas.py --check`; each
exited 0 (314 tests). The LF scan and `git diff --check` passed. The source remains
self-contained; the neighboring project was used only to confirm existing CPU
account/scheduling conventions.
