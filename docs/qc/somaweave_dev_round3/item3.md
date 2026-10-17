# Item 3 — maintained ingestion

Implemented after schema commit `59d0fae`. Added `ingest` to the ownership
table and structure allow-list, maintained format/clinical/build modules,
`build-case` CLI dispatch, synthetic fixtures/tests and ingestion documentation.
The chosen provenance interface is `Case.provenance`, added in item 2.

Commands: `somaweave build-case --manifest <explicit manifest>`, followed by
`validate-case` and sequential `interpret-case --run-id <case>-eval-5` for all
three cases. All build/validation/interpretation exit codes are 0. The five-row,
three-segment, two-MAF-record synthetic fixtures exercise missing rows without
dropping them, ambiguous joins/count disagreement, QC arrays, XLSX and batch CLI.

Runtime root: `/global/scratch/hpc6049/somaweave_dev/`.
Inputs: `cases_v2/{KQ0296,KQ0265,KQ0283}.json`.
Outputs: `results/<case>-eval-5/`.
Build manifest, source-context lineage, exact commands/exit codes, input checks,
full field diff and per-allele axis comparison: `validation_round3/item3/`.
Patient data and results are never committed. Clinical overlays contain only
previously reviewed diagnostic names/hypotheses, not reused genomic evidence.

All 115 alleles and original caller REF/ALT/depth values match the hand-built
inputs. Genomic keys, transcripts, cDNA/protein HGVS and consequences match;
new null `position.end` defaults are not coordinate changes. The 599/910/495
field diffs against the expanded hand-built cases are explicitly preserved:
v2 metadata, typed exon/fit/LOH/visual structures, source provenance, notes,
source spelling for tissue/storage and clearer source-category precedence.
No caller count or clinical treatment response was changed or invented.

Each case now retains all seven native alternative fits without choosing one.
Exon numbering is supplied where the MAF has a structured value. Dates remain
month precision. Missing local mismatch statistics, raw read strands, review
dates/roles and explicit LOH calls remain missing or explicitly uncalled, as
documented in the ingestion contract.

| Case | Alleles | Analytical changes vs eval-4 | Oncogenicity / tier / relevance changes |
|---|---:|---:|---|
| KQ0296 | 35 | 12 | 0 / 0 / 0 |
| KQ0265 | 52 | 25 | 0 / 0 / 0 |
| KQ0283 | 28 | 3 | 0 / 0 / 0 |

Eval-4 actually used the original legacy inputs, not the expanded eval-3
inputs. The 40 analytical changes therefore reflect the added measured
quality/template fields and corrected QC arrays. No biological/treatment
category changed. Native reviewed decisions remain independently quoted.

The interpretation implementation is the released item-2 code; manifests name
that interpretation revision. The ingestion source hashes in each input bind
the exact builder used before this ingestion commit. Final pre-commit results: 331 tests pass; structure and schema checks exit 0;
LF and whitespace checks pass. No
environment/dependency was installed. General non-WGS pipeline conversion and
unverified cross-transcript exon equivalence remain outside this adapter's scope.
