# SomaWeave as the deterministic evidence engine for the Djerba evidence appendix

Status: design for review, 2026-10-19. No implementation, no report authorization.
Counterpart documents in `somatic_pipeline_sm`: `docs/REPORTING_CONTRACT.md`,
`docs/AI_ASSISTED_DJERBA_EVIDENCE_REVIEW_DEVELOPMENT_PLAN.md` (design only),
`docs/schemas/djerba_ai_evidence_review_bundle.schema.json`, `AGENTS.md`.

## 1. Position

The sibling pipeline's reporting contract makes native OICR Djerba the only report
engine and prohibits analytical post-processing. Its development plan opens exactly
one slot: an **additive, visibly separate, human-reviewed evidence appendix** bound
to the final Djerba report, fed by a **deterministic source broker** and governed by
a closed JSON schema. SomaWeave is proposed as that broker *and* as the structured,
deterministic assessment the plan expected two LLM collectors and a judge to
produce. Nothing else changes: Djerba's findings stay authoritative and untouched;
SomaWeave never renders the report.

This is more conservative than the plan, not less: every statement in the appendix
is rule-derived and cites an evidence record with source, tier, status and
retrieval time; nothing is synthesized by a model.

## 2. Binding boundaries inherited from the sibling (restated, with SomaWeave's answer)

| Sibling boundary | SomaWeave answer |
|---|---|
| Native Djerba first; appendix starts from Djerba's final small-variant set | New ingest adapter from Djerba JSON (see 4.1); semantic check that SomaWeave's finding set equals Djerba's reportable set exactly |
| No SomaSieve analytical path | SomaWeave shares no code with SomaSieve; the PCGR asset reuse is read-only and outside this path |
| Additive and visibly separate | Appendix bundle is a separate file bound by hash to the Djerba JSON/HTML; no Djerba finding is added, removed, re-ordered or re-labelled |
| No silent semantic fallback | SomaWeave already records `unavailable` / `no_credentials` / `error` per source and tier; the projection turns any such status on a variant into a **hold**, distinct from `no_records` (valid zero) |
| No real run from development code | Feature branch in the sibling repo, full SHA, clean checkout, checksum-gated containers; SomaWeave pinned by commit and package hash (already recorded in every manifest) |
| Contract change before release | `AGENTS.md` amendment authorizing this one layer is the owner's act and precedes any Nextflow canary |
| Version-1 scope: small variants only | Same; CNAs, fusions, SVs, germline and biomarkers excluded |

## 3. What already fits

- **Sources**: CIViC (GraphQL), OncoKB (licensed token), ClinVar, Europe PMC, gnomAD,
  ClinicalTrials.gov via the ToolUniverse bridge — with payload cache holding exact
  response bytes, per-query status and timestamps, and `source_version` per record.
- **Trial-matching limits**: candidates never "eligible"; gene-level never presented
  as exact-variant; registry presence is not efficacy; level of condition match
  (diagnosis / OncoTree / lineage / basket) stamped on every record; listed only for
  oncogenic or likely-oncogenic findings. These are the plan's section 5.1 rules.
- **Four-axis assessment** with ClinGen/CGC/VICC criteria tags and AMP/ASCO/CAP tier
  and level, every claim cited, cross-cancer evidence labelled and capped at Tier III,
  OncoKB upstream annotations quoted and never re-derived.
- **Provenance**: run manifest binds commit, package hash, providers-config hash,
  OncoTree release, environment variable names (never values), input SHA-256.

## 4. What must be built (small, bounded)

### 4.1 Djerba-JSON ingest adapter — `src/somaweave/ingest/djerba.py`

Input: the Djerba report JSON (and its HTML for the binding hash). Output: `case.v2`
with one alteration per Djerba-reported small variant, carrying Djerba/OncoKB fields
as `annotations_as_reported` (quoted only), the Djerba-assigned OncoTree code as the
diagnosis, specimen purity/ploidy as Djerba reports them, and `input_provenance`
with both source hashes. Rules: no variant filtering, no re-annotation, variant
identity normalized to GRCh38 chrom:pos:ref:alt with the Djerba variant key kept.
Clinical history and treatment chronology are not in Djerba JSON; they come from the
existing lab/clinical inputs through `build-case` when available, else the relevance
axis reports "treatment history not provided" (already supported).

