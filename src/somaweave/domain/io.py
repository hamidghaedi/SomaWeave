"""Loading, validating and serialising canonical objects.

JSON Schemas in ``schemas/`` are generated from these pydantic models by
``scripts/export_schemas.py`` and are the versioned external contract. A
contract test asserts the committed schema matches the models.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from somaweave.domain.case import Case
from somaweave.domain.evidence import EvidenceRecord

SCHEMA_VERSIONS = {"case": "v2", "evidence": "v1"}


def schema_dir() -> Path:
    """Locate the repository ``schemas/`` directory (editable install) or the
    packaged copy. Falls back to generating schemas in memory."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "schemas"
        if (candidate / f"case.{SCHEMA_VERSIONS['case']}.schema.json").exists():
            return candidate
    raise FileNotFoundError("schemas/ directory not found; run from a repository checkout")


def case_json_schema() -> dict[str, Any]:
    schema = Case.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://somaweave.local/schemas/case.{SCHEMA_VERSIONS['case']}.schema.json"
    return schema


def evidence_json_schema() -> dict[str, Any]:
    schema = EvidenceRecord.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://somaweave.local/schemas/evidence.{SCHEMA_VERSIONS['evidence']}.schema.json"
    return schema


class CaseValidationError(ValueError):
    def __init__(self, errors: list[dict[str, Any]]):
        self.errors = errors
        super().__init__(f"{len(errors)} validation error(s)")

    def pretty(self) -> str:
        lines = []
        for e in self.errors:
            loc = ".".join(str(p) for p in e.get("loc", ()))
            lines.append(f"- {loc or '<root>'}: {e.get('msg')}")
        return "\n".join(lines)


def load_case(path: str | Path) -> Case:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return case_from_dict(data)


def case_from_dict(data: dict[str, Any]) -> Case:
    try:
        return Case.model_validate(data)
    except ValidationError as exc:
        raise CaseValidationError(exc.errors(include_url=False)) from exc


def dump_model(obj: Any) -> dict[str, Any]:
    """JSON-ready dict with enums and dates serialised."""
    return json.loads(obj.model_dump_json(exclude_none=True))


def write_json(obj: Any, path: str | Path) -> None:
    Path(path).write_text(json.dumps(dump_model(obj), indent=2, sort_keys=False) + "\n", encoding="utf-8")
