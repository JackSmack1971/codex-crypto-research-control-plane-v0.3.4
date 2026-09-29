---
name: massive-mcp-data-plane
description: Acquire and stage Massive-backed research data through the configured Massive MCP server with Basic-plan entitlement checks, current endpoint verification, pagination, workspace reuse, cutoff discipline, and a sealed acquisition manifest. Use inside governed daily, factor-research, or OOS workflows; do not bypass Massive MCP with direct HTTP/API clients.
---

**Repository path contract:** paths such as `config/...`, `scripts/...`, `docs/...`, `schemas/...`, `research/...`, and `workflows/...` are relative to the active project root (the directory containing `AGENTS.md` and `.codex/config.toml`), **not** relative to this installed Skill directory. Never walk `..` from the Skill installation to find project files. If no matching project root is active, do not invent one.

# Massive MCP data plane

Use this support skill whenever a governed workflow needs Massive source data. Read `docs/massive-mcp-data-plane.md` and `docs/data-capability-boundary.md` before acquisition.

## Required sequence

1. Run the local preflight before market acquisition. Confirm the deterministic pipeline/materializer/validators and request gate exist and can execute. Create a unique attempt ID; never overwrite a previous attempt. Initialize one request ledger from `config/massive-request-policy.json` before the first provider-facing `call_api`.
2. Read `config/daily-capabilities.json`. For every applicable capability, keep endpoint discovery, dated Basic-snapshot status, and actual authenticated access as separate evidence. Use bounded authenticated probes before large acquisitions.
3. Apply severity exactly: CORE denial/unresolved access blocks; ENRICHMENT denial degrades; EVENT_OPTIONAL denial/absence is recorded without blocking unless the active registered design explicitly requires it.
4. Use Massive MCP `search_endpoints` for current route/parameter verification and `call_api` for actual retrieval. On Windows, invoke request-gate/materialization Python scripts through the attempt-bound `scripts/control_plane/run_python.ps1` with `-RuntimeFile <runtime.json>` resolved by native bootstrap; never rely on a bare `python` shim after bootstrap. Before **every** `call_api`, obtain a permit from `scripts/control_plane/massive_request_gate.py`; complete that ledger entry immediately after the tool returns. The gate serializes provider starts and enforces the rolling cap. `search_endpoints`, `workspace`, and `query_data` are MCP control/local operations and are outside this provider-call budget. Do not treat endpoint discovery as entitlement proof. Follow pagination completely; every provider page retrieved through `call_api`, including a `next_url` follow-up, requires its own permit/completion ledger entry.
5. Prefer one Massive workspace for staging. Staged tables are transient and **must not** be treated as durable run evidence.
6. Materialize every used dataset with `scripts/control_plane/materialize_mcp_dataset.py`: inspect staged row count/schema, export stable ordered 100-200 row `query_data` slices, reject truncation, verify unique keys and exact local/staged row-count agreement, and persist canonical immutable JSONL + SHA-256 sidecar metadata.
7. For custom-bar history fetched per ticker, make the deterministic `query_data` projection add the literal ticker as a `ticker` column before combining chunks.
8. The request ledger is the canonical client-side provider-call receipt. Record endpoint/parameter digest, permit time, completion time, warning/outcome, returned row count, provider request ID when exposed, and pagination terminal/next-link state. Never invent request IDs. A `RATE_LIMIT` warning immediately marks the attempt TAINTED; stop acquisition and require a new attempt rather than retrying within the tainted one. If the user tightens the provider-rate constraint after an attempt has begun, stop the attempt and initialize a fresh ledger under the tighter policy rather than retroactively changing the old policy snapshot.
9. Check all as-of timestamps against the research cutoff. Post-cutoff data may verify schema/provenance but cannot enter the fixed run.
10. Seal the acquisition only after materialization. COMPLETE/DEGRADED require every CORE dataset to have successful authenticated access, complete pagination, verified local materialization, matching row count, and digest. PARTIAL is in-progress and not downstream-eligible. Before methodology audit/freeze, run `massive_request_gate.py audit --seal`; only a sealed PASS ledger is eligible for forecast freeze.

## Completion boundary

The source plane is complete when the capability evaluation exists, every CORE dataset is durably materialized and verified, the acquisition is sealed COMPLETE or DEGRADED, the provider-call ledger seals PASS, and any missing enrichment is explicit. Never bypass Massive MCP with direct HTTP/API clients, SDKs, copied API keys, web search, or another provider.
