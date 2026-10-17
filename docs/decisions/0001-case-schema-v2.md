# Case schema v2

Status: accepted implementation of the owner-directed schema revision, 2026-10-17.

## Reason

The evaluations could not structure exon membership, multiple purity models,
explicit uncalled LOH, paired visual review, strand-count dependence, treatment
modality or storage. Notes alone prevent deterministic use of those facts.

## Interface

`Case.schema_version` defaults to `case.v2` and accepts explicit `case.v1`.
New fields are optional. The original v1 schema remains committed unchanged;
the latest export is `schemas/case.v2.schema.json`.

- `Alteration.exon`, `exon_count`, `region_source` preserve source transcript
  numbering. Matching regions become variant-matched; known mismatches are
  excluded; unknown membership remains gene context. Ranges and compound
  requirements are checked without inventing missing exon membership.
- `loh_call` distinguishes `loh`, `no_loh`, `not_called`, with `loh_source`.
  Deprecated `caller_reported_loh` is retained. Explicit new calls take
  precedence, including `not_called`, while the original Boolean stays quoted.
  Neither representation is derived from VAF.
- `alternative_fits` carries purity, ploidy, native score, tool and disposition.
  Every model is enumerated with its zero-based source index, never ranked or
  selected. Native score is not composite interpretation confidence. Locus CN
  is not recalculated under different ploidy fits; this limitation is explicit.
- `visual_review` carries outcome, reviewer role, note and partial review date
  independently on tumour and normal. Codes are quoted; only exact
  `artifact`/`artefact` trigger the existing unreliable rule. Legacy
  `review_outcome` remains available and cannot silently clear contrary evidence.
- Non-exclusive template strands retain a nominal binomial p-value and an
  independence caveat without a strand-imbalance major flag. Exclusive strands
  use the existing test; omitted exclusivity retains v1 behavior.
- Treatment modality/general notes are separate from response notes. Specimen
  storage is separate from preservation.
- `Case.provenance: dict[str,str]` owns source paths, SHA-256 values and explicit
  ingestion decisions. It does not encode interpretation or promote labels.

## Migration and verification

Existing v1 files load unchanged. Missing values do not become negative, no
fit is preferred, and no composite score exists. The v2 synthetic example
populates the new structures. Its exact test expectations are extended for
the recorded exon, competing fit and visual quotes; unknown-exon and legacy
behavior remain separately tested. Regenerate schemas after domain changes;
contract checks compare the current schema with the models, preserving v1.
