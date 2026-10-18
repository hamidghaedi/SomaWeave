# Synthetic PCGR comparison

All11 findings appear below. Expected labels are **pending_owner**, copied
verbatim from frozen expected JSON, not adjudicated truth. PCGR native outputs
are a separate comparator. Neither the draft replay agreement nor a PCGR
classification establishes accuracy. No interpretation rule was changed.
Eight exported alleles were retained; scenario08 is partial and scenario09
was not run. Missing comparator inputs are not negative annotations.

The PCGR analytical column deliberately reads **not assessed by PCGR**;
PCGR has no independent SomaWeave-style relevance axis. Its AMP_ASCO_CAP
`ACTIONABILITY_TIER` values are shown as native numeric strings. No tier
crosswalk is proposed: disease matching, evidence levels, biological/diagnostic
context and available inputs differ. Identical-looking labels are not proof
of shared criteria or clinical equivalence.

| Scenario / allele | Expected analytical | PCGR analytical | Expected oncogenicity | PCGR native oncogenicity / criteria | Expected tier | PCGR native ACTIONABILITY_TIER | Expected relevance | PCGR relevance | Retained / native filter | Discrepancy classification and interpretation |
|---|---|---|---|---|---|---|---|---|---|---|
| 01_driver / A1: BRAF p.Val600Glu | high | not assessed by PCGR | likely_oncogenic | Oncogenic / `ONCG_OS1;ONCG_OS3;ONCG_OP1` | I | 1 | high | no separate axis | yes / PASS | **knowledge-base difference** — PCGR supplies OS3 hotspot and OP1 computational evidence absent from the single synthetic oncogenic record; its weighted class differs. Native tiers are not crosswalked. |
| 02_rare_tumour / A1: KIT p.Trp557_Lys558del | high | not assessed by PCGR | likely_oncogenic | Oncogenic / `ONCG_OS1;ONCG_OM2;ONCG_OM4;ONCG_OP4` | II | 1 | high | no separate axis | yes / PASS | **knowledge-base difference** — PCGR uses OS1/OM2/OM4/OP4 rather than the limited synthetic records. Tissue25 is Soft Tissue, not exact GIST disease matching. |
| 03_recurrence / A1: TERT c.-124C>T | high | not assessed by PCGR | likely_oncogenic | Likely_Oncogenic / `ONCG_OS1` | II | 1 | high | no separate axis | yes / PASS | **fixture artefact** — The synthetic prognostic record/level differs from PCGR bundled biomarkers and broad CNS site8; native tiers differ in vocabulary and inputs. Literal promoter-reference convention needs owner review. |
| 04_resistance_timing / A1: EGFR p.Thr790Met | high | not assessed by PCGR | likely_oncogenic | Oncogenic / `ONCG_OS1;ONCG_OS3;ONCG_OP1` | I | 1 | high | no separate axis | yes / PASS | **knowledge-base difference; fixture artefact** — PCGR adds hotspot/computational evidence; synthetic treatment chronology and resistance timing are not an input to this PCGR run. No temporal reasoning agreement is claimed. |
| 05_vaf_cn / A1: BRAF p.Val600Glu | high | not assessed by PCGR | uncertain_significance | Oncogenic / `ONCG_OS1;ONCG_OS3;ONCG_OP1` | IV | 1 | none | no separate axis | yes / PASS | **knowledge-base difference; fixture artefact** — PCGR adds hotspot/computational evidence. Alternative purity fits and locus CN are not quantitative native segment input; no PCGR purity/CN result was manufactured. |
| 06_ffpe_artifact / A1: BRAF p.Val600Glu | unreliable | not assessed by PCGR | likely_oncogenic | Oncogenic / `ONCG_OS1;ONCG_OS3;ONCG_OP1` | IV | 1 | none | no separate axis | yes / PASS | **knowledge-base difference; fixture artefact** — PCGR adds hotspot/computational evidence. It does not consume template/strand/manual artifact observations: biological oncogenicity does not validate this measured allele. |
| 07_discordant_pathology / A1: KRAS p.Gly12Cys | high | not assessed by PCGR | likely_oncogenic | Oncogenic / `ONCG_OS1;ONCG_OS3;ONCG_OP1;ONCG_OP4` | III | 1 | low | no separate axis | yes / PASS | **knowledge-base difference; engine difference; fixture artefact** — PCGR has broader bundled biomarkers and a pancreas tissue assignment; the synthetic evidence is cross-cancer and SomaWeave retains the recorded diagnosis/hypothesis gate. Native tiers alone cannot isolate rule from source effects. |
| 08_insufficient_conflicting / A1: APC p.Arg1450Ter | high | not assessed by PCGR | uncertain_significance | Oncogenic / `ONCG_OVS1;ONCG_OS1;ONCG_OP4` | IV | 2 | none | no separate axis | yes / PASS | **fixture artefact** — PCGR cannot see the deliberately opposing synthetic assertions or simulated outage; it uses OVS1/OS1/OP4 for the exported APC stop. CTNNA1 has a MANE reference-residue mismatch and is not compared. |
| 08_insufficient_conflicting / A2: CTNNA1 p.Arg100Gly | high | not assessed by PCGR | not_assessed | not comparable | not_assessed | not comparable | not_assessable | no separate axis | not exported; not a negative | **fixture artefact** — PCGR cannot see the deliberately opposing synthetic assertions or simulated outage; it uses OVS1/OS1/OP4 for the exported APC stop. CTNNA1 has a MANE reference-residue mismatch and is not compared. |
| 09_genome_findings / A1: ERBB2 amplification | not_assessable | not assessed by PCGR | uncertain_significance | not comparable | I | not comparable | high | no separate axis | not exported; not a negative | **fixture artefact** — Only qualitative CNA/fusion labels are supplied; required native segment/breakpoint inputs are absent. Not comparable, not a PCGR miss. |
| 09_genome_findings / A2: RET fusion | not_assessable | not assessed by PCGR | uncertain_significance | not comparable | I | not comparable | high | no separate axis | not exported; not a negative | **fixture artefact** — Only qualitative CNA/fusion labels are supplied; required native segment/breakpoint inputs are absent. Not comparable, not a PCGR miss. |

