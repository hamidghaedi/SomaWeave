"""ToolUniverse bridge: a child process that executes ToolUniverse tools on request.

SomaWeave never imports ``tooluniverse``. Its dependency footprint (faiss,
pandas 3, fastapi, mcp, huggingface_hub, ...) is incompatible with the pinned
``somaweave`` environment, so the package lives in its own environment and
this script is started from that environment's interpreter by
``somaweave.providers.tooluniverse.ToolUniverseBridgeTransport``.

The script depends only on the standard library plus ``tooluniverse``. It is
executed by path (``python /path/to/tooluniverse_bridge.py``), so it must not
import anything from ``somaweave``.

Protocol (newline-delimited JSON on stdin/stdout):

* On start the bridge loads the tool catalogue and writes one line::

      {"ready": true, "tooluniverse_version": "1.5.7", "tool_count": 3013}

  or ``{"ready": false, "error": "..."}`` and exits with status 1.
* Each request line is ``{"id": <str>, "tool": <name>, "arguments": {...}}``.
* Each response line is ``{"id": <str>, "ok": true, "result": <tool output>}``
  or ``{"id": <str>, "ok": false, "error": <message>}``.
* EOF on stdin ends the process.

Diagnostics go to stderr only; stdout carries protocol lines exclusively.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from importlib.metadata import PackageNotFoundError, version


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, default=str) + "\n")
    sys.stdout.flush()


def _load():
    # Running by path puts this directory first on sys.path, where the SomaWeave
    # adapter module is also named ``tooluniverse``; drop it so the import below
    # resolves to the installed package.
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != here]
    # ToolUniverse prints progress to stdout while loading; keep it off the protocol stream.
    with contextlib.redirect_stdout(sys.stderr):
        from tooluniverse import ToolUniverse  # noqa: PLC0415 - only available in the bridge environment

        tu = ToolUniverse()
        tu.load_tools()
    try:
        ver = version("tooluniverse")
    except PackageNotFoundError:
        ver = getattr(sys.modules.get("tooluniverse"), "__version__", None)
    return tu, ver


def main() -> int:
    try:
        tu, ver = _load()
    except Exception as exc:  # noqa: BLE001 - report every failure to the parent
        _emit({"ready": False, "error": f"{type(exc).__name__}: {exc}"})
        return 1
    _emit({"ready": True, "tooluniverse_version": ver, "tool_count": len(getattr(tu, "all_tools", []) or [])})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            rid = request.get("id")
            tool, arguments = request["tool"], request.get("arguments") or {}
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            _emit({"id": None, "ok": False, "error": f"malformed request: {exc}"})
            continue
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                result = tu.run({"name": tool, "arguments": arguments})
            _emit({"id": rid, "ok": True, "result": result})
        except Exception as exc:  # noqa: BLE001 - tool failures are reported, never fatal
            _emit({"id": rid, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
