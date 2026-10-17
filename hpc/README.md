# HPC usage

Development-cluster verification (2026-10-17) used the CPU account
`def-hpcg6049_cpu`, environment `~/.conda/envs/somaweave`, and runtime root
`/global/scratch/hpc6049/somaweave_dev/`. These are deployment examples only.
The cold-cache job used `cache_cold_20261017_bd92e73`, run ID
`cold-cache-bd92e73-20261017`, and logs under `validation_round3/`.

This directory holds scheduler templates and the conda environment
specification. No scientific logic lives here; everything the templates run is
in `src/somaweave/` through the `somaweave` CLI.

## Environment

```bash
conda env create -f hpc/env/somaweave.yaml
conda activate somaweave
python -m pip install -e .
```

Set `SOMAWEAVE_CONDA_ENV` if the environment has another name.

## Runtime roots

The workflow reads these variables (CLI flags override them):

| Variable | Purpose | Required |
|---|---|---|
| `SOMAWEAVE_RESULTS_ROOT` | `<results_root>/<run_id>/{manifest.json,evidence/,reports/,qc/,logs/}` | yes |
| `SOMAWEAVE_CACHE_ROOT` | raw provider payload cache (created if absent) | no |
| `SOMAWEAVE_WORK_ROOT` | per-run work directory | no |

Keep all three outside the Git checkout, on project or scratch storage with
appropriate access controls. The manifest records only the *names* of
`SOMAWEAVE_*` variables, never their values, and no hostname.

## Reference data (`SOMAWEAVE_REFERENCE_ROOT`)

Disease matching uses the public OncoTree `tumorTypes` JSON when it is
available; otherwise a small built-in subset is used and the manifest says
`oncotree: built-in subset` (many CIViC/OncoKB disease labels then resolve to
`unknown`, which caps actionability at tier III). Point
`SOMAWEAVE_REFERENCE_ROOT` at a directory laid out as
`<reference_root>/oncotree/tumorTypes_<version>.json` (the newest stamped file
is used, or `tumorTypes.json` if present), or pass `--oncotree-json <file>` to
`interpret-case`. Download a pinned release once from the login node (outbound
HTTPS is allowed there), e.g. with `<reference_root>` =
`/global/scratch/<user>/somaweave_dev/reference`:

```bash
mkdir -p "$SOMAWEAVE_REFERENCE_ROOT/oncotree"
curl -s 'https://oncotree.mskcc.org/api/versions'          # pick a stable api_identifier
curl -s 'https://oncotree.mskcc.org/api/tumorTypes?version=oncotree_2025_10_03' \
     -o "$SOMAWEAVE_REFERENCE_ROOT/oncotree/tumorTypes_oncotree_2025_10_03.json"
sha256sum "$SOMAWEAVE_REFERENCE_ROOT/oncotree/tumorTypes_oncotree_2025_10_03.json"
```

The manifest records the file path, the version stamp parsed from the file
name and its sha256, so a run is reproducible against a pinned release. Do not
commit the JSON (about 240 KB per release, licensed by MSKCC); keep it under
the reference root with the other site-specific data.

## Submitting a run

`sbatch` does not expand environment variables inside `#SBATCH` directives, so
the account and resources are given on the command line rather than inside the
template:

```bash
export SOMAWEAVE_RESULTS_ROOT=/path/to/results
export SOMAWEAVE_CACHE_ROOT=/path/to/cache        # optional
sbatch --account=<account> --time=00:10:00 --mem=2G --cpus-per-task=1 \
       --export=ALL hpc/slurm/interpret_case.sbatch examples/synthetic_case.json
```

Use `--export=ALL,SOMAWEAVE_RESULTS_ROOT=/path/to/results` to set the root
inline. Extra CLI arguments go through `SOMAWEAVE_INTERPRET_ARGS`, e.g.
`SOMAWEAVE_INTERPRET_ARGS="--offline"` for a run that contacts no source
(every query is then recorded as `not_queried`, which is missing evidence,
not negative evidence). No partition is set; the site default applies.

The script activates conda, enables `set -euo pipefail` only after activation
(conda hooks are not strict-mode clean), points `TMPDIR` at `SLURM_TMPDIR`
when available, and prints the job id and exit code at the end of the log.

## Running the test suite under Slurm

```bash
sbatch --account=<account> --time=00:10:00 --mem=2G --cpus-per-task=1 hpc/slurm/run_tests.sbatch
```

The job runs `python -m unittest discover -s tests -v` and
`scripts/check_structure.py` from the submission directory. Tests never use
the network.

## Login-node use

Validation (`somaweave validate-case`), offline runs and the unit suite are
light enough for a login node. Online runs query external APIs at the rates set
in `configs/providers.example.json`; submit them as jobs when processing more
than a handful of cases.
