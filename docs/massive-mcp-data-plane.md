# Massive MCP data plane

Massive MCP is the authoritative external source plane. Repository code owns durable materialization, normalization, calculation, sealing, and state transitions.

## Operational sequence

### 0. Native Windows bootstrap before acquisition

Before spending MCP calls, create a stable `run_id` (for example `2026-09-28-eod`) and a unique immutable `attempt_id` (for example `2026-09-28-eod-attempt-20260929T120000Z`). On Windows, do **not** begin by invoking `python` directly. Run the native bootstrap first:

```powershell
$Attempt = "2026-09-28-eod-attempt-20260929T120000Z"
$Runtime = "research\runs\$Attempt.python-runtime.json"

powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\control_plane\bootstrap.ps1 `
  -RunId 2026-09-28-eod `
  -AttemptId $Attempt `
  -ResearchCutoff 2026-09-28T23:59:59Z `
  -RuntimeOut $Runtime
```

The bootstrap itself does not require Python. It checks the required static files, writable research directories, request policy, source identity, Git availability, and prior attempts, and it **always writes** an attempt-scoped bootstrap artifact. It then probes for Python 3.11+ using `py -3`, direct CPython installation paths, PATH commands, and finally `uv python find >=3.11` with automatic downloads disabled. Astral documents `uv python find` as interpreter discovery and `--no-python-downloads` as the switch that prevents automatic Python downloads; the control plane uses uv only as a locator here, never as permission to mutate the machine.

If an existing uv-managed interpreter is found, subsequent repository scripts execute the returned interpreter path directly, bypassing a broken PATH `python.exe` shim/trampoline. If no working interpreter can be executed, bootstrap returns `BLOCKED`, persists the evidence, and the workflow stops before any Massive provider call. It never installs or repairs Python automatically.

When bootstrap is `READY`, bind the attempt to that runtime descriptor and route all Python scripts through the wrapper:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\control_plane\run_python.ps1 `
  -RuntimeFile $Runtime `
  .\scripts\control_plane\preflight.py `
  --run-id 2026-09-28-eod `
  --attempt-id $Attempt `
  --research-cutoff 2026-09-28T23:59:59Z `
  --out "research\runs\$Attempt.preflight.json"

powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\control_plane\run_python.ps1 `
  -RuntimeFile $Runtime `
  .\scripts\control_plane\discover_run.py 2026-09-28-eod
```

Never overwrite a prior terminal attempt. Git availability is informative rather than a market-data gate.

Initialize the attempt-scoped provider-call ledger through the **same bound runtime** before the first authenticated data probe:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\control_plane\run_python.ps1 `
  -RuntimeFile $Runtime `
  .\scripts\control_plane\massive_request_gate.py init `
  --run-id 2026-09-28-eod `
  --attempt-id $Attempt `
  --ledger "research\runs\$Attempt.massive-request-ledger.json"
```

`config/massive-request-policy.json` currently governs provider-facing Massive MCP `call_api` operations at five starts per rolling 60 seconds with at least 12 seconds between permits. The repository does not treat model pacing judgment as sufficient evidence.

### 1. Probe effective access before large acquisition

Before any multi-request phase, calculate its minimum pacing budget:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\control_plane\run_python.ps1 -RuntimeFile $Runtime .\scripts\control_plane\massive_request_gate.py plan --request-count 25
```

For every provider-facing `call_api`, run `permit` before the tool call and `complete` immediately after it. The gate refuses a new permit while the previous provider call is incomplete, so the queue is serial rather than merely time-spaced. Every paginated `call_api` page, including `next_url` follow-ups, consumes its own permit. `search_endpoints`, `workspace`, and `query_data` are MCP control/local-workspace operations and are not counted as provider requests by the current policy.

The ledger snapshots its policy at attempt creation. If the user later tightens the provider-rate constraint below that snapshot, stop the attempt and initialize a new attempt under the tighter policy; never rewrite the old ledger or reinterpret earlier calls as compliant.

For every capability in `config/daily-capabilities.json`, record three independent facts:

1. `discovery_status`: can Massive MCP describe the endpoint now?
2. `basic_snapshot_status`: did the dated Basic snapshot mark the capability included?
3. `access_status`: did a bounded authenticated MCP call actually succeed?

Write an attempt-scoped capability probe report and evaluate it with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\control_plane\run_python.ps1 `
  -RuntimeFile $Runtime `
  .\scripts\control_plane\evaluate_capabilities.py `
  research\runs\<attempt>.capability-probes.json `
  --out research\runs\<attempt>.capability-evaluation.json
