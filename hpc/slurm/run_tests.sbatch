#!/bin/bash
# Run the SomaWeave unit/contract/integration suite under Slurm.
#
#   sbatch --account=<account> --time=00:10:00 --mem=2G --cpus-per-task=1 hpc/slurm/run_tests.sbatch
#
# Run from the repository root (the script changes to SLURM_SUBMIT_DIR). Tests
# never contact the network. SOMAWEAVE_CONDA_ENV overrides the environment name.
#SBATCH --job-name=somaweave-tests
#SBATCH --nodes=1
#SBATCH --ntasks=1

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
cd "${SLURM_SUBMIT_DIR:-$(pwd)}"

echo "job id: ${SLURM_JOB_ID:-n/a}"
echo "python: $(command -v python)"
set +e
python -m unittest discover -s tests -v
rc=$?
python scripts/check_structure.py
rc2=$?
set -e
echo "job id: ${SLURM_JOB_ID:-n/a} unit tests exit code: ${rc}; structure check exit code: ${rc2}"
[ "${rc}" -eq 0 ] && [ "${rc2}" -eq 0 ]
