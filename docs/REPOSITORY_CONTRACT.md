# SomaWeave repository layout contract

**Status: normative. Applies to every future change, including local HPC work.**

**Current repository state:** The checkout contains the Python package under `src/somaweave/` (all packages in the ownership table), `schemas/`, `configs/`, `examples/`, `tests/` with offline fixtures, `hpc/` and `scripts/`, in addition to `docs/`. The paths in Section 2 define ownership; directories not yet present are created only when a component needs them.

## 1. Core invariants

1. Before creating any file, determine its owner using the placement table below. Do not create miscellaneous top-level directories or place source files in the repository root.
2. Application code belongs exclusively under `src/somaweave/`. Reusable logic must never live in notebooks, `scripts/`, or batch job files.
3. Dependencies flow from CLI/workflows -> services -> domain models and provider interfaces. Providers do not import the CLI or reporting layer. Technical assessments must not depend on language model output.
4. Every external integration is isolated behind an adapter; no provider-specific response structures leak into the canonical evidence model.
5. Runtime results, private case data, caches, reference genomes, models, software environments, and logs never enter Git.
6. Every new module includes tests and relevant documentation. Every schema-changing PR includes a versioned schema, migration notes, and compatible examples.
7. Move or rename files only while updating imports, tests, documentation, and this contract within the same change.
8. Repository changes must be deterministic, reviewable, and scientifically traceable. No hardcoded HPC usernames, accounts, queue names, absolute mount points, tokens, or subject identifiers.
9. Documentation, source comments, and commit messages describe only the product and technical changes. Do not include authorship-tool branding, generation metadata, or unrelated scaffolding.
10. Scientific assertions must preserve evidence provenance and explicitly distinguish lack of evidence from a failed query.

## 2. Directory ownership

| Path | Contents | Never put here |
|---|---|---|
| `src/somaweave/domain/` | Canonical case, specimen, alteration and evidence types | HTTP calls, file IO |
| `src/somaweave/normalization/` | Genome, ontology, drug and variant normalization | Source API plumbing |
| `src/somaweave/technical/` | Purity, VAF, copy number, FFPE, read QC algorithms | Treatment recommendations |
| `src/somaweave/providers/` | API clients, response parsers, rate limits, source status | Final prose |
| `src/somaweave/retrieval/` | Multi-source query plans and deduplication | Provider-specific DTOs outside adapters |
| `src/somaweave/evidence/` | Evidence matching, conflicts, grading and source links | Unattributed generated claims |
| `src/somaweave/interpretation/` | Case-aware rules and synthesis | Raw network clients |
| `src/somaweave/reporting/` | JSON, Markdown, template rendering | Genomic calculations |
| `src/somaweave/workflows/` | Orchestration of pipeline stages | Core scientific algorithms |
| `src/somaweave/cli.py` | CLI argument parsing and dispatch | Business logic |
| `schemas/` | Versioned, machine-readable contracts | Patient records |
| `configs/` | Safe example settings | API secrets |
| `examples/` | Synthetic educational inputs | Real patients |
| `tests/` | Unit, contract, integration tests and synthetic fixtures | Unredacted clinical records |
| `hpc/` | Slurm templates (`hpc/slurm/`), conda environment specs (`hpc/env/`), cluster usage notes (`hpc/README.md`) | Platform algorithms, site accounts or paths |
| `tests/fixtures/<package>/` | Recorded provider responses and synthetic inputs used by offline tests | Live-recorded data containing identifiers, tokens or real patients |
| `docs/decisions/` | Architecture decision records when ownership or design is ambiguous | Runtime outputs |
| `scripts/` | Repository QA and maintenance commands | Reusable library logic |
| `docs/` | Architecture, methods, operations, decisions | Runtime outputs |
| `.github/workflows/` | CI workflows only | Cluster-specific credentials |

New packages must have a clear single owner. If ownership is ambiguous, document an architecture decision under `docs/decisions/` before adding a path.

Schema policy: export the current model under its declared version and retain
older committed schemas unchanged. Case v2 adds optional source context while
continuing to load explicit case.v1 inputs; its migration is documented in
`docs/decisions/0001-case-schema-v2.md`.

## 3. Runtime directory contract

Outside the checkout, configure:

- `SOMAWEAVE_WORK_ROOT`: per-run work and temporary files, ideally node-local or allocated scratch.
- `SOMAWEAVE_RESULTS_ROOT`: finalized research reports and structured evidence, with access controls.
- `SOMAWEAVE_CACHE_ROOT`: versioned source caches, not authoritative inputs.
- `SOMAWEAVE_REFERENCE_ROOT`: read-only genomic references and local annotation resources.

Each run has a unique ID and directory tree: `<results_root>/<run_id>/{manifest.json,evidence/,reports/,qc/,logs/}`. Store case-sensitive input references and tool/source versions in the manifest. Never imply data are reproducible without preserving their versions and hashes. Raw patient inputs belong in access-controlled upstream storage, not in Git or examples.

## 4. Interfaces and scientific assertions

- Canonical variant identity includes assembly and normalized representation; never merge cross-build positions without an explicit transform.
- Preserve raw tumor and normal counts, independent template metrics, and QC flags separately from derived VAF.
- Evidence records include source name, native identifier, retrieval status, retrieval timestamp, disease/variant match, evidence type, and limitations.
- Store disease classification hypotheses separately from pathology-confirmed diagnosis.
- Track treatment start/end timestamps independently from specimen timestamps.
- Keep empirical claims and mechanistic hypotheses separate; reject uncited externally derived claims in final reports.
- Source access failure, unavailable evidence, and true negative evidence have different states.
- Use research-use labeling; expert review is mandatory before clinical use.

