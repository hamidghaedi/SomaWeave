# HPC guidance

SomaWeave is a portable Python package; nothing in `src/` depends on a particular cluster. Site-specific values (accounts, roots, environment names) are passed through environment variables and command-line options.

## Environment

```bash
conda env create -f hpc/env/somaweave.yaml     # Python 3.11, pydantic 2, requests, jsonschema
conda activate somaweave
python -m pip install -e .
```

The environment specification is deliberately minimal. Heavyweight optional tools (PCGR, MOAlmanac) should live in separate environments or Apptainer containers if adopted (see `docs/PHASE0_ASSESSMENT.md`).

## Runtime roots

| Variable | Purpose |
|---|---|
| `SOMAWEAVE_RESULTS_ROOT` | Finalized run directories (`<run_id>/manifest.json`, `evidence/`, `reports/`, `qc/`, `logs/`). Required by `interpret-case`. |
| `SOMAWEAVE_CACHE_ROOT` | Raw provider payload cache. Optional; without it nothing is cached. |
| `SOMAWEAVE_WORK_ROOT` | Scratch for per-run temporaries. Optional; defaults to the system temp dir (inside Slurm, `SLURM_TMPDIR`). |
| `SOMAWEAVE_REFERENCE_ROOT` | Read-only references. `oncotree/tumorTypes*.json` (public OncoTree export) enables full disease matching; without it a built-in subset is used and most external disease names resolve to `unknown`, which caps actionability at Tier III. Optional but strongly recommended. |

All roots must be outside the Git checkout and must respect your site's quota and access-control policies.

## Scheduler

Interpretation of a single case is lightweight (seconds to a few minutes, dominated by network latency) and may run on a login node where site policy allows small smoke checks. Batch interpretation and anything heavier goes through Slurm:

```bash
export SOMAWEAVE_RESULTS_ROOT=/path/to/results
sbatch --account=<account> --time=00:15:00 --mem=2G --cpus-per-task=1 \
       --export=ALL hpc/slurm/interpret_case.sbatch examples/synthetic_case.json
sbatch --account=<account> --time=00:10:00 --mem=2G hpc/slurm/run_tests.sbatch
```

Conventions learned from the reference project in this workspace and kept here: specify account and walltime and let the scheduler route the partition; activate conda inside the job before enabling `set -u`; use `SLURM_TMPDIR` for temporaries; write large outputs to allocated scratch, not the repository or login-node `/tmp`.

## Credentials

OncoKB requires an institutional token. Provide it as the `ONCOKB_API_TOKEN` environment variable or in a file readable only by you (default `~/.oncokb_token`, the convention used by other tools in this workspace). Never place it in the repository, job scripts, or `--export` lists that end up in logs. Without a token OncoKB is recorded as `no_credentials` and the run continues.

## Network

Live retrieval needs outbound HTTPS to `civicdb.org`, `www.oncokb.org`, `eutils.ncbi.nlm.nih.gov`, `www.ebi.ac.uk` and `gnomad.broadinstitute.org`. If a node has no outbound access, run with `--offline` (all sources recorded as `not_queried`) or rely on a populated `SOMAWEAVE_CACHE_ROOT`. Unreachable sources are reported as missing evidence, never as negative evidence. The October17 cold-cache compute-node check below covered the original four sources; the new gnomAD provider is separately checked from the login node in item4, not yet verified on compute.

## Data governance

Only synthetic cases live in the repository. Real case JSON, caches and results stay in access-controlled storage. The manifest intentionally omits hostnames and user names; environment variable *names* (not values) are recorded.

## Verified on the development cluster (2026-10-16)

- Conda environment created from `hpc/env/somaweave.yaml`; full unit suite passes.
- Login node: outbound HTTPS to all configured sources worked; offline and live `interpret-case` runs completed.
- Slurm: `hpc/slurm/interpret_case.sbatch` submitted with account and 15 min walltime, no partition; job completed with exit code 0 in 7 s using a warm payload cache. Compute-node outbound network was not exercised by that job.

### Cold-cache verification, 2026-10-17

Both jobs used source commit `bd92e73fed8d992dee34c464fb3418506d348c58`,
one CPU and 2 GiB memory. Scheduler accounting reports:

| Job | Entry point | State | Exit code | Elapsed |
|---|---|---|---|---|
| 12363467 | `hpc/slurm/run_tests.sbatch` | COMPLETED | 0:0 | 00:00:16 |
| 12363468 | `hpc/slurm/interpret_case.sbatch examples/synthetic_case.json` | COMPLETED | 0:0 | 00:00:45 |

The test job passed all 314 tests and the structure check. The interpretation
used a newly created, empty cache and the existing OncoTree reference. Its
manifest records `civic: {ok: 5, no_records: 1}`, `clinvar: {ok: 2}`,
`oncokb: {ok: 2}`, and `europepmc: {ok: 11, no_records: 1}`. All four sources
returned successful responses from the compute node; no source was unavailable
or errored. This verifies outbound HTTPS for these sources on the tested node
and date, not a permanent guarantee for every node or future request.

The existing environment was reused without installations. Submission exported
`PYTHONNOUSERSITE=1` and `CONDA_NO_PLUGINS=true` to isolate conda startup from
incompatible user-site plugins, and selected the existing environment through
`SOMAWEAVE_CONDA_ENV`. Site-specific submission examples and evidence locations
are in `hpc/README.md` and `docs/qc/somaweave_dev_round3/item1.md`.
