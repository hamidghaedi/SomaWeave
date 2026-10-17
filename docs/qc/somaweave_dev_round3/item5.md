# Item 5 — benchmark implementation and comparator design

Started after items1–4 completed; source base is population/hotspot release
`176579f`. Code belongs to the commit introducing
`scripts/run_benchmark.py`; its exact SHA is resolved as documented in this
directory's index and recorded in the external completion audit.

Files: `workflows/benchmark.py`, the QA runner, `tests/test_benchmark.py`,
nine synthetic case/evidence/expected triplets plus manifest/README in
`tests/benchmark/`, contract ownership row, benchmark/adjudication document,
comparator design, architecture/roadmap, this report and evaluation index.
The Phase0 PCGR release examples were also refreshed against the primary
installation guide; no image, reference or dependency was installed.

The runner delegates normalization, analytical assessment, reconciliation and
interpretation to existing services. Offline default replays clearly marked
synthetic evidence without network access. It never writes expectations or
inputs. It records input/package hashes, four separate axis comparisons,
analytical/review flags, excluded classes and treatment context. Unknown
alleles, path escapes, invalid/missing signoff and internal output paths fail.
There is no composite score or implicit negative interpretation of an outage.

Nine SPEC classes cover 11 findings, independently authored rather than copied
from development KQ inputs. Class9 covers CNV/fusion, not signatures. The FFPE
scenario uses explicit artefact review/template/strand concerns, not a fake
measured deamination assay. Most loci are protein-only, with no invented
genomic coordinate; PCGR therefore requires reviewed mapping before its stage.

All expected files are **pending_owner**, with reviewer/date blank. The
concrete proposed outcomes and rationales are in `docs/BENCHMARK.md` and the
per-scenario expected JSON. Owner signoff has been requested; it has not been
assumed. Consequently acceptance is **pending scientific adjudication**, not
complete. Draft agreement is a development result, not validated accuracy.

Commands and actual outcomes:

- `python scripts/run_benchmark.py --out <external-path>`: exit2, correctly
  refuses unsigned expectations before retrieval.
- `python scripts/run_benchmark.py --allow-draft --out <external-path>`:
  exit1, explicitly labelled offline draft; 11/11 agreement independently on
  each axis and all flag/exclusion checks pass. The narrative chronology
  check fails on "None days after" at month precision. The technical layer
  has bounded ranges; the relevance text does not render them. That defect
  is preserved as a failing expectation and remains open; the engine was not
  changed or the expectation weakened to obtain agreement.
- `python scripts/run_benchmark.py --live --allow-draft --out <external-path>`:
  exit2, draft mode cannot bypass live signoff.
- `python -m unittest discover -s tests`: exit0, 352 tests. New tests block
  socket connections, verify input immutability/reproducibility and mismatch
  reporting, gates, identity/path handling and mocked live dispatch.
- `python scripts/check_structure.py` and
  `python scripts/export_schemas.py --check`: exit0.
- CR scan finds no matches (expected exit1); `git diff --check`: exit0.

The initial narrower draft check exited0 before the missing-day wording was
noticed; the final stricter chronology expectation deliberately exits1.
Full commands, output/exit codes and the read-only draft comparison are under
`validation_round3/item5/` in the external runtime root. No benchmark live
queries or external comparators were run. Unit tests exercise live dispatch
only with temporary synthetic signoff and mocks; no signed fixture is committed.

Second-stage design is `docs/BENCHMARK_COMPARATORS_DESIGN.md`: pinned PCGR
Apptainer/reference pair, explicit source queries for BioMCP/ToolUniverse,
reviewed input mappings, independent axis/source/citation/reproducibility
metrics, and no automatic cross-tool tier equivalence. It is **design only**,
awaiting owner approval. No further implementation was authorized or performed.
