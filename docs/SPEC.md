# Evidence-Grounded Somatic Cancer Genomics Interpretation Platform

**Development Specification — Version 0.2**

**Status:** Proposed architecture  
**Primary purpose:** Research interpretation of somatic cancer genomic findings

## 1. Project objective

Develop a modular, reproducible interpretation system that integrates genomic alterations, clinical and pathological context, sequencing quality metrics, established cancer knowledge bases, and biomedical literature.

The system will produce structured, evidence-supported interpretations and human-readable research reports.

Its primary objectives are to:

- Determine the biological and clinical relevance of somatic alterations in the context of a particular tumor.
- Evaluate the technical credibility of the reported genomic findings.
- Retrieve and synthesize evidence from authoritative databases and primary scientific literature.
- Distinguish established evidence from mechanistic hypotheses and uncertain associations.
- Generate reproducible interpretations with traceable citations and explicit limitations.
- Minimize duplicated development by integrating existing, established bioinformatics and AI tools.

The platform must remain independent of specific cancers, genes, variant callers, sequencing platforms, and language-model providers.

## 2. Proposed architecture

The system will consist of six interconnected layers.

### Layer 1 — Case and genomic data ingestion

Accept structured and semi-structured input describing:

- Primary diagnosis, histology, tumor site and stage.
- Clinical history, disease progression, recurrence and metastasis.
- Treatments, timing and documented responses.
- Tissue source, collection date, preservation and tumor purity.
- SNVs, indels, copy-number alterations, structural variants, fusions and other molecular biomarkers.
- Tumor-normal sequencing measurements and associated technical QC metrics.

Support multiple specimens and time points belonging to the same case.

### Layer 2 — Normalization

Convert all inputs into a consistent internal data model.

Core normalization tasks include:

- Genomic coordinates and genome assembly.
- HGVS and gene identifiers.
- Disease classifications using OncoTree and related ontologies.
- Drug and treatment identifiers.
- Specimen roles and anatomical locations.
- Longitudinal clinical event dates.

Maintain both original and normalized values. Flag conflicting diagnoses or classification codes rather than silently correcting them.

### Layer 3 — Genomic annotation and technical assessment

Use existing interpretation systems where appropriate:

**PCGR** — Genome-wide annotation and variant prioritization.

**Molecular Oncology Almanac** — Biomarker and clinical evidence interpretation, subject to appropriate licensing.

Develop custom deterministic functions for:

- Tumor and normal allele fractions.
- Read-level and template-level support.
- Tumor purity and expected VAF.
- Copy-number and LOH effects.
- FFPE-related artifacts.
- Mapping, base-quality and orientation bias.
- Chronology of treatment exposure relative to specimen collection.

Analytical confidence must be evaluated independently from biological significance.

### Layer 4 — Biomedical evidence retrieval

Use **BioMCP** as the preferred initial interface for querying biomedical data sources.

Evaluate **ToolUniverse's Cancer Variant Interpretation skill** as an alternative or complementary agent workflow.

Relevant databases include CIViC, ClinVar, OncoKB, cBioPortal, PubMed, Europe PMC, and additional oncology knowledge resources.

Implement progressive evidence retrieval using:

1. Exact genomic or protein alteration.
2. Codon-level or functionally equivalent changes.
3. Gene alteration class in the same cancer.
4. Gene–disease associations.
5. Pathway or biological mechanism.
6. Cancer-specific treatment, recurrence, progression and resistance literature.

All retrieval operations must retain source identifiers, database versions, query status and timestamps.

### Layer 5 — Evidence reconciliation and interpretation

Normalize retrieved information into a common evidence model.

For each claim, capture:

- Relevant variant and cancer type.
- Biological or clinical assertion.
- Diagnostic, prognostic, predictive or mechanistic evidence category.
- Match specificity to the patient's alteration and disease.
- Study design, sample size and limitations.
- Supporting publication or knowledge-base assertion.
- Source-native evidence level and interpretation status.
- Contradictory evidence, if identified.

Interpretations must maintain separate assessments of:

**Analytical reliability**, **oncogenicity**, **clinical actionability**, and **relevance to the particular case**.

Apply recognized interpretation standards where appropriate, including ClinGen/CGC/VICC oncogenicity criteria and AMP/ASCO/CAP clinical-significance categories.

