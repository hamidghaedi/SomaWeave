# Item 4 — population frequency and explicit hotspot evidence

Implemented after ingestion `3c20149`; independent item6 hygiene is committed
as `3ef0035`. Files: `providers/gnomad.py`, OncoKB mapping and registry,
`retrieval/plan.py`, domain evidence/exports and regenerated evidence schema,
interpretation rules/claims, example provider configuration, provider/retrieval
and rule tests, `POPULATION_HOTSPOTS.md`, architecture/HPC/roadmap and this report.
The optional evidence-v1 additions do not change existing input fields. Both
case schemas remain unchanged.

gnomAD uses exact GRCh38 alleles, joint adjusted AC/AN, a defined set of nine
major populations, and dataset `gnomad_r4` (minor release not claimed). HTTP,
GraphQL, absent-allele and missing-count states remain distinct. Queries are
limited to ten/minute, burst one. OncoKB's existing explicit hotspot flag
supplies a separate codon record; no second hotspot service is needed. OS3
now requires that flag, replacing record-count OS3/OM3 approximations.
Population cautions are conservative research mappings, not a validated full
VICC classifier. They never establish the patient's germline status, infer
LOH/clonality, or supply treatment evidence.

Offline regression tests cover exact identity/build, joint counts/popmax,
cache, absence versus failure, rate/status handling, threshold boundaries,
population-max precedence, a synthetic 5% splice-region allele, and explicit
hotspot versus treatment-record counts. The high-frequency allele remains
uncertain even with supportive curated records; no-record/zero-AF never
promotes oncogenicity. The full suite passes 345 tests; all three mandatory
commands exit0, and whitespace/LF scans pass. No environment was installed.

Live login-node checks on 2026-10-17:

- gnomAD GraphQL exact-allele lookup returned HTTP200 with joint counts;
  the maintained adapter also retrieved frequencies throughout all three
  case runs, using a previously absent gnomAD cache namespace.
- OncoKB adapter queried without a payload cache, returned `ok`, data v7.6,
  one oncogenic record and one explicit hotspot record. Token handling was
  unchanged; its contents were neither copied nor printed.

Sequential initial interpretation commands:
`python -m somaweave interpret-case <cases_v2/case.json> --run-id <case>-eval-5-population`.
All three exit0. All 115 alleles remain represented. Results compared with
the preserved eval-5 inputs/results, without tuning to the reviewed decisions:

| Case | Alleles | Changed axis labels (analytical / oncogenicity / tier / relevance) | SBVS1-style | SBS1-style | Explicit OS3 |
|---|---:|---|---:|---:|---:|
| case-A | 35 | 0 / 0 / 0 / 0 | 13 | 2 | 1 |
| case-B | 52 | 0 / 0 / 0 / 0 | 14 | 8 | 1 |
| case-C | 28 | 0 / 0 / 0 / 0 | 16 | 1 | 0 |

KMT2C stays uncertain, with SBVS1-style caution. Newly queried gnomAD joint AF
is 15.6832%, max major-population AF 19.4114% (nfe); the older upstream AF
annotation remains separately quoted and is not used as evidence. SETD2 stays
likely oncogenic via OVS1. CTNNB1/PIK3CA retain their existing classification
and gain explicit hotspot criteria. EGFR remains a VUS with no therapy names.
No allele changed biological classification, tier or relevance.

Initial gnomAD status counts: case-A `{ok:29,no_records:6}`;
case-B `{ok:33,no_records:17,unavailable:1,error:1}`;
case-C `{ok:27,no_records:1}`. case-B's failures were a 30-second read timeout
and the service's `Service overloaded` response; both are missing evidence,
never zero AF. The adapter now maps that explicit overload to `unavailable`.

Runtime root: `/global/scratch/hpc6049/somaweave_dev/`. Initial exploratory
runs preserve their original run IDs and pre-commit implementation hash audit.
A final replay uses `<case>-eval-5-population-final` from the committed source,
the same unchanged cases/cache/reference, and fresh result directories. Exact
commands, exit codes, final source hashes/statuses and the 115-row side-by-side
comparison with reviewed decision/category and reported OncoKB classifications
are in `validation_round3/item4/`; the replay evidence is in `final_runs/`.
The initial runs' manifest SHAs alone are not the release identity: the source
hash audit records the pre-commit development code. Final run manifests bind
the committed implementation. No runtime evidence or patient JSON enters Git.

Remaining limits: browser minor releases are unpinned, raw payload hashes bind
the observed snapshot; source failures can recur; no formal clinical validation
or new germline inference is implied. gnomAD has not yet been tested from a
compute node; item1's cold-cache result covers the original four sources.