```

Severity is explicit:

- `CORE`: unresolved/denied access blocks.
- `ENRICHMENT`: denial degrades coverage but does not kill a valid crypto-core run.
- `EVENT_OPTIONAL`: denial/absence is recorded and skipped unless a registered design explicitly requires it.

A provider denial always wins over a static entitlement snapshot. Never bypass it.

If any provider call returns a `RATE_LIMIT` warning, record it as `RATE_LIMIT`. The gate marks the ledger `TAINTED`, refuses additional permits, and requires a fresh attempt. A later successful retry cannot retroactively make the tainted attempt compliant.

### 2. Two-phase core acquisition

The daily model uses a bounded two-phase crypto acquisition:

1. materialize the point-in-time universe and cutoff-day grouped crypto cross-section;
2. deterministically select the configured liquid USD universe from that fixed cross-section, then acquire the configured historical lookback for those selected assets plus BTC/ETH.

This avoids both a 120-day full-market grouped crawl and a survivorship-biased current-ticker backtest.

Current defaults are in `config/daily-model.json`: top 25 liquid USD pairs, 120 calendar days requested, and at least 60 observations required for deterministic features.

### 3. Durable MCP materialization protocol

`call_api(..., store_as=...)` and a Massive workspace are staging only. They are never sufficient evidence by themselves.

For every staged table:

1. use `query_data(action="describe")` or `show_tables` to record schema and exact staged row count;
2. choose stable ordering/key fields (`ticker,timestamp`, or the closest endpoint-specific equivalent);
3. export bounded ordered slices with `query_data`, normally 100-200 rows per call;
4. capture each slice exactly as CSV, JSON, or JSONL under an attempt-scoped staging directory;
5. run `scripts/control_plane/materialize_mcp_dataset.py` over all chunks with the expected row count, stable sort fields, and unique key fields;
6. reject truncation markers, malformed chunks, duplicate keys, and row-count mismatches;
7. persist canonical immutable JSONL plus a sidecar metadata file containing the local SHA-256 digest.

Example:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\control_plane\run_python.ps1 `
  -RuntimeFile $Runtime `
  .\scripts\control_plane\materialize_mcp_dataset.py `
  research\staging\<attempt>\crypto-cutoff\chunk-*.csv `
  --dataset-id crypto_grouped_cutoff `
  --run-id 2026-09-28-eod `
  --attempt-id <attempt> `
  --market Crypto `
  --endpoint-path /v2/aggs/grouped/locale/global/market/crypto/2026-09-28 `
  --params-json '{"adjusted":true}' `
  --requirement CORE `
  --research-cutoff 2026-09-28T23:59:59Z `
  --retrieved-at <exact-client-captured-UTC-time> `
  --as-of 2026-09-28 `
  --expected-rows <workspace-row-count> `
  --sort-fields T,t_2 `
  --key-fields T,t_2
```

For custom-bar history fetched one ticker at a time, make each `query_data` slice add the literal ticker as a `ticker` column and combine all slices into one `crypto_history` materialization. The deterministic pipeline expects `ticker` plus OHLC/VWAP/volume/timestamp fields.

### 4. Provenance timing

The provider-call ledger is the canonical client-side request receipt. It binds the endpoint and parameter digest to a serialized permit time and completion record and retains the outcome, warning, returned row count, pagination state, and request ID when Massive exposes one. Do not manually estimate a minute-level time and label it exact. Missing provider request IDs remain a limitation, not permission to invent them.

### 5. Seal only after durable evidence exists

The acquisition manifest may be:

- `COMPLETE`: all core and attempted required enrichments are verified/materialized;
- `DEGRADED`: every core dataset is verified/materialized, but one or more enrichment families are unavailable/incomplete and explicitly recorded;
- `PARTIAL`: in-progress/incomplete; not eligible for downstream analysis;
- `BLOCKED`: a core requirement failed.

For `COMPLETE` or `DEGRADED`, every `CORE` dataset must have successful authenticated access, complete pagination, non-approximate retrieval time, exact local row-count agreement, immutable materialization path, and SHA-256 digest.

After the last provider call and before methodology review, audit and seal the ledger:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\control_plane\run_python.ps1 `
  -RuntimeFile $Runtime `
  .\scripts\control_plane\massive_request_gate.py audit `
  --ledger research\runs\<attempt>.massive-request-ledger.json `
  --seal
```

The audit fails on any interval/window violation, incomplete provider request, or observed rate-limit response. Only a sealed PASS ledger is forecast-eligible.

### 6. Deterministic daily pipeline

After the independent data-steward returns PASS or an explicitly acceptable DEGRADED result, run `scripts/pipeline/run_daily_pipeline.py`. It consumes only verified materialized datasets and produces inspectable feature-store, market-state, factor, residual/relative-value, macro-coverage, ensemble, risk, and forecast-payload artifacts.

The pipeline refuses a BLOCK data-quality result, a BLOCKED capability evaluation, digest/row-count mismatches, insufficient history coverage, or missing BTC/ETH anchors.

## No-bypass rule

Do not use direct REST/HTTP clients, curl, requests/httpx, Massive/Polygon SDKs, copied API keys, web search, or alternate providers as substitutes for a denied Massive capability. Degrade or block according to the declared capability class.


## Windows runtime bootstrap hardening

On Windows, provider acquisition is downstream of a Python-independent PowerShell bootstrap. Repository paths resolve from the active project root, never the installed Skill directory. The resolver records every candidate outcome, checks repo virtualenv/Windows registry/common installs/uv/PATH, rebinds launchers to the actual interpreter executable, and may provision only a repository-local CPython under `.runtime/python` via uv. No system PATH mutation or global Python installation is permitted. Massive calls remain forbidden until Python >=3.11 executes successfully and the runtime descriptor is persisted.