### 4.2 Bundle projection — `src/somaweave/reporting/djerba_bundle.py`

Maps a SomaWeave run (report JSON + evidence sets) onto
`djerba_ai_evidence_review_bundle.schema.json`:

| Bundle field group | Source in SomaWeave |
|---|---|
| `source_report` (hashes, Djerba identity) | ingest provenance |
| `case_context` (OncoTree code/version/approval) | normalized disease context + OncoTree release recorded in manifest |
| `variants[].identity` | alteration (GRCh38 key, HGVS, transcript, Djerba variant key) |
| `source_registry`, snapshots, locators | provider payload cache references (`raw_reference`), `source_url`, `retrieved_at`, `source_version` |
| `variants[].claims` with evidence labels | established claims → `DIRECT` (curated structured evidence paraphrased with its citation); literature records → `UNAVAILABLE`-safe metadata unless an excerpt is verified; conflicts → `UNRESOLVABLE`; missing sources → `UNAVAILABLE` with limitation. `VERBATIM` only where a bounded excerpt (≤25 words) is taken from cached bytes at a locator — initially CIViC evidence statements only. `INFERRED` is not emitted in version 1 (no synthesis layer). |
| `variants[].trials` | trial records: NCT, status, phases, conditions, condition-match level → `POTENTIALLY_RELEVANT` only; eligibility `NOT_ASSESSED`; freshness window from `retrieved_at` |
| collector/judge slots | **Contract change needed**: the schema requires two collector roles with different model IDs and a judge. Proposal: one deterministic role `somaweave:<version>:<commit>` and an explicit `collector_mode: deterministic` enum value; the semantic validator's rule 3 (two distinct model IDs) is replaced by "deterministic engine identity recorded". This is a schema amendment for the sibling owner to approve. |
| `review` | empty human dispositions; the review UI (plan WP5) remains the sibling's |

### 4.3 Hold semantics — in the projection

A variant whose evidence set has any `unavailable` / `error` / `no_credentials`
status on a tier the planner emitted → `bundle_state: hold` with the exact source
message; a clean `no_records` → explicit zero-evidence claim with label
`UNAVAILABLE` and limitation "queried, no records". A finding-set mismatch with
Djerba → hold. OncoTree code unknown to the recorded release → hold.

### 4.4 Validation

- Contract tests against the closed schema with synthetic bundles (additive-only
  check: no Djerba finding altered).
- Semantic validator rules 1, 2, 4–11, 15, 16 implementable deterministically on
  the SomaWeave side; rules 12–14 are human-review rules and stay in the UI stage.
- Replay on the three private cases: Djerba JSON → `case.v2` → run → bundle;
  assert identity of four-axis labels with the `build-case` path for the same
  variants (differences are ingest defects, not engine changes).
- Gate order: unit/contract tests → structure/schema checks → private replay →
  owner reads the three bundles → `AGENTS.md` amendment → Nextflow canary on a
  feature branch at a full SHA.

## 5. What this is not

Not a report renderer; not an LLM narrative or collector; not a clinical sign-out
or eligibility decision; not a change to any Djerba output. Trial records are
candidates, never recommendations. All SomaWeave output in the appendix remains
labelled "research use; human validation required".

## 6. Open decisions for the owners

1. Amend the sibling `AGENTS.md` to authorize the additive appendix (sibling owner).
2. Accept the deterministic-engine amendment to the bundle schema (collector/judge
   slots) or keep the LLM collectors and treat SomaWeave strictly as the broker
   feeding them (then 4.2's claim mapping is dropped and only `source_registry`,
   snapshots and trials are projected).
3. Precondition on our side: the owner has reviewed the three real-case digests and
   the disagreement list is closed, and the synthetic benchmark expectations are
   signed. Integration work should not start before that.
4. Placement of this document in the sibling repository (`docs/`) is done by the
   local agent under the owner's authorization; this copy in SomaWeave is the
   reference.
