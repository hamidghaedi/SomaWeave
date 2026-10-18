# PCGR approved release and execution record

Verified on compute nodes on 2026-10-18 UTC (native PCGR log timestamps use
America/Toronto and show the preceding evening). No installation, reference
download or write to shared PCGR assets occurred.

## Release identity

- Image: `/global/scratch/hpc6049/cancer_dbs/pcgr/container/pcgr_2.2.5.sif`,
  3,168,247,808 bytes; SHA-256
  `a92d8420afb839f58afec965fa10900cf68d6b9add64666cf88b76770b8746dc`.
- Reference version marker:
  `/global/scratch/hpc6049/cancer_dbs/pcgr/refdata/data/grch38/.PCGR_BUNDLE_VERSION`
  contains **20250314**. Pass its `refdata/` parent to `--refdata_dir`.
- VEP cache: `.../pcgr/vep_cache/homo_sapiens/113_GRCh38/`;
  cache `info.txt` and native manifest record GRCh38 / GENCODE47.
  Container `vep --help` reports ensembl-vep113.0 / Ensembl API113;
  its installed distribution directory is ensembl-vep-113.4-0.
  The staged wget log is empty and was not used as version proof.
- Compute-node probe job **12363604**, COMPLETED0:0, 16s:
  `module load apptainer/1.4.5` succeeded (rc0), actual runtime
  `apptainer version 1.4.5`, actual PCGR2.2.5. Binary resolved through the
  site's CVMFS module tree. The historical1.2.2 fallback was unnecessary.
- Shared assets are passed explicitly via external run JSON, as approved by
  the work order. No copying into or modification of SOMAWEAVE_REFERENCE_ROOT,
  environment creation, package installation or new reference fetch occurred.

Runtime root **R**:
`/global/scratch/hpc6049/somaweave_dev/comparators/pcgr/`.
All real inputs/payloads/results, PCGR outputs and machine-readable command
records remain there. Only synthetic-map proposals and technical narratives
enter Git. The image, reference, cache and sibling projects remain read-only.

## Exact command and mounts

The maintained entry is `python -m somaweave.comparators.pcgr run <run.json>`,
submitted through `hpc/slurm/pcgr.sbatch` using the existing SomaWeave Python.
Each external `execution.json` records the complete expanded argv, image/input
hashes, bindings, native exit, required-artifact status and elapsed seconds.
Adapter implementation is the commit introducing this record; resolve it with
`git log -1 --format=%H -- src/somaweave/comparators/pcgr/run.py`.
Execution took place on the item-B development implementation before its
validated commit; the private validation audit records its file snapshots.
No interpretation-engine code was modified. Later adapter changes added only
preflight/provenance checks and additional parser columns; they did not change
PCGR options or scientific results.

```bash
apptainer exec --containall --cleanenv --no-home --pwd /work \
  --bind INPUT_DIR:/input:ro --bind REFDATA:/reference:ro \
  --bind VEP_CACHE:/vep:ro --bind OUTPUT:/output:rw --bind WORK:/work:rw \
  IMAGE pcgr --input_vcf /input/input.vcf --vep_dir /vep \
  --refdata_dir /reference --output_dir /output/native \
  --genome_assembly grch38 --sample_id SAMPLE --assay WGS --tumor_site SITE \
  --tumor_af_tag TVAF --tumor_dp_tag TDP --control_af_tag NVAF \
  --control_dp_tag NDP --vep_n_forks 2 --vep_buffer_size 500 \
  --vcfanno_n_proc 2 --no_html
```

`APPTAINER_TMPDIR`, `APPTAINER_CACHEDIR` and work/output/cache directories are
external under R. Inputs/refdata/VEP are read-only binds. No scientific
AF/DP threshold, purity-fit selection, TMB/MSI/signature job or extra input was
added. HTML alone is skipped; native R classification/export still runs.
Each VCF includes raw tumour and available normal AF/DP tags; missing normal
support stays absent. Native source-version metadata is preserved in every
`*.conf.yaml`, including absent-version markers; no database is claimed to
be current beyond the bundled version.

Submission:

```bash
export SOMAWEAVE_PYTHON=/global/home/hpc6049/.conda/envs/somaweave/bin/python
export SOMAWEAVE_APPTAINER_MODULE=apptainer/1.4.5
sbatch --account=def-hpcg6049_cpu --time=01:00:00 --mem=12G \
  --cpus-per-task=2 --array=0-7%4 --export=ALL \
  --output=R/synthetic/slurm-%A_%a.out hpc/slurm/pcgr.sbatch R/synthetic/configs.txt
```

R in this example is the literal runtime root above, not a shell variable in
the actual argv. All expanded configurations and scheduler output are retained.

## Genomic side-map derivation

`tests/benchmark/comparators/genomic_map.tsv` has all11 finding rows,
**8 verified small-allele mappings and 3 explicit unmapped rows**, all
`reviewed=pending_owner`. It is a proposal, not owner signoff. Frozen case,
evidence and expected files are unchanged. No PCGR call or benchmark accuracy
is attributed to an unmapped finding.

Preferred offline HGVS conversion was tried in job12363605. Native VEP
returned255, `ERROR: Cannot use HGVS format in offline mode`; the probe wrapper
itself did not propagate that error, so its scheduler state is not success
proof. `R/mapping/vep_stderr.txt` and `vep_exit.txt` preserve it.
No online HGVS conversion or download was substituted.

