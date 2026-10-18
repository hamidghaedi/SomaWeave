# Round4 handoff — 2026-10-18 work order

Baseline: `6f2cd69`. Interpretation rules, benchmark case/evidence/expected
fixtures and owner-signoff fields are frozen for this round. Real-case data
remain in the private evaluation workspace; Git uses only neutral case labels
and aggregate results.

| Item | Commit | Status |
|---|---|---|
| A | `421eae3` | [Review sheet](benchmark_review_sheet.md)/procedure and edge audit complete; owner signatures pending |
| B | `275cc96` | [Release](pcgr_release.md) and [comparison](pcgr_comparison.md): implementation and all8 submitted runs complete; seven complete scenarios, one partial; full acceptance blocked by unmapped inputs |
| C | Commit introducing `pcgr_real_aggregate.md` (resolve with `git log -1 --format=%H -- docs/qc/somaweave_dev_round4/pcgr_real_aggregate.md`) | [Aggregate comparison](pcgr_real_aggregate.md): coordinate condition passed for all115 alleles; three private runs completed; all115 retained; detailed results remain external |

Item A: 11 finding rows, verbatim expected field values, supplied evidence IDs,
rule names and one advisory assessment per row. All owner-decision cells are
blank. The staged reference does not directly resolve the legacy `GBM` code;
the distinction from the built-in benchmark index is recorded without changing
the fixture. No mixed-precision/missing-date or conditions/compound-profile
scenarios were added.

Validation for A: 353 unit tests and both mandatory structure/schema checks
pass. Existing benchmark files retain their baseline SHA-256 values; no
expected JSON or interpretation rule was modified. Detailed check output is
under the external `validation_round4/` directory.

Outstanding owner decisions: benchmark signatures; genomic-map review and any
ambiguous mappings; proposed oncogenicity crosswalk approval. Scenario09 has
qualitative amplification/fusion labels without nucleotide/segment/breakpoint
inputs, so its PCGR input route requires clarification rather than invented data.

No new environment, dependency, reference download or sibling-project change
is authorized or performed. BioMCP/ToolUniverse and LLM comparison remain deferred.

Item B adds maintained small-allele export/native parsing, offline MANE mapping
helpers, a portable CPU Slurm entry and20 offline comparator tests. Final suite
at this increment: **373 tests**, plus passing structure/schema gates. All
original benchmark case/evidence/expected files and interpretation-engine files
remain unchanged. No expectation or genomic-map review was signed.

The genomic map has11 rows: eight reference-verified alleles and three explicitly
unmapped rows. Scenario08 CTNNA1 has a MANE reference-residue mismatch;
scenario09 lacks exportable native CNA/fusion inputs. These require owner
clarification and prevent claiming nine fully comparable successful scenarios.
All detailed commands, exit codes, job records and payloads are external under
`validation_round4/` and `comparators/pcgr/` in the private workspace.

Final validation:373 offline unit tests, structure check and schema-export
check all pass before the C commit. LF scan finds no carriage returns under
src/tests/docs. Detailed per-item command/exit records and full commit SHAs are
in the external `validation_round4/completion.json`. Existing benchmark
expectations remain pending_owner; default/live scoring remains gated.
