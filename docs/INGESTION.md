# Building a case from pipeline outputs

`build-case` converts the paired WGS pipeline's reviewed outputs to case.v2.
It does not select variants, infer diagnoses or call APIs. Every interpreted
table row survives, including NOT_SELECTED, VUS and held alleles.

```bash
somaweave build-case --bam-review review.tsv --purple primary.purple.purity.tsv \
  --maf variants.maf.gz --vcf caller.vcf.gz --clinical clinical.xlsx \
  --clinical-context reviewed_clinical.json --assembly GRCh38 \
  --lab-manifest lab.csv --alternative-fits alternate_solutions.tsv \
  --purple-disposition fit_disposition.json --out case.json
```

Required inputs: BAM-review TSV, PURPLE primary purity and adjacent somatic
segment TSV, MAF, clinical JSON/XLSX and output. Optional explicit inputs add
caller VCF FILTER, laboratory methods, Picard coverage, caller/version and its
provenance file, final review categories, native alternative solutions and
scientific fit disposition. No file path has a deployment default. `--purple`
may also name a directory containing exactly one primary purity file.

Clinical JSON can supply canonical clinical fields (`case_id`, `assembly`,
`diagnosis`, `specimens`, `treatments`, `disease_hypotheses`, `clinical_events`),
or a released flat clinical_context with its clinical_rows. XLSX reads the
pipeline's donor/registration/specimen/diagnosis/treatment sheets with standard
library readers; no formulas are executed and no dependency is installed.
Canonical context overlays explicitly supply reviewed diagnosis names/hypotheses;
the adapter never derives those from variants, morphology alone or treatment.
An absent written diagnosis is labelled absent. Role binding uses registration
and MAF sample IDs, not a specimen-name guess.

`--manifest` accepts JSON `{"cases": [<options>, ...]}`. Each row has the same
option names with underscores and explicit `out`. Relative paths resolve from
the manifest directory. Rows execute in order; existing outputs are not
overwritten. Do not combine manifest and individual case options.

## Mapping and missing fields

- Exact anchored allele keys are preserved. MAF joins use gene, VCF position
  and protein label; ambiguity or ALT/depth disagreement fails. Unmatched MAF
  rows still survive, with raw REF unknown rather than invented as depth-ALT.
- JSON QC arrays are decoded and validated. Caller FILTER and annotation
  FILTER remain separate. Later review-category decisions take precedence in
  reported review labels; the original TSV and category files remain hashed.
- Read/template layers, non-exclusive strands and median qualities stay
  separate. Clipping is the measured local ALT-template fraction. Median NM
  remains reported data, not a substitute for additional local mismatches.
  Visual state is quoted; suspected artifact never becomes confirmed artifact.
- Exon N/total and its transcript are copied from the MAF. Unstructured exon
  labels are retained as mapping limitations, not guessed.
- PURPLE primary fit and pathology range stay separate. Every supplied
  alternate solution except the explicit Primary row is retained in source
  order, including repeated fit values. Raw search-grid points are not chosen
  as competing models. `not_called` means no explicit per-locus LOH call was
  supplied, not that all LOH analysis was unperformed. No minor-CN inference.
- Library data enrich the WGS methods/specimen context; Picard mean coverage
  is used if supplied. A caller/version must be explicitly passed, never
  inferred from installed software. Library tumour descriptor and clinical
  metastatic registration are preserved separately if inconsistent.
- Each source path and SHA-256, ingestion module hashes, mapping version and
  missing-field decisions live in `Case.provenance`. Source classifications
  are annotations quoted as reported, never interpretation evidence.

All case inputs, manifests, runtime results and source/reference data belong
outside Git. The checked-in five-row review, three-segment PURPLE, two-record
MAF and tiny clinical JSON under `tests/fixtures/ingest` are synthetic.
