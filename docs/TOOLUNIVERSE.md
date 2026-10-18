# ToolUniverse integration

Status: stage A (ToolUniverse as a data-access layer) and stage B (SomaWeave
exposed as MCP tools, loadable into ToolUniverse) implemented 2026-10-18.

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
| `page_size`, `max_records` | registry page size and cap on records kept (across all levels) |
| `condition_levels` | hierarchy levels to query (default `diagnosis, oncotree, lineage, basket`) |

If the interpreter is not configured or the bridge cannot start, every query is
recorded as `unavailable` with the reason — missing evidence, never negative.

## Scientific position of trial records

- Query: gene symbol as free text plus a **condition hierarchy** on the
  **gene tier** only, most specific first: the recorded diagnosis as written,
  the confirmed OncoTree node name, ancestor names below tissue level, and a
  tumour-class basket ("Solid Tumor" / "Hematologic Malignancy"). ToolUniverse
  sends multi-word conditions to ClinicalTrials.gov as exact phrases, so a
  histology-specific diagnosis string alone almost never matches (the first
  real-case evaluation returned 0 of 115); the hierarchy is what makes the
  search informative. Results are de-duplicated by NCT id keeping the most
  specific level; each record states its level (`source_native_rating`,
  e.g. `basket: Solid Tumor`) and basket matches carry an extra limitation.
  Disease hypotheses are never merged into the condition terms. The match is a
  registry text match; eligibility criteria and biomarker requirements are
  **not** evaluated. Levels are configurable (`condition_levels`).
- Records carry `evidence_category = trial`, `variant_match = gene`,
  `is_hypothesis = true`. `is_accepted()` therefore rejects them: they can never
  enter the accepted pool and cannot influence analytical reliability,
  oncogenicity, actionability or relevance. No tier is derived from a trial.
- Reports list them in a separate subsection, "Clinical trials (registry
  search; context only)", quoting status, phases, matching level, registered
  interventions and conditions with the NCT identifier, and repeat the
  limitation. Because the search is gene-level text matching, the list is
  shown **only when the oncogenicity axis is oncogenic or likely oncogenic**;
  for other classifications the subsection states how many matches were
  retrieved and why they are not listed (records stay in the evidence JSON).
  The second real-case evaluation motivated this: 25 of 56 retrieved records
  belonged to a single EGFR variant of uncertain significance.
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

## Stage B: SomaWeave as MCP tools

`src/somaweave/serve/mcp_server.py` exposes the command line as Model Context
Protocol tools so agents can run SomaWeave without bespoke glue:

| tool | action |
|---|---|
| `somaweave_validate_case` | `validate-case --json` |
| `somaweave_build_case` | `build-case --manifest <json>` |
| `somaweave_interpret_case` | `interpret-case` (live or `offline=true`); returns run dir, output paths, four-axis labels from `manifest.json` |
| `somaweave_list_runs` / `somaweave_get_run` | enumerate and summarise runs under `SOMAWEAVE_RESULTS_ROOT` |
| `somaweave_get_report` | content of `markdown`, `json`, `manifest`, `evidence`, `technical` or `log` (explicit request only, truncated at `max_chars`) |

Properties:

- The module imports nothing from the rest of `somaweave`; the engine runs as a
  subprocess in the interpreter named by `SOMAWEAVE_PYTHON`. On Frontenac the
  server itself can run from the `tooluniverse` environment (which already has
  `mcp`), or from `somaweave` after `pip install -e ".[mcp]"`.
- `run_id` arguments must be plain directory names inside the results root;
  anything else is rejected, so a client cannot read arbitrary files.
- Results stay on the cluster. Only paths and manifest summaries are returned
  unless the client calls `somaweave_get_report`.

Run:

```bash
export SOMAWEAVE_PYTHON=~/.conda/envs/somaweave/bin/python
export SOMAWEAVE_RESULTS_ROOT=/path/outside/the/repo
~/.conda/envs/tooluniverse/bin/python src/somaweave/serve/mcp_server.py --list-tools
~/.conda/envs/tooluniverse/bin/python src/somaweave/serve/mcp_server.py                                     # stdio, for MCP clients
~/.conda/envs/tooluniverse/bin/python src/somaweave/serve/mcp_server.py --transport streamable-http --port 8765
```

ToolUniverse loads the HTTP form with
`ToolUniverse().load_mcp_tools(["http://127.0.0.1:8765"])`; the tools then
appear alongside its catalogue for any agent using that instance.

## Not in scope

ToolUniverse's agent skills, LLM-driven interpretation, Open
Targets or other ToolUniverse tools (candidates for later adapters), and any
comparison of AI models against OncoKB-derived content.