## 5. Changes and review

Each change requires: placement check, type/schema validation where applicable, tests, an updated documentation reference, and a review of Git-tracked files for sensitive data and irrelevant generated artifacts. Structural changes require updating this document and, when necessary, `docs/ARCHITECTURE.md`. No new ungoverned parallel layouts.

## 6. HPC environment and reference implementations

### 6.1 Development context and reference priority

SomaWeave is developed primarily in a Linux HPC environment using Slurm. The current project workspace is:

`/global/project/hpcg6049/somatic_pipeline/SomaWeave`

The **primary operational reference** is the existing sibling project:

`../somatic_pipeline_sm`

Resolve this sibling path **relative to the SomaWeave repository root**, not relative to an arbitrary command working directory. Other nearby working projects may be consulted when they offer relevant verified patterns, but `../somatic_pipeline_sm` is the starting point for environment and execution questions.

These paths document the current development context. They are **not application defaults or hardcoded runtime dependencies**; application code and portable job templates must continue to use configurable paths, in accordance with Section 1.

The SomaWeave specification, architecture, and this contract govern **what is implemented and where it belongs**. The reference project supplies established examples of **how software runs in this HPC environment**. Current institutional cluster policy and access controls take precedence over either project's operational examples.

### 6.2 Mandatory discovery before HPC-related implementation

Before creating or changing package environments, installation instructions, containers, Slurm scripts, workflow execution, filesystem configuration, or computationally intensive code, inspect the relevant parts of `../somatic_pipeline_sm` and verify current cluster behavior.

At minimum, determine what is applicable from the following:

1. **Environment management:** Python versions; virtual environments, Conda/Mamba, modules, or containers; dependency files and version pinning; and how environments are activated in batch jobs.
2. **Job scheduling:** Slurm submission patterns, partitions and accounts configured for the project, resource requests, time limits, concurrency, job arrays, dependencies, retries, and failure handling.
3. **Execution conventions:** entry points, workflow launch methods, noninteractive execution, executable discovery, working-directory handling, and logging conventions.
4. **Filesystem and storage:** project versus scratch usage, temporary space (including node-local allocations where supported), read-only references, shared resources, results, caches, quotas, and cleanup policies.
5. **Data movement and network constraints:** approved methods for staging inputs, retrieving public database resources, shared filesystem access, outbound network availability, and credential handling.
6. **Reproducibility:** versioned configurations, containers or environment specifications, run manifests, checksums, provenance, monitoring, and restart/resume behavior.

Inspect only what is necessary for the task. Do not expose secrets, copy private datasets, or include environment-specific identifiers in tracked configuration or logs.

### 6.3 Reference projects are read-only

- Treat `../somatic_pipeline_sm` and other neighboring projects as **read-only references** unless the user explicitly authorizes changes to them.
- Never install software into, overwrite files within, clean up, or otherwise alter a reference project's environment, storage, jobs, or repository.
- Reuse **patterns and interfaces**, not private data, credentials, absolute paths, or incidental project-specific assumptions.
- Reuse existing shared tools or reference resources only when access and suitability are verified. Do not introduce a runtime dependency on a sibling checkout merely because it is available locally.
- When a reference implementation is incompatible with SomaWeave's requirements, document the reason and use a portable alternative consistent with this contract.

### 6.4 SomaWeave execution and environment rules

- Keep the Python application installable and runnable independently of any particular HPC account, path, or partition.
- Use environment variables and version-controlled, **secret-free** configuration examples for site-specific settings. Validate required paths and resources at runtime.
- Place scientific algorithms and reusable execution logic under `src/somaweave/`; `hpc/` contains only scheduler templates, wrappers, and cluster-oriented setup examples.
- Submit compute-intensive processing through the approved scheduler. Limit login-node activity to lightweight editing, inspection, environment discovery, and small smoke checks.
- Use cluster-supported environment and container mechanisms. Avoid unapproved installations, redundant environment copies, uncontrolled background workloads, and repeated downloads.
- Store intermediate files, caches, references, logs, and outputs in the configured external locations defined in Section 3. Respect quotas, permissions, cleanup rules, and any restrictions on node-local scratch.
- Make batch tasks noninteractive, parameterized, resumable where appropriate, and explicit about resource requests, failures, and exit status.
- Record sufficient execution provenance to reproduce a run: software/environment versions, input identifiers or checksums, configuration, reference versions, source revisions, and relevant scheduler metadata.
- Never infer that a command, tool, partition, storage location, or network route is usable without confirming it in the current environment.

### 6.5 HPC change acceptance checks

For any change that affects environment setup, job submission, storage, dependency management, or workflow execution:

1. Confirm that the relevant existing pattern in `../somatic_pipeline_sm` was reviewed, or explicitly record why inspection was unavailable or unnecessary.
2. Verify adherence to the repository layout, particularly the separation of reusable code, HPC wrappers, configuration, and runtime data.
3. Validate paths, permissions, dependency availability, and resource assumptions without exposing sensitive information.
4. Run lightweight local tests first; where practical and authorized, perform a small scheduler-based smoke test before scaling up.
5. Record what was actually tested versus what remains unverified. Do not claim successful cluster operation based only on syntactic checks.
6. Update `docs/ARCHITECTURE.md`, this contract, and any relevant operational documentation if environment decisions or layout responsibilities change.

**Guiding rule:** Learn the HPC operating conventions from functioning nearby projects, but keep SomaWeave self-contained, governed by its own repository contract, and portable across supported compute environments.
