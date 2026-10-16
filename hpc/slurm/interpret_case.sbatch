#!/bin/bash
# SomaWeave interpret-case Slurm template.
#
# Account, time, memory and CPUs are passed on the sbatch command line because
# sbatch does not expand environment variables inside #SBATCH directives:
#
#   export SOMAWEAVE_RESULTS_ROOT=/path/to/results
#   sbatch --account=<account> --time=00:10:00 --mem=2G --cpus-per-task=1 \
#          --export=ALL hpc/slurm/interpret_case.sbatch examples/synthetic_case.json
#
# Optional environment:
#   SOMAWEAVE_CONDA_ENV      conda environment name (default: somaweave)
#   SOMAWEAVE_CACHE_ROOT     provider payload cache directory
#   SOMAWEAVE_WORK_ROOT      per-run work directory
#   SOMAWEAVE_INTERPRET_ARGS extra arguments for interpret-case (e.g. "--offline")
#SBATCH --job-name=somaweave-interpret
#SBATCH --nodes=1
#SBATCH --ntasks=1

case_path="${1:?usage: sbatch [sbatch options] interpret_case.sbatch <case.json>}"

if command -v conda >/dev/null 2>&1; then
    source "$(conda info --base)/etc/profile.d/conda.sh"
elif [ -n "${CONDA_EXE:-}" ]; then
    source "$(dirname "$(dirname "$CONDA_EXE")")/etc/profile.d/conda.sh"
else
    echo "conda not found on PATH; load the site conda module before submitting" >&2
    exit 2
fi
conda activate "${SOMAWEAVE_CONDA_ENV:-somaweave}"

set -euo pipefail

export TMPDIR="${SLURM_TMPDIR:-${TMPDIR:-/tmp}}"
: "${SOMAWEAVE_RESULTS_ROOT:?SOMAWEAVE_RESULTS_ROOT must be set and exported (use --export=ALL or --export=ALL,SOMAWEAVE_RESULTS_ROOT=...)}"

echo "job id: ${SLURM_JOB_ID:-n/a}"
echo "case: ${case_path}"
echo "results root: ${SOMAWEAVE_RESULTS_ROOT}"
echo "python: $(command -v python)"
python -m somaweave --version

set +e
# shellcheck disable=SC2086
python -m somaweave interpret-case "${case_path}" ${SOMAWEAVE_INTERPRET_ARGS:-}
rc=$?
set -e
echo "job id: ${SLURM_JOB_ID:-n/a} exit code: ${rc}"
exit "${rc}"
