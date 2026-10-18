# ToolUniverse integration evaluation

Owner work order issued2026-10-18. Executed source:
`6269ffc27774a00135d99d9fb6cd3013b5e6dc9b`, in a clean detached worktree.
PYTHONPATH selects that worktree's src for every engine invocation; the bridge
retains its configured clean environment. The owner's concurrent main-checkout
documentation changes are preserved. No engine/report-rule changes, package
installation, environment upgrade, new reference or other ToolUniverse tool
execution occurred.

Private evaluation root **E**:
`/global/scratch/hpc6049/somaweave_dev/evaluation/tooluniverse/`.
Its `inputs.json`, submissions, native payload caches, query records, case
reports and comparisons remain external. `source_6269ffc/` contains code only;
all inputs/results/caches are outside that Git worktree. Existing environments:
`~/.conda/envs/somaweave` and isolated `~/.conda/envs/tooluniverse`1.5.7.

| Test | Status | Evidence |
|---|---|---|
| T1 | Complete: compute-node bridge and registry retrieval work | Below; E/T1 |
| T2 | Complete:115 queries, no records, all460 axis labels unchanged | Below; E/T2 |
| T3 | Conditional pass: six tools and both calls succeed after SDK MCP-class preload; bare SDK discovery fails | Below; E/T3 |
| T4 | Complete:387 tests, one expected skip; isolated MCP registration test passes; structure/schema checks pass | Below; E/T4 and E/validation |

## T1 — compute-node cold provider cache

Slurm job **12363740**, node **frnt152**, COMPLETED, exit **0:0**, scheduler
elapsed **00:00:55**. A newly created, initially empty SomaWeave provider cache
was used. This is a cold provider-cache check, not a claim that remote services
or the operating-system file cache were cold.

```bash
export SOMAWEAVE_TOOLUNIVERSE_PYTHON=$HOME/.conda/envs/tooluniverse/bin/python
export SOMAWEAVE_RESULTS_ROOT=E/T1/results
export SOMAWEAVE_CACHE_ROOT=E/T1/cache_cold
export SOMAWEAVE_REFERENCE_ROOT=/global/scratch/hpc6049/somaweave_dev/reference
export PYTHONPATH=E/source_6269ffc/src
export SOMAWEAVE_INTERPRET_ARGS='--run-id tu-compute-cold-1'
sbatch --account=def-hpcg6049_cpu --time=00:20:00 --mem=2G --cpus-per-task=1 \
  --export=ALL --chdir=E/T1 --output=E/T1/slurm-%j.out \
  E/source_6269ffc/hpc/slurm/interpret_case.sbatch \
  E/source_6269ffc/examples/synthetic_case.json
```

E denotes the literal private root above; actual expanded arguments are in
the submission/log records. Both manifest and source queries bind source6269ffc.
`evidence/source_queries.json` contains two ToolUniverse gene-tier queries:
**ok1 / no_records1 / unavailable0 / error0**. Both carry
`source_version="tooluniverse 1.5.7; ClinicalTrials.gov API v2"`, confirming
the bridge handshake reached the provider. First query duration is **5,912ms**,
including catalogue startup and registry request as measured by the provider;
the subsequent query took286ms. No unavailable message exists to quote.

One trial record was returned on the synthetic case; its category is `trial`,
`is_hypothesis=true`, and its evidence ID is absent from `accepted_ids`.
No axis is cleared or promoted by that record. Native query, timing and
version evidence: E/T1/results/tu-compute-cold-1/evidence/source_queries.json;
summary: E/T1/summary.json. Existing conda entry-point warnings appeared during
activation, but the selected engine interpreter, bridge and run completed;
the verbatim diagnostics remain in the job log. No package fix was attempted.

The full unit, structure and schema gates pass before each evaluation-document
commit; per-commit commands and exit codes are retained in E/validation/.

## T2 — unchanged private inputs with trial retrieval enabled

