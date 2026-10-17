# Population and hotspot evidence

The default exact-allele retrieval plan includes gnomAD v4. The adapter queries
the public GraphQL endpoint with the GRCh38 VCF-style chromosome, position, REF
and ALT, checks the returned identity, and uses **joint adjusted** AC/AN. It
never sums overlapping exome/genome samples. Unsupported assemblies, symbolic
alleles and non-small variants remain unassessed. No implicit liftover or
reference replacement occurs. Genomic exact-tier queries can run without HGVS.

`EvidenceRecord.population_frequency` preserves overall counts/AF and named
population frequencies. Max-population AF covers `afr, amr, ami, asj, eas, fin,
mid, nfe, sas`; sex strata and the heterogeneous `remaining` group are excluded.
Zero/absent denominators are never imputed to zero frequency. Raw payloads,
query, dataset selector (`gnomad_r4`) and retrieval date remain available. The
browser API does not pin a minor v4 release, so results do not claim one.
These are optional evidence-v1 additions; older evidence files still load.

Requests use the common injected transport, cache and bounded retry/status
handling. Defaults permit ten requests per minute, burst one. Configuration
cannot exceed that rate. GraphQL errors remain errors; only null-variant
responses or the service's exact 'variant not found' error mean no records.
An absent allele does **not** establish oncogenicity or pathogenicity.

Deterministic rules in `interpretation/rules.py` and `interpret.py`:

| Exact-allele measured frequency | Oncogenicity treatment |
|---|---|
| Overall or maximum major-population AF > 1% | SBVS1-style tag; strong probable-polymorphism caution; uncertain for review |
| AF > 0.1% and <= 1% | SBS1-style tag; frequency caution; uncertain for review |
| AF <= 0.1%, zero, or no records | Context only; no positive oncogenicity criterion |
| Source failure or unmeasured AF | Missing evidence; no frequency conclusion |

These are owner-specified conservative research rules, **not** a validated full
ClinGen/CGC/VICC classifier. They do not label the patient's allele germline,
assign benignity from frequency alone, change analytical ratings or erase
independent clinical evidence. If curated oncogenicity sources cannot be
queried, the classification remains not_assessed, with any measured caution
still quoted. Population retrieval alone cannot establish an actionability
tier. All cautions cite the exact evidence IDs. Upstream AF/classification
annotations remain quoted separately and do not enter these rules.

Hotspots use the explicit `hotspot=true` field already returned by OncoKB's
protein-change endpoint. A separate codon-level epidemiologic record carries
that flag, source dataVersion, citations and raw cache pointer. It can supply
OS3; the old record-count OS3/OM3 approximation is removed. Counts of treatment
records never establish recurrence. A hotspot alone does not promote an
otherwise unclassified allele or supply therapies. Existing curated-support
classification rules remain separate from hotspot tagging. `hotspot=false`
does not become benign evidence. No extra credentials or duplicated hotspot
API request is needed.

Implementation: `providers/gnomad.py`, `providers/oncokb.py`,
`retrieval/plan.py`, `domain/evidence.py`, `interpretation/{rules,interpret}.py`.
Offline tests: `tests/test_population_hotspot.py` and provider/retrieval rule
tests. Live checks and real-case comparisons stay outside Git; see item4 in
`docs/qc/somaweave_dev_round3/`.

Primary references checked 2026-10-17:

- [gnomAD API README](https://github.com/broadinstitute/gnomad-browser/blob/main/graphql-api/README.md)
- [gnomAD v4 query implementation](https://github.com/broadinstitute/gnomad-browser/blob/main/graphql-api/src/queries/variant-datasets/gnomad-v4-variant-queries.ts)
- [OncoKB API](https://api.oncokb.org/)
