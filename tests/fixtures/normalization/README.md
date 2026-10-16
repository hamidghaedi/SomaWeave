# Normalization test fixtures

All fixtures are hand-written and offline.

- `hgvs_cases.json`: table-driven protein and coding HGVS parsing cases (valid with expected fields; invalid lists).
- `oncotree_subset.json`: five entries in the public OncoTree `tumorTypes` JSON format, for the loader test only.
- `oncotree_subset_41.json`: 41 nodes copied from the public OncoTree release `oncotree_2025_10_03` (`/api/tumorTypes`), with `children`, `history`, `revocations`, `precursors` and `color` dropped. Covers lung, bowel, skin/eye melanoma, breast, pancreas, CNS (2025 codes `BRAIN`/`DIFG`/`GB`/`MBL`), soft tissue (`DES`), liver, testis/ovary germ-cell nodes (the duplicated name `Mixed Germ Cell Tumor` tests ambiguity handling) and `OTHER`/`CUP`. One deliberate deviation from the public data: `DES` carries a synthetic `externalReferences.DOID` entry (`DOID:0080366`) to exercise the file-level DOID path; the public release carries only `UMLS` and `NCI` references.
- `hgnc_subset.tsv`: four rows in HGNC complete-set column layout; `MLL4` is deliberately ambiguous between KMT2B and KMT2D as a previous symbol, and `MLL2` appears as a previous symbol of KMT2D and an alias of KMT2B.