All three case-v2 input SHA-256 values equal the eval-5 manifests. Each new
manifest records the same executed source6269ffc. Results are named
`<private-case>-eval-6-trials` under E/T2/results; study identifiers and payloads
remain external. No case fields or query terms were adjusted to obtain matches.

Non-ToolUniverse provider payloads were snapshotted into E/T2/cache using hard
links in new provider directories: civic231, clinvar81, europepmc380,
gnomad95 and oncokb96 cache files. The ToolUniverse subdirectory initially did
not exist. The shared original
cache was not purged. No previous SomaWeave ToolUniverse provider response was
reused. Available pre-existing source evidence was reused rather
than refreshed to manufacture label agreement.

Submission used the same pinned `hpc/slurm/interpret_case.sbatch` template and
bridge/reference/PYTHONPATH settings as T1, with:

```bash
export SOMAWEAVE_RESULTS_ROOT=E/T2/results
export SOMAWEAVE_CACHE_ROOT=E/T2/cache
export SOMAWEAVE_INTERPRET_ARGS='--run-id <private-case>-eval-6-trials'
sbatch --account=def-hpcg6049_cpu --time=00:45:00 --mem=2G --cpus-per-task=1 \
  --export=ALL --chdir=E/T2 --output=E/T2/<neutral-label>-%j.out \
  E/source_6269ffc/hpc/slurm/interpret_case.sbatch <unchanged-private-case.json>
```

The literal commands, environment overrides, sbatch exit codes and IDs are in
E/T2/submissions.json. All jobs ran on frnt152 and completed0:0. Scheduler
wall times were53s/73s/45s for case-A/B/C respectively; first ToolUniverse query
durations were19,350ms/19,291ms/19,375ms. Every trial query records
`tooluniverse 1.5.7; ClinicalTrials.gov API v2`.

| Case | Findings / ToolUniverse gene queries | ok | no_records | unavailable / error / other | Trial records | Findings with trials | Four-axis label changes vs eval-5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| case-A | 35 | 0 | 35 | 0 | 0 | 0 | 0 / 140 labels |
| case-B | 52 | 0 | 52 | 0 | 0 | 0 | 0 / 208 labels |
| case-C | 28 | 0 | 28 | 0 | 0 | 0 | 0 / 112 labels |

**All four axes are identical for all115 findings:460 label comparisons,
zero differences.** The same identity also holds against the final
population-enriched eval-5 replay. No defect fix or interpretation-rule change
was made. A successful empty registry search is not missing/failed evidence
and is not evidence that no suitable clinical trial exists.

### Plausibility and hypothesis handling

| Case | Plausible diagnosis/parent match | Disease mismatch | Uninformative basket-only match |
|---|---:|---:|---:|
| case-A | 0 | 0 | 0 |
| case-B | 0 | 0 | 0 |
| case-C | 0 | 0 | 0 |

There are no returned trial records to assess; these zeros do **not** establish
match specificity or exclude false-positive matches in future cases. External
per-case review, including the empty record lists, is
E/T2/plausibility_review.json; aggregate counts/diffs are E/T2/aggregate.json.

For the case with the histology hypothesis, all35 recorded native requests use
exactly the recorded `diagnosis.name` as the ClinicalTrials condition argument.
No hypothesis term is merged into that primary condition. Hypotheses remain
separate planner metadata; they do not appear in the outgoing tool arguments.
The other two cases likewise use their recorded diagnosis names for all80
requests. Actual condition strings/native requests stay in the private review.
No synonym/parent expansion or molecular-hypothesis substitution was introduced.

### Reviewer wording assessment — suggestions only

The separate heading **Clinical trials (registry search; context only)** and
the positive-record statement that eligibility was not evaluated and no tier
is derived are clear. The synthetic T1 match exercises that positive view.
Two limitations remain in the current presentation:

- The real-case subsections display only `none retrieved`, omitting the
  explanatory limitation used when matches exist. Suggested empty-search text:
  **“No registry records were returned for the submitted gene and diagnosis
  text. This does not establish that no suitable trials exist; eligibility
  and biomarker requirements were not assessed.”**
- `Registry matches on gene symbol and recorded diagnosis only` can sound like
  a confirmed biomarker/disease match. Suggested positive-view wording:
  **“These records were returned by a registry free-text search using the gene
  symbol and recorded diagnosis. The gene may occur anywhere in the registry
  text; required alterations, condition applicability and eligibility were not
  assessed. No actionability tier is assigned from these records.”**

The code also renders `none retrieved` when a queried provider is unavailable;
although the coverage table preserves its unavailable status, that wording
could be mistaken for a completed negative search. Suggested separate text:
**“Registry search unavailable; trial availability was not assessed. See source
coverage for the reason.”** This failure presentation was identified by source
inspection, not observed in T1/T2 (unavailable0). These are QC suggestions only;
no report or engine rule was edited.

## T3 — localhost MCP discovery and calls

Executed on login1.frontenac.local using the isolated ToolUniverse interpreter;
installed versions are ToolUniverse1.5.7 and mcp1.30.0. The engine remains in
the SomaWeave interpreter, with PYTHONPATH selecting pinned source6269ffc.
The client drops the inherited cluster PYTHONPATH/PYTHONHOME before import;
no environment package or persistent setting was changed.

```bash
export SOMAWEAVE_PYTHON=$HOME/.conda/envs/somaweave/bin/python
export SOMAWEAVE_RESULTS_ROOT=E/T3/results
export PYTHONPATH=E/source_6269ffc/src
$HOME/.conda/envs/tooluniverse/bin/python \
  E/source_6269ffc/src/somaweave/serve/mcp_server.py --list-tools
$HOME/.conda/envs/tooluniverse/bin/python \
  E/source_6269ffc/src/somaweave/serve/mcp_server.py \
  --transport streamable-http --port 43949
```

`--list-tools` exited0 and listed exactly:
`somaweave_validate_case`, `somaweave_build_case`,
`somaweave_interpret_case`, `somaweave_list_runs`, `somaweave_get_run`,
`somaweave_get_report`. HTTP bind stayed at its default **127.0.0.1**.
The successful client sequence was:

```python
from tooluniverse import ToolUniverse
from tooluniverse.tool_registry import get_tool_class_lazy

get_tool_class_lazy("MCPAutoLoaderTool")
tu = ToolUniverse()
tu.load_tools()
tu.load_mcp_tools(["http://127.0.0.1:43949/mcp"])

tu.run({
    "name": "mcp_loader_http_127.0.0.1_43949_mcp",
    "arguments": {
        "operation": "call_tool",
        "tool_name": "somaweave_validate_case",
        "tool_arguments": {
            "case_path": "/global/scratch/hpc6049/somaweave_dev/evaluation/tooluniverse/source_6269ffc/examples/synthetic_case.json"
        }
    }
})
tu.run({
    "name": "mcp_loader_http_127.0.0.1_43949_mcp",
    "arguments": {
        "operation": "call_tool",
        "tool_name": "somaweave_interpret_case",
        "tool_arguments": {
            "case_path": "/global/scratch/hpc6049/somaweave_dev/evaluation/tooluniverse/source_6269ffc/examples/synthetic_case.json",
            "run_id": "tu-mcp-offline-1",
            "offline": True
        }
    }
})
```

Discovery returned `total_tools=6`, `servers_connected=1`, no errors and no
discovery_error. Both calls returned `isError=false`; the JSON decoded from
`content[0].text` has `ok=true`, `exit_code=0` and empty stderr. The native MCP
envelope's keys are `meta`, `content`, `structuredContent`, `isError`;
`structuredContent` is null, so clients must decode the text JSON here.

