# T2 follow-up — condition-hierarchy trial retrieval

Owner-authorized rerun at source **8d7a59b**, using a clean detached worktree
and unchanged case-v2 inputs. The private runtime root **R7** is
`/global/scratch/hpc6049/somaweave_dev/evaluation/tooluniverse/T2_eval7/`;
the source worktree is its sibling `source_8d7a59b/`. Every run manifest binds
the full8d7a59b commit and the input SHA-256 already recorded by eval-5/eval-6.
Results are `<private-case>-eval-7-trials`. No case metadata, hypothesis,
interpreted variant or source classification was changed for the evaluation.

The owner's new condition hierarchy was exercised as released. No engine,
provider or report code was modified, and no package/environment change was
made. The ToolUniverse provider cache started empty; the other providers reused
a snapshot of the eval-6 non-trial cache. The bridge retains its configured
clean environment and existing isolated ToolUniverse1.5.7 interpreter.

## Execution and reproducibility

The same released Slurm template and existing SomaWeave environment were used:

```bash
export SOMAWEAVE_TOOLUNIVERSE_PYTHON=$HOME/.conda/envs/tooluniverse/bin/python
export SOMAWEAVE_RESULTS_ROOT=R7/results
export SOMAWEAVE_CACHE_ROOT=R7/cache
export SOMAWEAVE_REFERENCE_ROOT=/global/scratch/hpc6049/somaweave_dev/reference
export PYTHONPATH=E/source_8d7a59b/src
export SOMAWEAVE_INTERPRET_ARGS='--run-id <private-case>-eval-7-trials'
sbatch --account=def-hpcg6049_cpu --time=00:45:00 --mem=2G --cpus-per-task=1 \
  --export=ALL --chdir=R7 --output=R7/<neutral-label>-%j.out \
  E/source_8d7a59b/hpc/slurm/interpret_case.sbatch <unchanged-case-v2.json>
```

E is the parent evaluation directory from the main handoff; R7 and E above
are abbreviations for the literal paths, not literal submitted arguments.
Exact argv/environment overrides and sbatch exit codes are in
R7/submissions.json. Inputs/source hashes are in R7/inputs.json; native payloads,
source queries, generated research reports and per-finding comparisons remain
external under R7. The previous evaluation's completion record is preserved.

| Case | Job | Node | State / exit | Wall time |
|---|---|---|---|---|
| case-A | 12364073 | frnt152 | COMPLETED / 0:0 | 00:02:10 |
| case-B | 12364074 | frnt152 | COMPLETED / 0:0 | 00:04:38 |
| case-C | 12364075 | frnt152 | COMPLETED / 0:0 | 00:01:45 |

## Retrieval and four-axis identity

| Case | Findings / gene-tier provider queries | ok | no_records | unavailable / error / other | Native successful request entries | Trial records | Unique NCT IDs within case | Findings with trials |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| case-A | 35 | 4 | 31 | 0 | 70 | 36 | 35 | 4 |
| case-B | 52 | 3 | 49 | 0 | 156 | 18 | 17 | 3 |
| case-C | 28 | 2 | 26 | 0 | 56 | 2 | 1 | 2 |

The115 provider queries contain282 successful native request entries across
condition levels, including cache reuse; this is not282 distinct HTTP calls.
No condition-level unavailability was noted. There are56 finding–trial records,
53 case-specific NCT entries after de-duplication across findings, and52 distinct
NCT IDs across the entire evaluation. Repeated NCTs across different findings
are counted explicitly, not treated as independent supporting evidence.

**All four axes are identical for all115 findings compared with eval-5:
460 labels, zero differences.** The same identity holds against eval-6.
All56 trial records are gene-tier hypotheses and absent from the accepted
evidence pools. Positive registry retrieval did not change analytical
reliability, oncogenicity, actionability or relevance. No defect was patched
to produce agreement.

