# SomaWeave

**Evidence-grounded somatic cancer genomics interpretation.**

SomaWeave is a research platform that combines somatic genomic findings, specimen and sequencing evidence, clinical history, curated cancer knowledge bases and scientific literature into traceable research interpretations.

**Status:** early development (v0.1). The command-line workflow validates a case, normalizes it, performs deterministic technical assessment, retrieves evidence from CIViC, OncoKB (licensed token), ClinVar, Europe PMC and gnomAD plus clinical-trial registry context via ToolUniverse, reconciles and interprets it along four separate axes, and writes a cited JSON and Markdown research report. Research use only; not for standalone clinical decision-making.

## How it works

The diagrams go from coarse to fine: the system layers first, then the
interpretation pipeline, then one diagram per layer. Every box corresponds to a
package or file that exists under `src/somaweave/` at this commit.

### Level 0 — System layers

```mermaid
flowchart TB
    IN["<b>Inputs</b><br/>per-case pipeline outputs + clinical history<br/>(outside Git)"]
    ENG["<b>SomaWeave engine</b><br/>ingest → normalize → technical QC → retrieve → reconcile → interpret → report<br/>deterministic, rule-based, fully cited"]
    OUT["<b>Outputs</b><br/>run directory: manifest, evidence, four-axis report (JSON + Markdown), QC, log"]
    KB["<b>External knowledge</b><br/>CIViC · OncoKB · ClinVar · Europe PMC · gnomAD<br/>ClinicalTrials.gov (via ToolUniverse) · OncoTree"]
    AG["<b>Agents and clients</b><br/>CLI · MCP tools (ToolUniverse, Claude Code, any MCP client)"]
    VAL["<b>Validation</b><br/>synthetic benchmark (owner-adjudicated) · PCGR comparator · real-case replays"]

    IN --> ENG --> OUT
    KB <--> ENG
    AG --> ENG
    OUT --> VAL
```

### Level 1 — Interpretation pipeline

```mermaid
flowchart LR
    case["case.v2 JSON"] --> norm["Normalization<br/><i>normalization/</i>"]
    norm --> tech["Technical assessment<br/><i>technical/</i>"]
    tech --> ret["Tiered retrieval<br/><i>retrieval/ + providers/</i>"]
    ret --> rec["Reconciliation<br/><i>evidence/</i>"]
    rec --> int["Four-axis interpretation<br/><i>interpretation/</i>"]
    int --> rep["Reporting<br/><i>reporting/</i>"]
    rep --> run["Run directory<br/>SOMAWEAVE_RESULTS_ROOT/run_id/"]
    wf["Orchestration<br/><i>workflows/interpret_case.py</i>"] -.-|drives| norm
    wf -.-|drives| rep
```

Each stage writes only to the next; database-specific code never reaches
`interpretation/`, and `interpretation/` never performs network calls.

### Level 2a — Inputs and ingestion

```mermaid
flowchart LR
    subgraph upstream["Upstream pipeline outputs (per case, outside Git)"]
        maf["Somatic calls<br/>MAF / VCF"]
        purple["PURPLE<br/>purity, ploidy, copy number"]
        bam["BAM review<br/>tumour and normal read support"]
        picard["Picard metrics<br/>depth, insert size, FFPE context"]
        clin["Clinical history<br/>diagnosis, specimens, treatments"]
        lab["Lab manifest<br/>assay, assembly, specimen type"]
    end
    build["build-case<br/><i>ingest/</i>"]
    case["case.v2 JSON<br/>schemas/case.v2.schema.json"]
    maf & purple & bam & picard & clin & lab --> build --> case
    case --> val["validate-case"]
```

Ingestion converts and records provenance; it never interprets. Partial dates
(month or year precision) are preserved as such and propagate as bounded ranges
through chronology and reporting.

### Level 2b — Knowledge sources and tiered retrieval

