#!/usr/bin/env python
"""Repository structure check against docs/REPOSITORY_CONTRACT.md.

Fails if: unknown top-level entries exist, Python modules live outside the
allowed locations, tracked files look like runtime data or secrets, or
cluster-specific identifiers appear in reusable code.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ALLOWED_TOP_LEVEL = {
    "README.md", "LICENSE", "pyproject.toml", ".gitignore", ".github",
    "src", "schemas", "configs", "examples", "tests", "hpc", "scripts", "docs",
}
ALLOWED_PACKAGES = {
    "domain", "normalization", "technical", "providers", "retrieval",
    "evidence", "interpretation", "reporting", "workflows",
}
PY_ALLOWED_ROOTS = ("src/somaweave/", "tests/", "scripts/")
FORBIDDEN_SUFFIXES = {".vcf", ".bam", ".cram", ".bai", ".sif", ".log", ".token", ".pem"}
SECRET_PATTERNS = [re.compile(p) for p in (
    r"(?i)api[_-]?key\s*[=:]\s*['\"][A-Za-z0-9_\-]{16,}",
    r"(?i)bearer\s+[A-Za-z0-9_\-\.]{20,}",
    r"ghp_[A-Za-z0-9]{20,}",
)]
# Cluster-specific identifiers must not appear in reusable code (src/).
SITE_SPECIFIC = [re.compile(p) for p in (
    r"/global/(project|scratch|home)/", r"def-hpcg\d+", r"cpubase_|gpubase_", r"hpc\d{4}",
)]
MAX_TRACKED_BYTES = 2_000_000


def tracked_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                             cwd=ROOT, check=True, capture_output=True, text=True).stdout
        return [ROOT / line for line in out.splitlines() if line.strip()]
    except Exception:
        return [p for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]


def main() -> int:
    problems: list[str] = []
    files = tracked_files()

    for entry in ROOT.iterdir():
        if entry.name == ".git":
            continue
        if entry.name not in ALLOWED_TOP_LEVEL:
            problems.append(f"unexpected top-level entry: {entry.name}")

    pkg_root = ROOT / "src" / "somaweave"
    if pkg_root.exists():
        for child in pkg_root.iterdir():
            if child.is_dir() and child.name not in ALLOWED_PACKAGES and child.name != "__pycache__":
                problems.append(f"unexpected package under src/somaweave/: {child.name} (update the contract first)")

    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        if f.suffix == ".py" and not rel.startswith(PY_ALLOWED_ROOTS):
            problems.append(f"python file outside allowed roots: {rel}")
        if f.suffix.lower() in FORBIDDEN_SUFFIXES:
            problems.append(f"runtime/data file tracked: {rel}")
        if f.exists() and f.stat().st_size > MAX_TRACKED_BYTES:
            problems.append(f"large file tracked ({f.stat().st_size} bytes): {rel}")
        if f.suffix in {".py", ".toml", ".yaml", ".yml", ".json", ".md", ".sh", ".cfg", ".ini"} and f.exists():
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    problems.append(f"possible secret in {rel}")
                    break
            if rel.startswith("src/"):
                for pat in SITE_SPECIFIC:
                    if pat.search(text):
                        problems.append(f"site-specific identifier in reusable code: {rel} ({pat.pattern})")
                        break

    if problems:
        print("structure check FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"structure check ok ({len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
