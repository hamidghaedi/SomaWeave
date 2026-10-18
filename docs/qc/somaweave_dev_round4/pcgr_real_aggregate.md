# Private-case PCGR comparison — aggregate results only

The conditional input gate passed: all115 existing small variants already had
GRCh38 chromosome/position/REF/ALT in the private case-v2 inputs. No coordinates
were back-filled, case JSON changed or alleles selected out. Three final PCGR
runs completed with native and adapter exit0, final annotation tables and
source-version manifests. The release/options are those in `pcgr_release.md`.
Complete commands, scheduler states/wall times, source hashes, input ledgers,
per-allele comparison and manifests remain in the private runtime workspace
under `comparators/pcgr/real/`; no real-case payload enters Git.

SomaWeave's existing final population-enriched replay supplies its unchanged
four-axis results. No new live retrieval, interpretation tuning, clinical
release or change of an upstream reviewed decision occurred. PCGR retention is
annotation retention, not technical clearance or inclusion in a patient report.

## Retention and native oncogenicity

| Case | Input alleles | PCGR retained | PCGR native VICC class distribution | SomaWeave oncogenicity distribution |
|---|---:|---:|---|---|
| case-A | 35 | 35 | Benign11; Likely_Benign8; VUS15; Likely_Oncogenic1 | uncertain_significance34; likely_oncogenic1 |
| case-B | 52 | 52 | Benign9; Likely_Benign12; VUS29; Oncogenic2 | uncertain_significance50; oncogenic1; likely_oncogenic1 |
| case-C | 28 | 28 | Benign11; Likely_Benign4; VUS13 | uncertain_significance28 |

Counts refer to exact input alleles, not transcript rows. All115 were retained
with matched anchored keys; no unexplained allele drop or representation change
was observed. This does not validate somatic origin or oncogenicity.

## Native actionability vocabularies

| Case | PCGR ACTIONABILITY_TIER (framework AMP_ASCO_CAP; numeric strings) | SomaWeave actionability tier |
|---|---|---|
| case-A | 2:1; 3:1; 5:21; 6:12 | III:2; IV:33 |
| case-B | 2:1; 3:1; 5:31; 6:19 | III:2; IV:50 |
| case-C | 3:1; 5:21; 6:6 | IV:28 |

No tier crosswalk or tier agreement score is proposed: disease-matching and
level/context inputs differ. Native values remain unchanged. PCGR has no
independent counterpart to SomaWeave's relevance axis in this comparison.

## Discrepancy review

These are exploratory per-allele oncogenicity discrepancies under the
**pending-owner naming crosswalk**, not benchmark accuracy. A primary category
is assigned once per differing allele; coincident source/rule effects remain
possible. Unmatched analytical/relevance axes and untranslated tiers are not
counted as disagreements.

| Case | Fixture artefact | Knowledge-base difference | Engine difference | Possible SomaWeave defect | Total |
|---|---:|---:|---:|---:|---:|
| case-A | 0 | 6 | 13 | 0 | 19 |
| case-B | 0 | 7 | 15 | 0 | 22 |
| case-C | 0 | 1 | 14 | 0 | 15 |

Attribution is based on the actual source criteria, not chosen to create
agreement. Shared population-frequency criteria produce many engine
differences: PCGR assigns Benign/Likely_Benign, whereas SomaWeave deliberately
keeps a population caution uncertain until accepted somatic benign assertions
exist. One shared loss-of-function-mechanism context reaches PCGR Oncogenic
with its weighted criteria but remains SomaWeave likely_oncogenic under the
class-level-support gate. Other differences use PCGR computational/consequence
benign evidence absent from SomaWeave's accepted exact somatic evidence pool;
these are primarily classified as knowledge-base differences. This is not
proof that only one factor explains each difference, or that PCGR is correct.
No engine change is justified or implemented merely to remove these differences.

## Analytical and missing-input limits

PCGR analytical axis: **not assessed by PCGR**, for every allele. Existing
SomaWeave analytical results remain:

| Case | high | moderate | low | unreliable |
|---|---:|---:|---:|---:|
| case-A | 11 | 1 | 4 | 19 |
| case-B | 25 | 0 | 11 | 16 |
| case-C | 2 | 0 | 4 | 22 |

PCGR retained the technically unreliable alleles too; this is expected for an
annotation comparator that did not consume template/visual evidence. It does
not overturn any BAM-review hold. No purity alternative was selected, and
locus-level copy-number states were not fabricated into native segment files.

| Case | Input alleles lacking a computable raw normal AF | Native vaf_control_detected |
|---|---:|---:|
| case-A | 4 | 0 |
| case-B | 3 | 0 |
| case-C | 3 | 0 |

Available normal AF/DP tags were supplied; absent counts remained missing.
PCGR's native warnings/manifest mark control AF unavailable for the whole file
when some records lack it. No missing value was replaced with zero, and no
additional control-AF threshold was requested. This native consumer limitation
further prevents treating its retention as a matched-normal technical review.

Remaining: owner review of the naming crosswalk and discrepancy attributions;
independent adjudication would be needed for accuracy claims. No specific
SomaWeave defect was established by these aggregate differences. All original
inputs, raw native assertions and case-specific evidence remain private.