```mermaid
flowchart LR
    plan["Retrieval planner<br/><i>retrieval/plan.py</i><br/>tiers: exact_variant → codon →<br/>functional_equivalent → gene_alteration_class →<br/>gene → pathway"]
    cache[("Payload cache<br/>SOMAWEAVE_CACHE_ROOT")]
    oncotree[("OncoTree release JSON<br/>reference file")]

    subgraph direct["Direct HTTPS adapters (providers/)"]
        civic["CIViC<br/>GraphQL"]
        oncokb["OncoKB<br/>token required; hotspot flag"]
        clinvar["ClinVar<br/>E-utilities"]
        epmc["Europe PMC<br/>REST"]
        gnomad["gnomAD<br/>GraphQL, population AF"]
    end
    subgraph bridge["Isolated environment (hpc/env/tooluniverse.yaml)"]
        tubr["tooluniverse_bridge.py<br/>stdlib, JSON lines"] --> tu["ToolUniverse 1.5.7"] --> ctg["ClinicalTrials.gov API v2<br/>gene tier; condition hierarchy<br/>diagnosis → OncoTree → lineage → basket"]
    end

    plan <--> cache
    plan <--> civic & oncokb & clinvar & epmc & gnomad
    plan <--> tubr
    oncotree --> plan
    plan --> rec["Reconciliation<br/><i>evidence/</i><br/>applicability class, acceptance,<br/>disease match, conflicts"]
```

Every query is recorded with source, tier, status and timestamp. An
unreachable, unlicensed or empty source is `unavailable` / `no_credentials` /
`no_records` — missing evidence, never negative. `--offline` runs the whole
engine with every source `not_queried`. Trial-registry records carry
`evidence_category = trial` and are never accepted, so they cannot influence
any axis.

### Level 2c — What feeds each interpretation axis

```mermaid
flowchart TB
    subgraph inputs["Inputs"]
        reads["Read support, depth, strand,<br/>normal-template ALT reads"]
        spec["Specimen: FFPE/fresh,<br/>purity, ploidy, copy number"]
        pop["gnomAD population AF"]
        kb["Curated evidence<br/>(CIViC, OncoKB, ClinVar)"]
        lit["Literature<br/>(Europe PMC)"]
        dx["Diagnosis, hypotheses,<br/>OncoTree lineage"]
        tx["Treatment chronology<br/>(partial dates allowed)"]
    end
    A["Analytical reliability<br/>high / moderate / low / unreliable"]
    O["Oncogenicity<br/>ClinGen/CGC/VICC criteria tags"]
    T["Actionability<br/>AMP/ASCO/CAP tier I-IV, level A-D;<br/>variant-matched therapies only"]
    R["Case relevance<br/>disease match, hypothesis dependence,<br/>treatment context"]
    reads & spec & pop --> A
    pop & kb & lit --> O
    kb & dx --> T
    dx & tx & kb --> R
    A -.-|"no composite score"| O
    O -.-|"no composite score"| T
    T -.-|"no composite score"| R
```

The four labels are reported side by side and never combined. Clonality and
LOH are never inferred from VAF alone; the technical layer lists the
copy-number/purity scenarios compatible with the observed VAF instead.
Cross-cancer evidence is labelled as such and capped at Tier III.

### Level 2d — Agent access and validation

```mermaid
flowchart LR
    subgraph agents["Agents and clients"]
        tuc["ToolUniverse<br/>load_mcp_tools(url)"]
        mcpc["Any MCP client<br/>(stdio or HTTP)"]
        cli["Shell / Slurm<br/>python -m somaweave"]
    end
    mcp["MCP server<br/><i>serve/mcp_server.py</i><br/>somaweave_validate_case · build_case ·<br/>interpret_case · list_runs · get_run · get_report"]
    engine["SomaWeave CLI<br/>(SOMAWEAVE_PYTHON)"]
    runs[("Run directories<br/>SOMAWEAVE_RESULTS_ROOT")]

    tuc & mcpc --> mcp --> engine
    cli --> engine --> runs
    mcp -.->|"paths, manifest summaries,<br/>report text on request"| runs

    subgraph validation["Validation (scripts/, comparators/)"]
        bench["Synthetic benchmark<br/>9 scenarios, 11 findings<br/>expectations pending owner sign-off"]
        pcgr["PCGR comparator<br/><i>comparators/pcgr/</i><br/>export VCF → Apptainer PCGR → parse<br/>side-by-side, no label equivalence"]
    end
    runs --> bench & pcgr
```

### Candidate tools: what was adopted and what was not

