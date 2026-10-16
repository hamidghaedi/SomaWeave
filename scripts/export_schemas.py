#!/usr/bin/env python
"""Regenerate schemas/*.schema.json from the pydantic models.

Run after any domain-model change and commit the result together with a
schema version bump and migration notes when the change is breaking.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from somaweave.domain.io import SCHEMA_VERSIONS, case_json_schema, evidence_json_schema  # noqa: E402


def main() -> int:
    out = ROOT / "schemas"
    out.mkdir(exist_ok=True)
    targets = {
        out / f"case.{SCHEMA_VERSIONS['case']}.schema.json": case_json_schema(),
        out / f"evidence.{SCHEMA_VERSIONS['evidence']}.schema.json": evidence_json_schema(),
    }
    check = "--check" in sys.argv
    rc = 0
    for path, schema in targets.items():
        text = json.dumps(schema, indent=2, sort_keys=True) + "\n"
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                print(f"OUT OF DATE: {path.relative_to(ROOT)}")
                rc = 1
            else:
                print(f"ok: {path.relative_to(ROOT)}")
        else:
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