Discrepancy categories are explanatory review attributions, not an accuracy
score or proof of a sole cause. Each row names source/input differences first;
engine differences are reported where disease/criteria handling also differs.
No possible SomaWeave defect was established from this comparison. The known
fixture inconsistencies above require owner decisions, not engine tuning.

## Proposed oncogenicity crosswalk — pending_owner

| PCGR VICC native class | Proposed SomaWeave class | Approval |
|---|---|---|
| Oncogenic | oncogenic | pending_owner |
| Likely_Oncogenic | likely_oncogenic | pending_owner |
| VUS | uncertain_significance | pending_owner |
| Likely_Benign | likely_benign | pending_owner |
| Benign | benign | pending_owner |
| No output / unexportable | no equivalence to not_assessed or benign | pending_owner |

Both systems describe ClinGen/CGC/VICC-derived oncogenicity concepts, but the
rule implementations and evidence inputs differ. This table is a naming
proposal only; no classifier, benchmark expectation or report consumer uses
it. In particular PCGR uses weighted criteria and computational/population
inputs, whereas SomaWeave requires accepted somatic assertions for benign
classes and keeps population cautions uncertain. Native numeric AMP tiers
remain untranslated; cross-cancer and tissue matching cannot be reconciled by
renaming a tier.

## Native enrichment audit

The external parsed JSON preserves every retained row's consequence,
hotspot assertion, gnomADe_AF/gnomADg_AF, ClinVar class, native VICC class and
criteria, native AMP tier/framework, HGVS/MANE and exact anchored allele key.
No ClinVar germline classification is treated as somatic oncogenic evidence.
Multiple transcript rows remain separate. Source dots remain dots, not zero.
Native VEP HGVS matches all8 exported descriptions. The TERT literal offset
and legacy GBM code are explicitly reviewable scope issues, not resolved by
successful annotation. See `pcgr_release.md` for exact identities and commands.

For an omitted allele the parser reports unknown native exclusion reason
unless a FILTER supplies one. Here all8 exported alleles are retained with
native PASS; no unexplained drop or representation change was observed.

## Remaining owner decisions

- Sign/change benchmark expected labels and rationale through the documented
  owner procedure. The agent did not sign anything.
- Review the genomic map, clarify CTNNA1 reference/transcript and the intended
  promoter coordinate convention; three rows remain unmapped.
- Supply supported native CNA/fusion inputs for scenario09 or accept its
  not-comparable status. Do not count a fabricated empty run toward nine.
- Approve or revise the proposed oncogenicity naming crosswalk. No tier
  crosswalk or clinical equivalence is asserted.
