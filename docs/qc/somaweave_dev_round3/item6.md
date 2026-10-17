# Item 6 — conflict and source-policy hygiene

Implemented independently of the population-provider work, from main after
ingestion commit `3c20149`. Files: `evidence/reconcile.py`,
`tests/test_conflicts_compatible.py`, `docs/PHASE0_ASSESSMENT.md`, this report.

Conflict comparison now requires the same gene, category and drug set, and
either identical source descriptions or compatible single-protein profiles
of the same class/codon. Three-letter/HGVS spelling differences are accepted;
compound profiles, distinct codons/classes/genes/drugs remain separate.
Different source diseases retain `same_disease=False`. The text explicitly
does not assume equivalent biological effects between substitutions.

CIViC's primary API documentation confirms anonymous reads and the default
three requests/s limit; keys serve authenticated curation or rate-limit
exemption. Its FAQ confirms CC0 content and MIT application code. ClinVar's
attribution/use policy and NCBI copyright exceptions replace the unsupported
blanket public-domain statement; E-utilities rate limits were rechecked.
Europe PMC's indexed official help text supports article-specific copyright;
the current copyright/REST pages returned HTTP403. Full current service terms
are explicitly recorded as **could not verify on 2026-10-17**. Access success
is kept distinct from redistribution rights. Sources are linked in the
assessment. No credentials, dependencies or reference data were added.

Validation commands: `python -m unittest discover -s tests`,
`python scripts/check_structure.py`, `python scripts/export_schemas.py --check`,
`grep -rlI $'\r' src tests docs`, `git diff --check`. A separate scratch
checkout of the committed base plus only these item6 files also passed all
three required checks (334 tests), establishing independence from the pending
item4 changes. All check exit codes are 0; the CR scan exits 1 because it finds
no matches, as expected. `.gitattributes` retains `text=auto eol=lf`.
Full worktree suite with the pending population changes passes 345 tests.
Validation evidence stays in `validation_round3/item6/` under the external
runtime root. No change to the four-axis classification rules is included in
this commit. Remaining gap: current Europe PMC full terms could not be fetched.
