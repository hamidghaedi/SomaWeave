# ToolUniverse integration

Status: implemented 2026-10-18 (stage A, data access). Stage B (exposing
SomaWeave itself as an MCP tool) is tracked separately.

## What ToolUniverse is, and how SomaWeave uses it

ToolUniverse (Harvard MIMS lab, Apache-2.0) is a registry of several thousand
scientific tools — thin wrappers around public APIs with a uniform JSON call
interface — exposed three ways: a Python SDK (`ToolUniverse().run(...)`), an
MCP server for LLM agents, and separately installed agent skills.

SomaWeave uses only the first layer, as a **deterministic data-access adapter**.
No LLM is involved, nothing is interpreted by ToolUniverse, and the adapter is
one provider among others behind the stable `Provider` interface. The first tool
wired in is `ClinicalTrials_search_studies` (ClinicalTrials.gov API v2).

## Isolation: why a bridge process

`tooluniverse` 1.5.7 requires `faiss-cpu==1.12.0`, `pandas>=3`, `fastapi`,
`fastmcp`, `mcp`, `huggingface_hub`, `boltz-api`, `pdfplumber`, `rcsb-api` and
more (≈730 MB installed). Those pins cannot coexist with the `somaweave`
environment, so:

- ToolUniverse lives in its own environment (`hpc/env/tooluniverse.yaml`).
- SomaWeave never imports it. `src/somaweave/providers/tooluniverse_bridge.py`
  is a stdlib-only script executed *by the ToolUniverse interpreter* as a
  persistent child process; it loads the catalogue once (≈10 s) and then
  answers newline-delimited JSON requests `{"id", "tool", "arguments"}` with
  `{"id", "ok", "result" | "error"}`.
- `ToolUniverseBridgeTransport` implements the ordinary `Transport` protocol
  for URLs of the form `tooluniverse://<tool name>`, so the payload cache,
  `RecordingTransport` and `ScriptedTransport` fixtures work unchanged.
- The bridge is started with a minimal environment (`clean_environment: true`)
  because the Compute Canada login shell exports a `PYTHONPATH` whose
  `_manylinux.py` shadows standard behaviour. Only `HOME`, `PATH`, locale,
  temp-dir, proxy and CA-bundle variables are passed through.

Configuration (`configs/providers.example.json`, key `tooluniverse`):

| key | meaning |
|---|---|
| `python_executable` | interpreter of the ToolUniverse environment; `null` → `$SOMAWEAVE_TOOLUNIVERSE_PYTHON` |
| `clean_environment` | start the bridge with a minimal environment (default `true`) |
| `startup_timeout_s` | catalogue load allowance (default 180 s) |
| `search_tool` | ToolUniverse tool name (default `ClinicalTrials_search_studies`) |
| `statuses` | ClinicalTrials.gov overall-status filter (default recruiting / not yet recruiting) |
| `page_size`, `max_records` | registry page size and cap on records kept |

If the interpreter is not configured or the bridge cannot start, every query is
recorded as `unavailable` with the reason — missing evidence, never negative.

## Scientific position of trial records

- Query: gene symbol as free text plus the recorded diagnosis as condition, on
  the **gene tier** only. The match is a registry text match; eligibility
  criteria and biomarker requirements are **not** evaluated.
- Records carry `evidence_category = trial`, `variant_match = gene`,
  `is_hypothesis = true`. `is_accepted()` therefore rejects them: they can never
  enter the accepted pool and cannot influence analytical reliability,
  oncogenicity, actionability or relevance. No tier is derived from a trial.
- Reports list them in a separate subsection, "Clinical trials (registry
  search; context only)", quoting status, phases, registered interventions and
  conditions with the NCT identifier, and repeat the limitation.
- Each record keeps `source_version` (`tooluniverse <version>; ClinicalTrials.gov
  API v2`), the retrieval timestamp and a pointer to the cached raw payload.

## Licensing

ToolUniverse code: Apache-2.0. ClinicalTrials.gov data are US-government public
records. Other ToolUniverse tools wrap sources with their own terms; in
particular OncoKB content reached through ToolUniverse remains under the OncoKB
licence (no AI/ML training, permission required for benchmarking models). The
adapter is restricted by configuration to the trial-registry tool.

## Validation

- `tests/test_provider_tooluniverse.py`: record mapping from a recorded live
  response, empty/erroneous payloads, tier support, cache round trip, registry
  and planner wiring, and the real bridge script driven by a stub
  `tooluniverse` package (handshake, request, tool error, missing interpreter).
- Live check on the Frontenac login node (2026-10-18): catalogue load 10.7 s,
  3,013 tools; `ClinicalTrials_search_studies` round trip 4.5 s.

## Not in scope

ToolUniverse's MCP server and agent skills, LLM-driven interpretation, Open
Targets or other ToolUniverse tools (candidates for later adapters), and any
comparison of AI models against OncoKB-derived content.
