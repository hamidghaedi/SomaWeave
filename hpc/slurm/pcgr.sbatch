#!/bin/bash
# Supply account/time/memory/CPUs with sbatch. Runtime config is external JSON.
# SOMAWEAVE_PYTHON must name the existing environment's Python executable.
# Optional SOMAWEAVE_APPTAINER_MODULE selects a verified site module.
# Alternatively SOMAWEAVE_APPTAINER names a verified executable directly.
# With --array=0-N, argument 1 is a newline-separated list of config paths.
#SBATCH --job-name=somaweave-pcgr
#SBATCH --nodes=1
#SBATCH --ntasks=1
set -euo pipefail
config="${1:?usage: pcgr.sbatch external_run.json}"
if [ -n "${SLURM_ARRAY_TASK_ID:-}" ]; then
    mapfile -t configs < "$config"
    config="${configs[$SLURM_ARRAY_TASK_ID]:?array index has no run config}"
fi
: "${SOMAWEAVE_PYTHON:?set the existing environment Python executable}"
if [ -n "${SOMAWEAVE_APPTAINER_MODULE:-}" ]; then
    module load "$SOMAWEAVE_APPTAINER_MODULE"
fi
"$SOMAWEAVE_PYTHON" -m somaweave.comparators.pcgr run "$config"
