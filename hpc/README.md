# HPC usage

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
