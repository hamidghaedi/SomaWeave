# Roadmap

Phases follow `docs/SPEC.md` section 6.

| Phase | Scope | Status |
|---|---|---|
| 0 | Dependency, licensing and environment assessment | Done: `docs/PHASE0_ASSESSMENT.md`, `hpc/env/somaweave.yaml` |
| 1 | Comparative benchmark (ToolUniverse, BioMCP, PCGR, complements) | Planned; benchmark design in the Phase 0 assessment |
| 2 | Core data model and schemas | Done: `domain`, `schemas/*.v1` |
| 3 | Evidence integration | Initial: CIViC, OncoKB, ClinVar, Europe PMC adapters; six-tier retrieval; raw-payload cache; full OncoTree disease matching |
| 4 | Interpretation engine | Initial: technical assessment, reconciliation, rule-based four-axis interpretation with alteration-class applicability gate, OVS1 class-level criterion, OncoKB level mapping |
| 5 | Research reporting | Initial: cited JSON + Markdown reports |
| 6 | Independent validation | Round 1 completed on 3 real cases (see Evaluation rounds); expert-reviewed acceptance criteria still to define |
| 7 | Deployment | Initial: Slurm templates and smoke test |


## Evaluation rounds

| Round | Date | Cases | Outcome |
|---|---|---|---|
| 1 | 2026-10-16 | 3 real cases, 115 variants, run by the sibling project's agent against commit f2f5935 | Found: truncating-class OncoKB evidence lost (SETD2), gene-level fusion/expression/other-variant records tiering small variants, 73 gene-level therapy strings on a VUS, hypothesis rationale missing from the report, `planner` reported as a missing source, shared-cache temp-file race, ClinVar 429s, month-precision dates not representable. All addressed in the commits following 942ae2a; re-run as `<KQ>-eval-2`. |

## Next steps

- Expand oncogenicity rules toward full ClinGen/CGC/VICC scoring with computational and population-frequency inputs (population AF holds such as the KMT2C case are not yet consumed).
- Exon/domain membership for region-class evidence (e.g. 'Exon 3 Mutation') via transcript annotation so region profiles can become variant-matched.
- Structured fields for competing purity fits and manual-review conclusions beyond the quoted `review_outcome`; `preservation` vs storage distinction.
- Add cBioPortal adapter; evaluate BioMCP as an aggregating provider; PCGR as genome-scale input behind Apptainer.
- Load the HGNC table from `SOMAWEAVE_REFERENCE_ROOT`; extend `DiseaseReference` to carry multiple conditions (ClinVar).
- Conflict detection across diseases/variant profiles (currently same category, drugs and variant description only).
- Curated benchmark set across the SPEC section 4 scenario classes; reviewer feedback capture.
- Optional constrained-LLM narrative layer behind the template renderer, with citation checking.
