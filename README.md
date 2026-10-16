# SomaWeave

**Evidence-grounded somatic cancer genomics interpretation.**

SomaWeave is a research platform for combining somatic genomic findings, technical and specimen evidence, clinical history, curated cancer knowledge bases, and scientific literature into traceable research interpretations.

**Status:** Repository scaffold. Interpretation services are planned, not implemented. Not for standalone clinical decision-making.

## Principles

- Keep analytical validity, oncogenicity, actionability, and case relevance separate.
- Preserve the original source, evidence levels, timestamps, and uncertainty behind every claim.
- Support longitudinal specimens and treatment chronology.
- Keep clinical data, sequencing files, credentials, and generated reports outside source control.
- Make local and HPC execution reproducible and portable.

## Start here

Read **[docs/REPOSITORY_CONTRACT.md](docs/REPOSITORY_CONTRACT.md)** before modifying the project. It is the binding directory placement and integration contract for all future development.

```bash
python -m pip install -e .
python -m somaweave validate-case examples/synthetic_case.json
python -m unittest discover -s tests -v
python scripts/check_structure.py
```

## Layout

- `src/somaweave/` — Python implementation, organized by domain and responsibility.
- `schemas/` — versioned input/output JSON contracts.
- `configs/` — portable, non-secret configuration examples.
- `examples/` — synthetic examples only.
- `tests/` — tests and synthetic fixtures.
- `hpc/` — scheduler scripts and cluster deployment templates.
- `scripts/` — maintenance and validation utilities.
- `docs/` — architectural, operational and scientific specifications.

See [architecture](docs/ARCHITECTURE.md), [HPC guidance](docs/HPC.md), [development rules](docs/DEVELOPMENT.md), and [roadmap](docs/ROADMAP.md).

## Scope

The planned workflow encompasses case and variant normalization, technical QC, retrieval of curated and literature evidence, claim reconciliation, rule-constrained interpretation, and structured research reporting. External services are optional adapters and must not silently become mandatory dependencies.

## Licensing

No license is granted by this initial repository. External databases and software remain governed by their respective usage terms.
