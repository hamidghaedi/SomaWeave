# Round4 handoff — 2026-10-18 work order

Baseline: `6f2cd69`. Interpretation rules, benchmark case/evidence/expected
fixtures and owner-signoff fields are frozen for this round. Real-case data
remain in the private evaluation workspace; Git uses only neutral case labels
and aggregate results.

| Item | Commit | Status |
|---|---|---|
| A | Commit introducing `benchmark_review_sheet.md` (resolve with `git log -1 --format=%H -- docs/qc/somaweave_dev_round4/benchmark_review_sheet.md`) | Review sheet/procedure and edge audit complete; owner signatures remain pending |
| B | Pending | Existing PCGR release under verification; no comparator result claimed yet |
| C | Pending conditional coordinate check | No result claimed |

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
