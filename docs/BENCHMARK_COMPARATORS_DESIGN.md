# External comparator design

Owner work order issued 2026-10-18 approves the PCGR track using the existing
2.2.5 image, reference20250314 and VEP113, read-only. This is the approved
comparison release, irrespective of newer public releases described below.
The original design follows for context. BioMCP/ToolUniverse and any
OncoKB-consuming LLM comparison remain deferred. Owner expectation signatures,
genomic-map review and crosswalk approval remain separate decisions.
Execution and limitations: [round4 handoff](qc/somaweave_dev_round4/README.md).

This is a design for the second stage requested in the development work order,
aligned with PHASE0_ASSESSMENT section3. No comparator was installed, downloaded,
submitted or invoked. The first-stage runner only exercises SomaWeave. Owner
adjudication of benchmark expectations and approval of this stage are separate
decisions.

## Inputs and boundaries

Freeze an approved benchmark revision and expected outcomes before running any
system. Keep all real cases external; the synthetic fixtures must not be given
the status of an independent clinical validation cohort. Preserve four separate
axes, the original inputs, source-native assertions, match specificity and
source failures. No tuning against the comparator or automatic replacement of
owner expectations is permitted.

PCGR needs verified genomic identities for its SNV/indel VCF comparison. Most
current fixtures are protein-only: prepare an explicitly reviewed mapping to
public reference alleles/transcripts before a PCGR release; do not invent
coordinates, convert DNA rearrangements to measured RNA fusions, or manufacture
read counts. Allele-specific CNA segments can be supplied when present. Mark
non-expressible scenarios **not comparable**, with the reason, rather than
scoring them as missed calls. The simulated provider outage is an offline
robustness check, not a factual claim about a live database.

## PCGR

Use an owner-approved Apptainer image and matching assembly-specific reference
bundle under `SOMAWEAVE_REFERENCE_ROOT`; record image/bundle/VEP digests and the
complete command in a Slurm release. Read-only bind inputs/reference; write
outputs/cache/work externally. Pin the software/reference pair before download.
The [current installation guide](https://sigven.github.io/pcgr/articles/installation.html)
documents image2.3.2 with reference20260620 (checked 2026-10-17); these supersede
the old Phase0 snapshot's release examples, but are **not** an installed or
approved release here. The [input specification](https://sigven.github.io/pcgr/articles/input.html)
lists somatic VCF, allele-specific CNA, RNA-fusion and expression inputs. Its
[output specification](https://sigven.github.io/pcgr/articles/output.html)
provides machine-readable annotation outputs for comparison.

Compare exact allele retention, reported population/hotspot annotation,
variant/disease applicability and native clinical tiers, leaving unprovided
technical axes unassessed. PCGR's output is a comparator, not adjudicated truth.
Do not equate one tool's tier vocabulary to another without an explicit reviewed
crosswalk. No downstream report template changes belong in this stage.

## BioMCP and ToolUniverse

Pin command/skill versions and the explicit source/query plan. Send synthetic
variant/disease/treatment terms only, never patient IDs or private histories.
Use separate environments/containers if dependencies are needed, with environment
specification and HPC documentation updated before installation.
[BioMCP's variant guide](https://biomcp.org/user-guide/variant/) distinguishes
general annotation from the explicit OncoKB helper; do not count default output
as proof that every source was queried. [Its CIViC documentation](https://biomcp.org/sources/civic/)
describes section-specific retrieval. The [ToolUniverse oncology tool reference](https://github.com/mims-harvard/ToolUniverse/blob/main/plugin/skills/tooluniverse-precision-oncology/TOOLS_REFERENCE.md)
identifies individual database tools. Record actual tool calls and payloads,
not just a narrative response. No assumed source availability or invented
empty result is acceptable.

Separate deterministic retrieval coverage from any agent-generated synthesis.
For synthesis, an approved model/prompt/run protocol and repeat measurements
are needed; uncited claims and uncertainty inflation are separate error classes.
The [OncoKB licence FAQ](https://faq.oncokb.org/licensing) requires explicit
permission to benchmark existing AI/ML models and prohibits using its content
to train them. Confirm that permission before an OncoKB-based AI comparator;
without it omit that arm and report the limitation. Existing research API
access is not proof of AI benchmarking permission. No such entitlement has
been inferred or obtained by this work.

## Comparison deliverable

One external Markdown summary plus machine-readable comparison, bound to input,
code, image, reference and source versions. Report independently:

- Retrieval: per-source/tier status, records, query counts, exact/codon/class/
  gene scope, disease applicability and source-specific missingness.
- Interpretation: per-axis agreement with owner outcomes, native classifications
  alongside any explicit crosswalk, accepted/excluded classes and safety flags.
- Claims: resolvable source IDs/citations, evidence match to the claim, and
  unsupported assertions; a real citation alone does not establish relevance.
- Reproducibility: repeated pinned-cache comparisons, changed live-source
  versions separately, runtime, requests, peak resources and any service/model
  charges. No composite clinical confidence score.

Independent reviewed clinical cases would still be required for clinical
performance claims. This stage proceeds only after the owner approves the
design, input mappings, versions/resources and any required source entitlement.
