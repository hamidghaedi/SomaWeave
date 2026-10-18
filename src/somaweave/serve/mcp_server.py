"""Expose SomaWeave as Model Context Protocol (MCP) tools.

Agents (ToolUniverse via ``load_mcp_tools``, Claude Code, any MCP client) call
``somaweave_*`` tools; each tool runs the SomaWeave command line in the
configured interpreter and returns compact JSON — run identifiers, paths and
the four-axis finding summary read back from ``manifest.json``. Report text is
returned only when a client asks for it explicitly (``somaweave_get_report``);
nothing is sent anywhere by this module itself.

This module imports nothing from the rest of ``somaweave`` so it can run by
path from any interpreter that has the ``mcp`` package (on Frontenac the
isolated ``tooluniverse`` environment already does) while the engine runs in
the ``somaweave`` environment named by ``SOMAWEAVE_PYTHON``::

    SOMAWEAVE_PYTHON=~/.conda/envs/somaweave/bin/python \\
    SOMAWEAVE_RESULTS_ROOT=/path/outside/the/repo \\
    python src/somaweave/serve/mcp_server.py                      # stdio
    python src/somaweave/serve/mcp_server.py --transport streamable-http --port 8765

The ``mcp`` dependency is optional (``pip install somaweave[mcp]``) and is
imported lazily by :func:`build_server`; :class:`SomaWeaveRunner` is plain
standard library and is what the unit tests exercise.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

PYTHON_ENV_VAR = "SOMAWEAVE_PYTHON"
RESULTS_ENV_VAR = "SOMAWEAVE_RESULTS_ROOT"
DEFAULT_TIMEOUT_S = 1800.0
REPORT_FORMATS = {"markdown": "reports/report.md", "json": "reports/report.json", "manifest": "manifest.json",
                  "evidence": "evidence/evidence.json", "technical": "qc/technical.json", "log": "logs/run.log"}


@dataclass
class SomaWeaveRunner:
    """Runs the SomaWeave CLI in a chosen interpreter and reads run directories.

    ``python`` defaults to ``$SOMAWEAVE_PYTHON`` or the current interpreter;
    ``results_root`` to ``$SOMAWEAVE_RESULTS_ROOT``. ``extra_env`` is merged
    into the child environment (e.g. cache root, OncoKB token variable name).
    """

    python: Optional[str] = None
    results_root: Optional[str] = None
    timeout_s: float = DEFAULT_TIMEOUT_S
    extra_env: dict[str, str] = field(default_factory=dict)

    # -- helpers ---------------------------------------------------------------
    def interpreter(self) -> str:
        return self.python or os.environ.get(PYTHON_ENV_VAR) or sys.executable

    def results_dir(self) -> Path:
        root = self.results_root or os.environ.get(RESULTS_ENV_VAR)
        if not root:
            raise ValueError(f"results root not configured ({RESULTS_ENV_VAR} unset)")
        return Path(root).expanduser().resolve()

    def _run_cli(self, args: list[str]) -> dict[str, Any]:
        env = {**os.environ, **self.extra_env}
        if self.results_root:
            env[RESULTS_ENV_VAR] = str(self.results_root)
        cmd = [self.interpreter(), "-m", "somaweave", *args]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=self.timeout_s, env=env, check=False)
        except FileNotFoundError as exc:
            return {"ok": False, "exit_code": None, "error": f"interpreter not found: {exc}", "command": cmd}
        except subprocess.TimeoutExpired:
            return {"ok": False, "exit_code": None, "error": f"timed out after {self.timeout_s:g} s", "command": cmd}
        return {"ok": proc.returncode == 0, "exit_code": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:],
                "command": cmd}

    def _run_dir(self, run_id: str) -> Path:
        if not run_id or run_id in {".", ".."} or any(sep in run_id for sep in ("/", "\\")):
            raise ValueError("run_id must be a plain directory name")
        root = self.results_dir()
        run_dir = (root / run_id).resolve()
        if run_dir.parent != root:
            raise ValueError("run_id resolves outside the results root")
        if not (run_dir / "manifest.json").exists():
            raise FileNotFoundError(f"no run {run_id!r} under {root}")
        return run_dir

    @staticmethod
    def _summary_from_manifest(run_dir: Path) -> dict[str, Any]:
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        outputs = manifest.get("outputs") or {}
        return {
            "run_id": manifest.get("run_id"), "run_dir": str(run_dir), "case_id": (manifest.get("input") or {}).get("case_id"),
            "offline": manifest.get("offline"), "somaweave_version": manifest.get("somaweave_version"), "git_commit": manifest.get("git_commit"),
            "source_status_counts": manifest.get("source_status_counts"), "findings": manifest.get("findings"),
            "outputs": {k: str(run_dir / v) for k, v in outputs.items()},
        }

    # -- tools -------------------------------------------------------------------
    def validate_case(self, case_path: str) -> dict[str, Any]:
        """Validate a case JSON file against the canonical model; returns the CLI JSON summary or the validation errors."""
        res = self._run_cli(["validate-case", case_path, "--json"])
        if res["ok"]:
            try:
                res["summary"] = json.loads(res.get("stdout") or "{}")
            except ValueError:
                pass
        return res

    def build_case(self, manifest_path: str) -> dict[str, Any]:
        """Convert upstream pipeline files listed in a build manifest into canonical case.v2 JSON (``build-case --manifest``)."""
        return self._run_cli(["build-case", "--manifest", manifest_path])

    def interpret_case(self, case_path: str, run_id: Optional[str] = None, offline: bool = False,
                       providers_config: Optional[str] = None, oncotree_json: Optional[str] = None) -> dict[str, Any]:
        """Run the full interpretation workflow; returns run directory, output paths and the four-axis finding summary."""
        args = ["interpret-case", case_path]
        if run_id:
            args += ["--run-id", run_id]
        if offline:
            args.append("--offline")
        if providers_config:
            args += ["--providers-config", providers_config]
        if oncotree_json:
            args += ["--oncotree-json", oncotree_json]
        res = self._run_cli(args)
        if res["ok"]:
            line = next((ln for ln in (res.get("stdout") or "").splitlines() if ln.startswith("run ") and " complete: " in ln), "")
            run_dir = line.split(" complete: ", 1)[1].strip() if line else ""
            if run_dir and Path(run_dir, "manifest.json").exists():
                res.update(self._summary_from_manifest(Path(run_dir)))
        return res

    def list_runs(self, limit: int = 50) -> dict[str, Any]:
        """List run directories under the results root (newest first) with case id and finding count."""
        root = self.results_dir()
        runs = []
        for d in sorted((p for p in root.iterdir() if (p / "manifest.json").exists()), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
            try:
                m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
                runs.append({"run_id": m.get("run_id") or d.name, "case_id": (m.get("input") or {}).get("case_id"),
                             "finished_utc": m.get("finished_utc"), "offline": m.get("offline"), "findings": len(m.get("findings") or [])})
            except (OSError, ValueError) as exc:
                runs.append({"run_id": d.name, "error": f"unreadable manifest: {exc}"})
        return {"results_root": str(root), "runs": runs}

    def get_run(self, run_id: str) -> dict[str, Any]:
        """Return the manifest-derived summary of one run (paths, statuses, four-axis labels)."""
        return self._summary_from_manifest(self._run_dir(run_id))

    def get_report(self, run_id: str, format: str = "markdown", max_chars: int = 200_000) -> dict[str, Any]:
        """Return the content of a run artefact: markdown | json | manifest | evidence | technical | log."""
        rel = REPORT_FORMATS.get(format)
        if rel is None:
            raise ValueError(f"format must be one of {sorted(REPORT_FORMATS)}")
        path = self._run_dir(run_id) / rel
        if not path.exists():
            raise FileNotFoundError(f"{rel} missing in run {run_id!r}")
        text = path.read_text(encoding="utf-8")
        return {"run_id": run_id, "format": format, "path": str(path), "truncated": len(text) > max_chars, "content": text[:max_chars]}


def build_server(runner: SomaWeaveRunner | None = None, name: str = "somaweave"):
    """Create a FastMCP server with the SomaWeave tools registered (imports ``mcp`` lazily)."""
    from mcp.server.fastmcp import FastMCP  # noqa: PLC0415 - optional dependency

    runner = runner or SomaWeaveRunner()
    server = FastMCP(name, instructions=(
        "SomaWeave: evidence-grounded somatic cancer genomics interpretation (research use only). "
        "Tools run the deterministic SomaWeave engine on case JSON files and return run identifiers, paths and "
        "four-axis labels (analytical, oncogenicity, actionability, relevance). Use somaweave_get_report to read a report."))

    @server.tool(name="somaweave_validate_case")
    def validate_case(case_path: str) -> dict:
        """Validate a SomaWeave case JSON file (case.v1 or case.v2) and return its summary or validation errors."""
        return runner.validate_case(case_path)

    @server.tool(name="somaweave_build_case")
    def build_case(manifest_path: str) -> dict:
        """Build canonical case.v2 JSON from upstream pipeline outputs listed in a build manifest JSON."""
        return runner.build_case(manifest_path)

    @server.tool(name="somaweave_interpret_case")
    def interpret_case(case_path: str, run_id: str | None = None, offline: bool = False,
                       providers_config: str | None = None, oncotree_json: str | None = None) -> dict:
        """Run the SomaWeave interpretation workflow on a case JSON file. Returns run_dir, output paths and per-finding axis labels; live retrieval unless offline=true."""
        return runner.interpret_case(case_path, run_id=run_id, offline=offline, providers_config=providers_config, oncotree_json=oncotree_json)

    @server.tool(name="somaweave_list_runs")
    def list_runs(limit: int = 50) -> dict:
        """List SomaWeave runs under the configured results root, newest first."""
        return runner.list_runs(limit=limit)

    @server.tool(name="somaweave_get_run")
    def get_run(run_id: str) -> dict:
        """Summarise one SomaWeave run from its manifest: case id, source statuses, four-axis labels, output paths."""
        return runner.get_run(run_id)

    @server.tool(name="somaweave_get_report")
    def get_report(run_id: str, format: str = "markdown", max_chars: int = 200000) -> dict:
        """Return a run artefact's content. format: markdown | json | manifest | evidence | technical | log."""
        return runner.get_report(run_id, format=format, max_chars=max_chars)

    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve SomaWeave as MCP tools.")
    parser.add_argument("--transport", choices=["stdio", "streamable-http", "sse"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--python", default=None, help=f"SomaWeave interpreter (default: ${PYTHON_ENV_VAR} or this interpreter)")
    parser.add_argument("--results-root", default=None, help=f"Results root (default: ${RESULTS_ENV_VAR})")
    parser.add_argument("--list-tools", action="store_true", help="Print registered tool names and exit")
    args = parser.parse_args(argv)
    runner = SomaWeaveRunner(python=args.python, results_root=args.results_root)
    server = build_server(runner)
    if args.list_tools:
        import asyncio  # noqa: PLC0415

        for tool in asyncio.run(server.list_tools()):
            print(tool.name)
        return 0
    if args.transport != "stdio":
        server.settings.host = args.host
        server.settings.port = args.port
    server.run(transport=args.transport)
    return 0


if __name__ == "__main__":
    sys.exit(main())
