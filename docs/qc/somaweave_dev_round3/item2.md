# Item 2 — coherent case v2

Implemented after compute validation commit `4c53bc2`.

Files: domain case/alteration/exports/I/O, region applicability, technical VAF/
strand/quality modules, interpretation's verified-region scope, JSON/Markdown
renderers, synthetic example, case.v2 schema, synthetic fixtures/tests,
architecture, roadmap, contract and decision0001.

The new case provenance dictionary is the chosen owner of input paths and
hashes for ingestion. No real case or reference file is committed.

Behavior: all new fields are optional. Explicit case.v1 files still load;
the original example and frozen v1 schema have a separate regression. Exon
match/mismatch/unknown, ranges and compound requirements are tested. LOH state
is explicit and quoted even without locus CN; new `not_called` takes precedence
over a deprecated Boolean without deleting it. Every competing purity fit is
enumerated in source order with index/disposition, and none is selected. Typed
visual review on either role quotes the upstream code; exact artifact/artefact
retains the existing unreliable rule. Non-exclusive strand p-values are nominal
context only. Treatment notes/modality and storage remain separate concepts.

Commands: existing Python `-m unittest discover -s tests`,
`scripts/check_structure.py`, `scripts/export_schemas.py --check`, and
`-m somaweave validate-case examples/synthetic_case.json`. Schema export is run
after domain edits; all three required gates and example validation must pass
before commit. Final results: 325 tests pass; structure, schema check and example validation each exit 0. LF scan and diff whitespace checks pass. No dependency or environment was installed.

The original example expectations changed only where the owner-requested v2
example adds a recorded exon, alternative fit and visual quotes. The new
alternative-fit compatible count is hand-checked (purity0.22, locus CN3): three
multiplicity/CCF scenarios lie within the original observed interval. Existing
four-axis/missing-evidence/no-LOH-inference checks remain intact.

Remaining limitations: region numbering uses the supplied transcript/source,
not inferred cross-transcript equivalence. Alternate fits reuse the supplied
locus CN, not a recomputed CNA model. Missing measurements and outcomes remain
missing. Maintained ingestion and new population/hotspot retrieval follow.
