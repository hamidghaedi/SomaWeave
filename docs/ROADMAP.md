# Roadmap

Phases follow `docs/SPEC.md` section 6.

| Phase | Scope | Status |
|---|---|---|
| 0 | Dependency, licensing and environment assessment | Done: `docs/PHASE0_ASSESSMENT.md`, `hpc/env/somaweave.yaml` |
| 1 | Comparative benchmark (ToolUniverse, BioMCP, PCGR, complements) | Planned; benchmark design in the Phase 0 assessment |
| 2 | Core data model and schemas | Done: `domain`, `schemas/*.v1` |
| 3 | Evidence integration | Initial: CIViC, OncoKB, ClinVar, Europe PMC adapters; six-tier retrieval; raw-payload cache; full OncoTree disease matching |
| 4 | Interpretation engine | Initial: technical assessment, reconciliation, rule-based four-axis interpretation |
| 5 | Research reporting | Initial: cited JSON + Markdown reports |
| 6 | Independent validation | Not started |
| 7 | Deployment | Initial: Slurm templates and smoke test |

## Next steps

- Expand oncogenicity rules toward full ClinGen/CGC/VICC scoring with computational and population-frequency inputs.
- Add cBioPortal adapter; evaluate BioMCP as an aggregating provider; PCGR as genome-scale input behind Apptainer.
- Load the HGNC table from `SOMAWEAVE_REFERENCE_ROOT`; extend `DiseaseReference` to carry multiple conditions (ClinVar).
- Conflict detection across diseases/variant profiles (currently same category, drugs and variant description only).
- Curated benchmark set across the SPEC section 4 scenario classes; reviewer feedback capture.
- Optional constrained-LLM narrative layer behind the template renderer, with citation checking.
