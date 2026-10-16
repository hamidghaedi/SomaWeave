# Evidence fixtures

`retrieval_ctnnb1_d32n.json` is a serialised `somaweave.retrieval.RetrievalResult`
for alteration A1 (CTNNB1 p.Asp32Asn) of `examples/synthetic_case.json`. It was
produced offline by replaying the recorded provider exchanges in
`tests/fixtures/providers/` (CIViC exact/codon/gene, ClinVar exact, Europe PMC
exact/gene-class/disease-only with synthetic zero-hit responses for the other
tiers) through `run_plan`. Regenerate the same way if the provider fixtures or
the retrieval layer change. No network access is needed to use it.
