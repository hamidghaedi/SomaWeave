# Roadmap

Phases follow `docs/SPEC.md` section 6.

| Phase | Scope | Status |
|---|---|---|
| 0 | Dependency, licensing and environment assessment | Done: `docs/PHASE0_ASSESSMENT.md`, `hpc/env/somaweave.yaml` |
| 1 | Comparative benchmark (ToolUniverse, BioMCP, PCGR, complements) | Planned; benchmark design in the Phase 0 assessment |
| 2 | Core data model and schemas | Done: case v2 with compatible v1 input loading; evidence v1 |
| 3 | Evidence integration | Initial: CIViC, OncoKB, ClinVar, Europe PMC and gnomAD v4 adapters; six-tier retrieval; raw-payload cache; full OncoTree disease matching |
| 4 | Interpretation engine | Initial: technical assessment, reconciliation, rule-based four-axis interpretation with alteration-class applicability gate, OVS1 class-level criterion, OncoKB level mapping |
| 5 | Research reporting | Initial: cited JSON + Markdown reports |
| 6 | Independent validation | Round 1 completed on 3 real cases (see Evaluation rounds); expert-reviewed acceptance criteria still to define |
| 7 | Deployment | Initial: Slurm templates and smoke test |


## Evaluation rounds

| Round | Date | Cases | Outcome |
|---|---|---|---|
| 1 | 2026-10-16 | 3 real cases, 115 variants, evaluated against commit f2f5935 | Found: truncating-class OncoKB evidence lost (SETD2), gene-level fusion/expression/other-variant records tiering small variants, 73 gene-level therapy strings on a VUS, hypothesis rationale missing from the report, `planner` reported as a missing source, shared-cache temp-file race, ClinVar 429s, month-precision dates not representable. All addressed in the commits following 942ae2a; re-run as `<KQ>-eval-2`. |

## Next steps

- Owner-adjudicated benchmark set across all nine SPEC section4 classes and an offline comparison harness.
- Review the comparator design before any PCGR, BioMCP or ToolUniverse implementation or installation.
- Independent scientific validation of research oncogenicity rules; the current criterion tags do not constitute a full validated ClinGen/CGC/VICC classifier.
- Verify transcript/domain membership when a case does not already provide exon context; no implicit transcript inference.
- Add cBioPortal/HGNC support where required, with source/version contracts; preserve separation from treatment evidence.
- Optional constrained narrative generation remains separate future work with citation checks.

## Development work order, 2026-10-17

Compute-node cold-cache verification is complete (all four sources reachable;
see HPC guidance). Case v2 addresses structured exon membership, LOH state,
competing fits, visual review, strand dependence, modality and storage. The v1
schema is frozen, with compatible v1 input loading. Maintained ingestion is complete (`3c20149`); compatible-description conflict
detection and source-policy verification are complete (`3ef0035`). Population/
hotspot adapters and conservative rules are implemented with offline and live
checks; the three-case comparison is recorded in item4. Benchmark adjudication
and external comparators remain separate owner-review stages. Case fields do
not establish upstream assay validation or clinical readiness.
