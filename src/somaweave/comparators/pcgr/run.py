"""Execute the approved external release, preserving commands and return codes.

Every path is supplied in an external JSON configuration. No scientific options
are inferred from VAF, classifications, purity alternatives or treatment history.
In particular, no fit is selected for PCGR and no TMB/MSI/signature job is added.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(config_path: Path) -> int:
    cfg = json.loads(config_path.read_text())
    required = ("input_vcf", "image", "refdata", "vep_cache", "output", "work", "cache", "sample", "tumor_site")
    for name in required:
        if name not in cfg:
            raise ValueError(f"missing run configuration: {name}")
    paths = {k: Path(cfg[k]).resolve() for k in required if k not in {"sample", "tumor_site"}}
    for name in ("input_vcf", "image", "refdata", "vep_cache"):
        if not paths[name].exists():
            raise ValueError(f"missing {name}")
    for a in ("input_vcf", "image", "refdata", "vep_cache"):
        for b in ("output", "work", "cache"):
            if paths[b] == paths[a] or paths[b].is_relative_to(paths[a]) or paths[a].is_relative_to(paths[b]):
                raise ValueError("writable directory overlaps a read-only input/reference")
    writable = [paths[n] for n in ("output", "work", "cache")]
    if any(a == b or a.is_relative_to(b) or b.is_relative_to(a)
           for i, a in enumerate(writable) for b in writable[i + 1:]):
        raise ValueError("output/work/cache must be distinct, non-overlapping directories")
    for name in ("output", "work", "cache"):
        # Output cannot overwrite a completed or failed attempt.
        paths[name].mkdir(parents=True, exist_ok=name != "output")
    threads = int(cfg.get("threads", 1))
    if threads < 1:
        raise ValueError("threads must be positive")
    binary = os.environ.get("SOMAWEAVE_APPTAINER", "apptainer")
    bindings = [(paths["input_vcf"].parent, "/input", "ro"), (paths["refdata"], "/reference", "ro"),
                (paths["vep_cache"], "/vep", "ro"), (paths["output"], "/output", "rw"),
                (paths["work"], "/work", "rw")]
    cmd = [binary, "exec", "--containall", "--cleanenv", "--no-home", "--pwd", "/work"]
    for src, dest, mode in bindings:
        if "," in str(src) or ":" in str(src):
            raise ValueError("unsafe bind path")
        cmd += ["--bind", f"{src}:{dest}:{mode}"]
    cmd += [str(paths["image"]), "pcgr", "--input_vcf", f"/input/{paths['input_vcf'].name}",
            "--vep_dir", "/vep", "--refdata_dir", "/reference", "--output_dir", "/output/native",
            "--genome_assembly", "grch38", "--sample_id", cfg["sample"], "--assay", "WGS",
            "--tumor_site", str(int(cfg["tumor_site"])), "--tumor_af_tag", "TVAF", "--tumor_dp_tag", "TDP",
            "--control_af_tag", "NVAF", "--control_dp_tag", "NDP", "--vep_n_forks", str(threads),
            "--vep_buffer_size", "500", "--vcfanno_n_proc", str(threads), "--no_html"]
    env = os.environ.copy()
    env.update(APPTAINER_CACHEDIR=str(paths["cache"]), APPTAINER_TMPDIR=str(paths["work"]),
               TMPDIR=str(paths["work"]))
    version = subprocess.run([binary, "--version"], capture_output=True, text=True, check=True).stdout.strip()
    record = {"configuration": cfg, "command": cmd,
              "binds": [{"source": str(s), "destination": d, "mode": m} for s, d, m in bindings],
              "input_sha256": sha256(paths["input_vcf"]), "image_sha256": sha256(paths["image"]),
              "apptainer": version, "job_id": os.environ.get("SLURM_JOB_ID"),
              "started_unix": time.time(), "classification_vocabulary": "PCGR native; no tier crosswalk"}
    record["adapter_sources_sha256"] = {p.name: sha256(p) for p in Path(__file__).parent.glob("*.py")}
    with (paths["output"] / "execution.stdout.txt").open("w") as out, (paths["output"] / "execution.stderr.txt").open("w") as err:
        result = subprocess.run(cmd, env=env, stdout=out, stderr=err, check=False)
    # PCGR 2.2.5 can return zero after a child failure. Require both final
    # machine-readable annotation and source-version manifest as evidence.
    manifests = list(paths["output"].glob("native/*.conf.yaml"))
    tables = list(paths["output"].glob("native/*.snv_indel_ann.tsv.gz"))
    complete = bool(manifests and tables)
    rc = result.returncode if result.returncode else (0 if complete else 1)
    record.update(native_exit_code=result.returncode, exit_code=rc, artifacts_complete=complete,
                  elapsed_seconds=time.time() - record["started_unix"],
                  native_manifests=[str(p) for p in manifests])
    (paths["output"] / "execution.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({k: record[k] for k in ("job_id", "exit_code", "elapsed_seconds", "native_manifests")}))
    return rc