The reproducible alternative is documented in `docs/PCGR_COMPARATOR.md`:
unique MANE_Select cross-reference row → VEP113 cached exon/CDS model →
enumerated unique nucleotide substitution/contiguous deletion → independently
verified indexed FASTA REF → native PCGR forward VEP annotation.
`mapping.py` and `export_transcripts.pl` implement that route. Private artifacts
under `R/mapping/` include selected transcripts, models, candidate positions,
FASTA queries/results and `prepare_synthetic.py`. Model extraction12363609
succeeded. The maintained exporter was separately run in12363626,
COMPLETED0:0, 2s, and its JSON models equal those used for derivation. REF
verification12363617 completed0:0; every exported reference allele matched.
Initial cache deserialization through IO::Uncompress failed; native VEP's
Storable-over-gzip-pipe approach worked. No failed probe is counted as a mapping.

Native forward annotations match all8 exported descriptions (protein/CDS HGVS
and consequences), including the anchored KIT deletion. Important limits:

- Scenario08 CTNNA1 p.Arg100Gly is not mappable on MANE Select
  ENST00000302763.12: residue100 is **Gln**, not Arg. The coordinate columns
  remain empty. No alternative transcript or p.Gln100Gly substitution was
  invented. Its APC finding alone ran, explicitly marked partial in scope.json.
- TERT c.-124C>T is mapped literally relative to the selected CDS start to
  GRCh38 chr5:1295113G>A; native VEP reports that exact c.-124C>T. It was not
  silently replaced by a TSS-relative hotspot. Owner genomic-map review should
  confirm the intended reference convention before using this as an adjudicated
  promoter benchmark.
- Scenario09 has only qualitative ERBB2 amplification and KIF5B::RET fusion
  labels, no segment/breakpoint or quantitative native comparator inputs. It
  cannot supply an SNV VCF; no empty successful run, made-up CNA segment or
  RNA-fusion input was created. Clarification remains pending.

## Synthetic Slurm outcomes

Array12363618, CPU-only, 2CPUs/12G/task; all8 submitted tasks completed0:0.
This is **7 complete scenarios plus one partial scenario**, not9 complete
benchmark scenarios. Each manifest below is relative to R. Native PCGR exits
and adapter exits are both0 and final annotations/manifests exist.

| Scenario | Array task / native job ID | State / exit | Scheduler wall time | PCGR elapsed seconds | Source-version manifest |
|---|---|---|---|---|---|
| 01_driver | 12363618_0 / 12363619 | COMPLETED / 0:0 | 00:01:39 | 87.948 | `synthetic/01_driver/output-1/native/01_driver.pcgr.grch38.conf.yaml` |
| 02_rare_tumour | 12363618_1 / 12363620 | COMPLETED / 0:0 | 00:01:06 | 55.279 | `synthetic/02_rare_tumour/output-1/native/02_rare_tumour.pcgr.grch38.conf.yaml` |
| 03_recurrence | 12363618_2 / 12363621 | COMPLETED / 0:0 | 00:01:39 | 88.145 | `synthetic/03_recurrence/output-1/native/03_recurrence.pcgr.grch38.conf.yaml` |
| 04_resistance_timing | 12363618_3 / 12363622 | COMPLETED / 0:0 | 00:01:38 | 86.946 | `synthetic/04_resistance_timing/output-1/native/04_resistance_timing.pcgr.grch38.conf.yaml` |
| 05_vaf_cn | 12363618_4 / 12363623 | COMPLETED / 0:0 | 00:01:36 | 85.332 | `synthetic/05_vaf_cn/output-1/native/05_vaf_cn.pcgr.grch38.conf.yaml` |
| 06_ffpe_artifact | 12363618_5 / 12363624 | COMPLETED / 0:0 | 00:01:41 | 88.614 | `synthetic/06_ffpe_artifact/output-1/native/06_ffpe_artifact.pcgr.grch38.conf.yaml` |
| 07_discordant_pathology | 12363618_6 / 12363625 | COMPLETED / 0:0 | 00:01:40 | 87.010 | `synthetic/07_discordant_pathology/output-1/native/07_discordant_pathology.pcgr.grch38.conf.yaml` |
| 08_insufficient_conflicting | 12363618_7 / 12363618 | COMPLETED / 0:0 | 00:01:40 | 87.744 | `synthetic/08_insufficient_conflicting/output-1/native/08_insufficient_conflicting.pcgr.grch38.conf.yaml` |

## Adapter failure handling and limits

Initial private-case attempts12363611–12363613 exposed PCGR's temporary-prefix
assumption: `--output_dir /output` generated a sibling `/outputXXXX` under the
read-only container root. A bcftools child failed, yet PCGR returned0 without
its source manifest or final annotation. These are **failed attempts** and
remain external; they are not accepted runs. The adapter now uses nested
`/output/native` and rejects native0 without both required artifacts. Offline
regression tests cover that case and reject writable/reference overlap before
creating directories. No change to the image or its scientific code was made.

Remaining acceptance gaps: scenario09 cannot run from supplied inputs;
scenario08 is partial; three map rows lack resolvable genomic inputs. Owner
signatures/map review/crosswalk approval remain pending. These gaps prevent a
claim of full item-B acceptance despite successful execution of all valid
submitted work. See `pcgr_comparison.md` for all11 findings.