These distinct frameworks must not be collapsed into a single unvalidated confidence score.

### Layer 6 — Report generation

Produce:

- Structured JSON containing all interpreted findings, evidence and provenance.
- A detailed research interpretation report.
- A concise narrative suitable for review and integration into research reporting workflows.
- Explicit limitations, unresolved questions and technical review flags.

Use constrained language-model generation or templates to assemble the prose.

Every externally supported assertion must have a verifiable citation. Unsupported claims must be removed or explicitly designated as hypotheses.

## 3. Integration strategy

Existing tools will be evaluated before becoming core dependencies.

| Tool | Primary role |
|---|---|
| BioMCP | Unified biomedical retrieval |
| ToolUniverse | AI-guided investigation workflows |
| PCGR | Genome-scale somatic interpretation |
| Molecular Oncology Almanac | Complementary biomarker interpretation |
| CIViC MCP | Direct retrieval of curated assertions |
| Literature extraction module | Variant- and cancer-specific research evidence |
| Custom interpretation engine | Clinical and technical integration |
| Custom report generator | Evidence-grounded research prose |

The platform must support provider substitution, offline testing, source-specific credentials and partial operation when an external service is unavailable.

## 4. Evaluation and benchmarking

Before finalizing the architecture, compare existing systems using a curated benchmark.

The benchmark should include:

- Common and clinically actionable driver mutations.
- Rare tumors with characteristic molecular alterations.
- Variants associated with recurrence or metastasis.
- Treatment resistance and treatment-timing scenarios.
- Ambiguous VAF and copy-number configurations.
- FFPE artifacts and technically unreliable calls.
- Discordant pathology and genomic evidence.
- Cases with insufficient or conflicting literature.
- Genome-level findings involving CNVs, fusions or signatures.

Evaluate source retrieval, variant–disease specificity, interpretation accuracy, citation validity, reproducibility, runtime and cost.

The existing CTNNB1 p.Asp32Asn case may serve as a development test fixture, but independent cases must be used for unbiased benchmarking.

## 5. Implementation approach

Use Python as the primary implementation language.

Start with a command-line application and structured JSON interfaces. Add API and web-based review interfaces after validating the core engine.

The architecture should provide independent modules for:

- Data intake and validation.
- Molecular and clinical normalization.
- Technical assessment.
- Provider adapters.
- Literature retrieval.
- Evidence extraction and reconciliation.
- Interpretation rules.
- Narrative generation.
- Report rendering.
- Reviewer decisions and provenance.

Maintain automated unit, integration, contract and end-to-end tests.

External API failures, missing credentials and unavailable evidence must be represented explicitly.

## 6. Development phases

**Phase 0 — Dependency and environment assessment:** Review existing projects, licensing, software versions, and deployment requirements. Inspect the applicable HPC environment and established execution patterns in the primary operational reference project before choosing installation or scheduling mechanisms.

**Phase 1 — Comparative benchmark:** Test ToolUniverse, BioMCP, PCGR and eligible complementary systems.

**Phase 2 — Core data model:** Implement reusable case, specimen, alteration, source and evidence schemas.

**Phase 3 — Evidence integration:** Implement programmatic retrieval and normalized evidence storage.

**Phase 4 — Interpretation engine:** Integrate deterministic technical analysis, cancer-specific interpretation rules and evidence reconciliation.

**Phase 5 — Research reporting:** Generate source-grounded JSON and prose reports.

**Phase 6 — Independent validation:** Evaluate unseen cases with expert review and explicitly defined acceptance criteria.

**Phase 7 — Deployment:** Add scalable execution, optional API/UI and workflow integration. Validate configuration, storage separation, and scheduler-based execution in the target environment.

Each phase must deliver independently testable components.

## 7. Quality, safety and governance

The system is initially intended for research use.

It must:

- Keep identifiable clinical information within an authorized environment.
- Minimize data transmitted to external APIs.
- Respect third-party database licensing and usage restrictions.
- Maintain immutable source and interpretation provenance.
- Preserve contradictory findings and unresolved uncertainty.
- Prevent the generation of unsupported treatment recommendations.
- Require qualified human review before conclusions are used clinically.

## 8. Minimum viable product

The initial working system must be able to accept a de-identified clinical case with one or more somatic variants and associated sequencing QC measurements.

It must then:

