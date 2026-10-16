# Interpretation fixtures

`rule_records.json` holds hand-written, synthetic `EvidenceRecord` payloads
keyed by scenario name (same-disease level A, parent-disease level B,
different-disease, submitted item, ClinVar oncogenic/benign, gene-level match,
literature hit). They exercise the rule tables in
`somaweave.interpretation.rules` against a synthetic lung adenocarcinoma
(OncoTree LUAD) case and do not describe real curated assertions.