Every retained trial has `source_native_rating=basket: Solid Tumor`.
The narrower levels returned no retained records. Case-A has70 outgoing
entries:35 recorded-diagnosis conditions and35 basket conditions. No unconfirmed
histology hypothesis appears in its outgoing condition arguments. Case-B uses
the recorded diagnosis, confirmed OncoTree name and basket; case-C uses its
recorded diagnosis and basket. These statements were checked against the
recorded multi-line native_request, not inferred from the final trial labels.
Planner hypothesis metadata stays separate. One returned basket trial lists
the unconfirmed hypothesis; that does not make it a confirmed-diagnosis match.

Case-A has one finding capped at25 returned records. All counts therefore
describe the released adapter's retained first-page/capped results, not an
exhaustive registry or eligibility search.

## Registered-condition plausibility review

Every returned record was reviewed against the **unchanged recorded diagnosis**
and defensible parents. Search level was not used as the decision:

- **Plausible:** the registry condition list explicitly names the recorded
  diagnosis or a non-generic parent. This establishes disease-family
  plausibility only; required biomarkers, subtype, age, treatment history,
  recruitment location and eligibility were not evaluated.
- **Disease-mismatch:** the list supplies specific disease labels unsupported
  by the recorded diagnosis/parents, without an applicable generic umbrella.
  This means no supported recorded-diagnosis match, not proven ineligibility
  or a new diagnosis. Unresolved primary/histology was not silently resolved.
- **Uninformative:** only a broad cancer/solid-tumour umbrella supports the
  case, even when other unrelated specific cancers are also listed, or the
  condition field contains non-diagnostic text. Mutation-qualified baskets
  retain an unresolved-requirement note; no molecular eligibility is inferred.

This review is a separate recorded QC assessment, not an interpretation-engine
rule or modification to patient results. Controlled categories and reasons for
all48 distinct case/condition-list combinations are in
R7/condition_reviews.json. Each finding–trial record inherits its reviewed
condition-list decision; full conditions, NCT IDs, source/raw references and
reasons remain in R7/plausibility_review.json and plausibility_review.tsv.

| Case | Plausible records | Disease-mismatch records | Uninformative records | Total |
|---|---:|---:|---:|---:|
| case-A | 0 | 4 | 32 | 36 |
| case-B | 1 | 2 | 15 | 18 |
| case-C | 0 | 0 | 2 | 2 |
| Total | 1 | 6 | 49 | 56 |

De-duplicated **within each case**:

| Case | Plausible unique trials | Disease-mismatch unique trials | Uninformative unique trials |
|---|---:|---:|---:|
| case-A | 0 | 4 | 31 |
| case-B | 1 | 2 | 14 |
| case-C | 0 | 0 | 1 |

Of the49 uninformative finding–trial records,45 have broad-basket-only support
(including mixed lists), two have mutation-qualified basket support, one
contains a regimen description rather than a diagnosis, and one only describes
disease extent/resectability. These are not49 literal lists containing only
the words Solid Tumor. This distinction prevents generic and malformed text
from being mistaken for verified disease matching.

## Presentation findings and remaining limits

The new report identifies the retrieval level, which helps distinguish basket
discovery from a diagnosis-specific result. A basket result can still name a
relevant parent in its registered condition list: the single plausible record
here does so. Conversely six records have only unsupported specific disease
labels despite being retrieved by the broad basket search.

The blanket basket limitation that registered conditions do not name the
diagnosis can obscure a relevant named parent. Suggested wording, **not
implemented**: “Retrieved through a broad basket condition. Review the
registered conditions and eligibility; retrieval level alone does not establish
or exclude applicability to this diagnosis.” A narrower search with no results
is not evidence against a parent match found through a basket query.

Trial availability, condition-list plausibility and eligibility remain separate.
The assessment cannot establish sensitivity/specificity of registry matching,
exhaustiveness beyond the configured cap, variant-specific eligibility or
treatment benefit. No report or engine rule was changed. The bare SDK MCP
startup issue from the original evaluation was not retested in this T2-only run.

Validation before the documentation commit:394 offline unit tests pass with the
expected one MCP-registration skip; structure and schema-export checks exit0.
Per-command logs/exit codes and the full documentation commit are bound in the
external R7/completion.json, without embedding a commit's own hash here.
