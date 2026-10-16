# SomaWeave

**Evidence-grounded somatic cancer genomics interpretation.**

SomaWeave is a research platform that combines somatic genomic findings, specimen and sequencing evidence, clinical history, curated cancer knowledge bases and scientific literature into traceable research interpretations.

**Status:** early development (v0.1). The command-line workflow validates a case, normalizes it, performs deterministic technical assessment, retrieves evidence from CIViC, OncoKB (licensed token), ClinVar and Europe PMC, reconciles and interprets it along four separate axes, and writes a cited JSON and Markdown research report. Research use only; not for standalone clinical decision-making.

## Principles

- Keep analytical validity, oncogenicity, actionability and case relevance separate; no composite score.
- Preserve the original source, evidence level, timestamp and uncertainty behind every claim.
- A failed or skipped query is missing evidence, never negative evidence.
- Never infer clonality or LOH from VAF alone; report compatible scenarios instead.
- Support longitudinal specimens and treatment chronology.
- Keep clinical data, sequencing files, credentials and generated reports outside source control.
- Make local and HPC execution reproducible and portable.

## Start here

Read **[docs/REPOSITORY_CONTRACT.md](docs/REPOSITORY_CONTRACT.md)** before modifying the project. It is the binding directory placement and integration contract.

```bash
conda env create -f hpc/env/somaweave.yaml
conda activate somaweave
python -m pip install -e .

python -m somaweave validate-case examples/synthetic_case.json
export SOMAWEAVE_RESULTS_ROOT=/path/outside/the/repo
python -m somaweave interpret-case examples/synthetic_case.json --offline
python -m somaweave interpret-case examples/synthetic_case.json          # live retrieval
python -m somaweave interpret-case --help                                # roots, cache, providers config, OncoTree

python -m unittest discover -s tests -v
python scripts/check_structure.py
python scripts/export_schemas.py --check
```

## Layout

- `src/somaweave/` — Python implementation: `domain`, `normalization`, `technical`, `providers`, `retrieval`, `evidence`, `interpretation`, `reporting`, `workflows`, `cli.py`.
- `schemas/` — versioned JSON Schemas generated from the domain models (`case.v1`, `evidence.v1`).
- `configs/` — portable, secret-free configuration examples (provider endpoints, rate limits).
- `examples/` — synthetic cases only.
- `tests/` — unit, contract and end-to-end tests with recorded offline fixtures.
- `hpc/` — conda environment spec, Slurm templates and cluster notes.
- `scripts/` — repository QA (`check_structure.py`, `export_schemas.py`).
- `docs/` — specification, architecture, contract, HPC guidance, development rules, roadmap, Phase 0 assessment.

See [architecture](docs/ARCHITECTURE.md), [HPC guidance](docs/HPC.md), [development rules](docs/DEVELOPMENT.md), [roadmap](docs/ROADMAP.md) and the [Phase 0 dependency assessment](docs/PHASE0_ASSESSMENT.md).

## Scope

The workflow covers case and variant normalization, technical QC, retrieval of curated and literature evidence, claim reconciliation, rule-constrained interpretation and structured research reporting. External services are optional adapters behind a stable interface and never become silent mandatory dependencies.

## Licensing

No license is granted by this repository yet. External databases and software remain governed by their respective terms (see `docs/PHASE0_ASSESSMENT.md`).
