# Normalization test fixtures

All fixtures are hand-written and offline.

- `hgvs_cases.json`: table-driven protein and coding HGVS parsing cases (valid with expected fields; invalid lists).
- `oncotree_subset.json`: five entries in the public OncoTree `tumorTypes` JSON format, for the loader test only.
- `hgnc_subset.tsv`: four rows in HGNC complete-set column layout; `MLL4` is deliberately ambiguous between KMT2B and KMT2D as a previous symbol, and `MLL2` appears as a previous symbol of KMT2D and an alias of KMT2B.