| Call | Decoded returned keys |
|---|---|
| somaweave_validate_case | ok, exit_code, stdout, stderr, command, summary |
| somaweave_interpret_case | ok, exit_code, stdout, stderr, command, run_id, run_dir, case_id, offline, somaweave_version, git_commit, source_status_counts, findings, outputs |

The offline interpretation produced a manifest/report with two synthetic
findings, `offline=true`, executed commit6269ffc and26 `not_queried` source
statuses. No real case was exposed through MCP. Actual calls, complete returned
values and commands are in E/T3/mcp_calls.json; server/client diagnostics are
in E/T3/server.log and client.log. The harness exited0. The server was then
intentionally terminated (SIGTERM, process return-15); a loopback socket probe
confirmed no listener remained. E/T3/teardown.json records that check.

### Open SDK startup issue

The bare `ToolUniverse().load_mcp_tools(...)` attempt returned zero tools with
verbatim `discovery_error: "'MCPAutoLoaderTool'"`. Adding only `tu.load_tools()`
still returned the same failure. In both cases the SDK reported success/one
connected server despite discovering zero tools; that is not accepted as a
successful test. Preserved attempts: E/T3/attempt1 and attempt2.

Inspection of installed ToolUniverse1.5.7 `mcp_integration.py` shows its loader
directly indexes `tool_type_mappings["MCPAutoLoaderTool"]`, while the default
SDK registry is lazy. Explicitly invoking the existing SDK function
`get_tool_class_lazy("MCPAutoLoaderTool")` before discovery resolves this in
the client process. No monkey patch, source edit, reinstall, upgrade or engine
fix was made. T3 therefore passes **with that explicit class-preload step**;
the bare documented convenience call is not reproducible on this side.
Suggested follow-up: document the required SDK initialization or have the
upstream loader resolve its class through the lazy registry. Any code fix is
outside this test-only work order.

## T4 — unit and repository gates

On login1.frontenac.local, from the pinned source worktree:

```bash
$HOME/.conda/envs/somaweave/bin/python -m unittest discover -s tests
PYTHONPATH=src $HOME/.conda/envs/tooluniverse/bin/python \
  -m unittest tests.test_serve_mcp.ServerRegistrationTests
```

Both exit0. Full suite: **387 tests in11.066s, OK(skipped=1)**. The skipped
test is MCP registration because `mcp` is absent from the SomaWeave environment;
that same registration test passes separately in the ToolUniverse environment
(one test in1.687s). Nothing was installed into either environment.
Exact commands, environment selection and outputs: E/T4/commands.json,
unit.txt and registration.txt.

Before every T1–T4 document commit, the current main checkout also passes:

```bash
$HOME/.conda/envs/somaweave/bin/python -m unittest discover -s tests
$HOME/.conda/envs/somaweave/bin/python scripts/check_structure.py
$HOME/.conda/envs/somaweave/bin/python scripts/export_schemas.py --check
```

Each command exits0; full-suite count remains387 with the expected one skip.
Per-item outputs/argv/exit codes are in E/validation/T1 through T4. The final
external E/completion.json binds each document commit, runtime manifests,
input/source hashes and test outputs. No commit embeds its own hash here.

## Open issues and limits

1. Bare SDK MCP discovery failed with `'MCPAutoLoaderTool'`; the explicit lazy
   class preload succeeds. This is recorded, not patched or hidden by a claimed
   default-call pass. All listeners were restricted to localhost and stopped.
2. Zero real-case search results leave disease-match plausibility/specificity
   unmeasured. Exact recorded-diagnosis wording was preserved; no broader query
   was substituted. The four-axis identity test passed for all115 findings.
3. Empty/unavailable registry wording needs the reviewer clarifications proposed
   above. No report-rule/prose change is authorized or made by this evaluation.

Only this QC handoff is changed by the evaluation commits. Real clinical inputs,
search terms, native payloads and per-finding comparisons remain outside Git.