1. Validate and normalize the inputs.
2. Retrieve relevant curated database evidence.
3. Search and extract supporting published evidence.
4. Evaluate applicable technical and biological considerations.
5. Integrate the findings with the patient's diagnosis and treatment timeline.
6. Produce a machine-readable evidence object.
7. Generate a coherent, source-cited research interpretation.
8. Highlight uncertainty, conflicts and missing information for expert review.

**Completion criterion:** Another analyst must be able to reproduce the interpretation, inspect the evidence behind each claim, and identify which conclusions are established, inferred or unresolved.

## 9. Repository governance and HPC implementation requirements

### 9.1 Governing project documents

SomaWeave development must comply with the repository's current governing documents:

- `docs/SPEC.md` (this document) defines scientific scope and functional/non-functional requirements.
- `docs/ARCHITECTURE.md` defines component responsibilities and integration boundaries.
- `docs/REPOSITORY_CONTRACT.md` defines mandatory file placement, dependency boundaries, runtime data separation, and contribution rules, including HPC conventions.
- `README.md` provides the project overview and user-facing setup guidance.

At project initialization, the checkout contains only `README.md` and these three documents. The directory ownership table in `docs/REPOSITORY_CONTRACT.md` specifies where future components belong; it does **not** require empty directories or premature application scaffolding. Add components incrementally as required by implemented functionality. Resolve document conflicts explicitly before consequential changes and update affected documents together.

### 9.2 Primary HPC operational reference

The current primary development workspace is `/global/project/hpcg6049/somatic_pipeline/SomaWeave`. The sibling project `../somatic_pipeline_sm`, resolved **relative to the SomaWeave checkout**, is the primary operational reference for the HPC environment.

Before implementing or modifying dependencies, containers, scheduler jobs, filesystem settings, workflow execution, or deployment steps, examine the relevant working examples in that reference project. Determine, as applicable:

- Python, package management, modules, container runtimes, and reproducible environment definitions.
- Slurm submission patterns, approved resource requests, job monitoring, restart behavior, and noninteractive execution.
- Project, shared, scratch, temporary, cache, and results storage conventions; quotas and permissions.
- Reference-data access, network restrictions, software distribution, and credential handling.
- Run provenance, logs, checksums, version pinning, and recovery practices.

The reference project is **read-only unless explicit permission is provided**. Reuse compatible patterns rather than copying private data, credentials, environments, or code indiscriminately. Other nearby projects may inform individual decisions when relevant. Institutional HPC policy and verified current cluster behavior take precedence over historical examples.

These locations are documented context, **not hardcoded application defaults or runtime dependencies**. SomaWeave must operate independently of the sibling checkout and use configurable paths and site-specific settings.

### 9.3 Runtime and portability requirements

- Maintain a portable, installable Python application; isolate HPC job wrappers and templates from reusable scientific algorithms according to the repository contract.
- Configure working space, results, caches, and reference resources outside Git, using the runtime-root conventions in `docs/REPOSITORY_CONTRACT.md`.
- Keep raw case data, patient-identifiable information, secrets, large genomic inputs, software environments, logs, and generated results out of source control.
- Use scheduler-supported execution for compute-intensive workloads; reserve login nodes for approved lightweight operations.
- Preserve run-level provenance, including inputs and their hashes where appropriate, software/database/reference versions, configuration, and source revision.
- Support noninteractive execution, explicit failure reporting, restartability where practical, and bounded resource use.
- Account for unreliable or absent external API connectivity through configured caches, explicit source-status reporting, and offline test fixtures. Do not silently treat unreachable sources as negative evidence.

### 9.4 Verification and acceptance

An HPC-related implementation change is not complete solely because code or a batch script passes static checks. It must include appropriate lightweight tests and, when authorized and available, a small scheduler-based smoke test. Record the environment, commands, observed results, and unresolved limitations. Do not claim cluster validation when the cluster was not accessed.

HPC-specific implementation detail belongs in `docs/REPOSITORY_CONTRACT.md`, operational documentation, and approved configuration examples; this specification states the required behavior and constraints without duplicating full site-specific procedures.

---

**Recommended initial implementation:** Build the canonical case/evidence model and deterministic technical interpretation modules around BioMCP. Evaluate ToolUniverse as an optional research agent and PCGR as a genome-scale input. Add further providers only when benchmarks show a meaningful benefit.