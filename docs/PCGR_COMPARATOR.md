# PCGR comparator

The owner-approved comparator is PCGR2.2.5 with bundle20250314 and VEP113.
No installation or reference download is needed. It is independent of the
unsigned benchmark scoring gate; comparison does not adjudicate expectations.

## Commands

Use the existing SomaWeave Python environment, outside runtime output paths in
Git. Supply paths explicitly:

```bash
python -m somaweave.comparators.pcgr export --case /path/case.json \
  --sample synthetic --out /scratch/input/input.vcf
# For a protein-only synthetic case, also supply:
# --map tests/benchmark/comparators/genomic_map.tsv --scenario 01_driver

export SOMAWEAVE_PYTHON=/path/to/existing/environment/bin/python
export SOMAWEAVE_APPTAINER_MODULE=apptainer/1.4.5
sbatch --account=<account> --time=01:00:00 --mem=12G --cpus-per-task=2 \
  --export=ALL hpc/slurm/pcgr.sbatch /scratch/run.json

python -m somaweave.comparators.pcgr parse \
  --table /scratch/output/native/sample.pcgr.grch38.snv_indel_ann.tsv.gz \
  --native-vcf /scratch/output/native/sample.pcgr.grch38.vcf.gz \
  --ledger /scratch/input/input.export.json --out /scratch/comparison.json
```

External `run.json` supplies `input_vcf`, `image`, `refdata` (parent of `data/`),
`vep_cache`, fresh `output`, `work`, `cache`, `sample`, integer `tumor_site`,
and `threads`. A Slurm array receives a newline-separated config-path list;
array indices start at zero. The Python adapter uses explicit read-only
input/reference binds and writes only to external output/work/cache. Runtime
image/input hashes, actual Apptainer version, full command, bind list, native
exit code and required-artifact status go to `execution.json`. Require both a
native source-version YAML and final annotation table: PCGR2.2.5 can return
zero after a failed child command. `/output/native` is deliberately nested:
PCGR's bcftools temp-prefix construction otherwise tries to write beside the
bind mount at `/outputXXXX`, which is outside the writable output directory.

## Export and identity rules

`comparators/pcgr/vcf.py` documents every mapping rule. Export every small
allele, including held alleles; retain native caller FILTER codes. TVAF/NVAF
use raw ALT/(REF+ALT), TDP/NDP retain depth, and absent support stays missing.
GT0/1 is a VCF format placeholder, not a measured or inferred genotype.
An explicit specimen is required for ambiguous measurements. No lift-over,
protein-name fuzzy joins, inferred purity selection or scientific filtering.
PCGR tissue integers use an explicit recorded-OncoTree lookup; unknown codes
use site0 with a note. Disease hypotheses never replace the recorded diagnosis.
This limited map is not a general OncoTree ontology service.

The final parser preserves PCGR's native oncogenicity criteria, AMP tier,
consequence, hotspot, population and ClinVar assertions. Multiple transcript
rows remain visible. An absent annotation is not a benign call. Its filter
reason is unknown unless a native FILTER explicitly supplies it. Re-expression
of an indel is not silently reconciled; investigate an unmatched exact key.
PCGR does not assess the analytical read/template axis.

## Offline synthetic genomic mapping

VEP113 rejects HGVS input with `--offline` (exit255). The alternative uses
its staged transcript cache, not online conversion or a guessed hotspot:

1. `mapping.select_mane(xref, genes)` chooses the unique `MANE_Select` row in
   the matching reference bundle's compressed `gene_transcript_xref.tsv.gz`.
   The relevant marker is in `gencode_tag`, not the empty `mane_select2` column.
2. In the approved container, run
   `perl export_transcripts.pl /vep /input/selected_transcripts.json` using the
   module resource under `src/somaweave/comparators/pcgr/`. It reads VEP113's
   compressed Storable models, exporting CDS, peptide, strand, exon coordinates
   and coding start. No database adaptor or network call is made.
3. `mapping.protein_snv` verifies the reference amino acid and enumerates all
   single-base substitutions that produce the specified alternate amino acid.
   Require exactly one. `deletion_interval` requires a contiguous genomic
   deletion, then anchors it using the preceding GRCh38 reference base.
4. Verify every REF with the staged indexed FASTA using `samtools faidx` in
   the container. A literal c.-124 offset is relative to the CDS start, not
   automatically the common TSS-relative promoter hotspot. In the 1-based CDS
   helper, c.-124 corresponds to coordinate `1-124`.
5. Forward VEP annotation is part of the native PCGR run. Retain the chosen
   transcript and check its consequence/HGVS against the input description.
   Synthetic evidence supplied to SomaWeave is not supplied to PCGR.

The side map is a proposal with `reviewed=pending_owner`. Reference mismatch,
ambiguous substitutions and qualitative CNV/fusion-only cases are not exported.
Unmapped rows explicitly retain their reason and empty genomic columns. Do
not substitute another residue or invent CNA segments/RNA measurements to fill
a benchmark cell. Current execution evidence and uncovered findings are in
[the release record](qc/somaweave_dev_round4/pcgr_release.md).