| Resource | Status in SomaWeave | Role |
|---|---|---|
| CIViC | **Adopted** — `providers/civic.py` | Predictive / prognostic / diagnostic evidence items and assertions with levels, disease (DOID) and drugs |
| OncoKB | **Adopted** — `providers/oncokb.py` (institutional academic token, outside Git) | Oncogenicity, therapeutic levels, hotspot flag; class-level evidence for truncating variants |
| ClinVar | **Adopted** — `providers/clinvar.py` | Germline/somatic classifications with review status and conditions, quoted not re-derived |
| Europe PMC | **Adopted** — `providers/europepmc.py` | Literature retrieval and citation validation |
| gnomAD | **Adopted** — `providers/gnomad.py` | Population allele frequency as an analytical/oncogenicity caution |
| OncoTree | **Adopted** — `normalization/disease.py` (versioned release JSON as a reference file) | Disease code, name, synonym and lineage resolution |
| ToolUniverse | **Adopted, two ways** — data layer `providers/tooluniverse.py` + stdlib bridge in an isolated environment; SomaWeave exposed back to it as MCP tools (`serve/`) — [docs/TOOLUNIVERSE.md](docs/TOOLUNIVERSE.md) | ClinicalTrials.gov registry context on the gene tier (never evidence, no tier derived); agent access to the engine |
| PCGR | **Comparator implemented** — `comparators/pcgr/` ([docs/PCGR_COMPARATOR.md](docs/PCGR_COMPARATOR.md)); existing PCGR 2.2.5 image + GRCh38 bundle on the HPC, read-only | Side-by-side native labels on the synthetic benchmark (7 of 8 scenarios complete) and aggregate counts on private cases; oncogenicity crosswalk pending owner review; never adjudicated truth |
| cancerhotspots.org | Not integrated | Hotspot flag taken from OncoKB instead; no duplicated hotspot source |
| cBioPortal | Assessed, optional later | Cohort frequency context only; never an actionability source |
| Molecular Oncology Almanac | Assessed, optional later | Would consume the database JSON directly, not the algorithm package |
| BioMCP | Assessed, not adopted | MCP wrapper over sources already queried directly |
| Djerba (OICR) | **Integration designed, not implemented** — [docs/DJERBA_APPENDIX_INTEGRATION.md](docs/DJERBA_APPENDIX_INTEGRATION.md) | SomaWeave as the deterministic evidence engine behind the sibling pipeline's planned human-reviewed evidence appendix; Djerba remains the only report engine |

Details and licence notes: [docs/PHASE0_ASSESSMENT.md](docs/PHASE0_ASSESSMENT.md), [docs/POPULATION_HOTSPOTS.md](docs/POPULATION_HOTSPOTS.md), [docs/INGESTION.md](docs/INGESTION.md), [docs/BENCHMARK.md](docs/BENCHMARK.md), [docs/TOOLUNIVERSE.md](docs/TOOLUNIVERSE.md), [docs/PCGR_COMPARATOR.md](docs/PCGR_COMPARATOR.md).

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

python -m somaweave build-case --help                                      # upstream files -> case.v2 JSON
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

- `src/somaweave/` — Python implementation: `domain`, `ingest`, `normalization`, `technical`, `providers`, `retrieval`, `evidence`, `interpretation`, `reporting`, `workflows`, `comparators`, `serve`, `cli.py`.
- `schemas/` — versioned JSON Schemas generated from the domain models (`case.v1`, `case.v2`, `evidence.v1`).
- `configs/` — portable, secret-free configuration examples (provider endpoints, rate limits).
- `examples/` — synthetic cases only.
- `tests/` — unit, contract and end-to-end tests with recorded offline fixtures.
- `hpc/` — conda environment spec, Slurm templates and cluster notes.
- `scripts/` — repository QA (`check_structure.py`, `export_schemas.py`) and the synthetic benchmark runner (`run_benchmark.py`).
- `docs/` — specification, architecture, contract, HPC guidance, development rules, roadmap, Phase 0 assessment.

See [architecture](docs/ARCHITECTURE.md), [HPC guidance](docs/HPC.md), [development rules](docs/DEVELOPMENT.md), [roadmap](docs/ROADMAP.md) and the [Phase 0 dependency assessment](docs/PHASE0_ASSESSMENT.md).

## Using SomaWeave from agents

`src/somaweave/serve/mcp_server.py` exposes the CLI as Model Context Protocol tools (`somaweave_validate_case`, `somaweave_build_case`, `somaweave_interpret_case`, `somaweave_list_runs`, `somaweave_get_run`, `somaweave_get_report`). It runs the engine as a subprocess in `SOMAWEAVE_PYTHON`, returns run identifiers, paths and four-axis labels, and can be loaded into ToolUniverse or any MCP client. See [docs/TOOLUNIVERSE.md](docs/TOOLUNIVERSE.md).

## Scope

The workflow covers case and variant normalization, technical QC, retrieval of curated and literature evidence, claim reconciliation, rule-constrained interpretation and structured research reporting. External services are optional adapters behind a stable interface and never become silent mandatory dependencies.

## Licensing

No license is granted by this repository yet. External databases and software remain governed by their respective terms (see `docs/PHASE0_ASSESSMENT.md`).
