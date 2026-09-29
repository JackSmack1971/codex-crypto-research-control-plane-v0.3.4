---
name: daily-research-run
description: Run one governed end-of-day research cycle through Massive MCP acquisition, data-quality gate, deterministic analytics, independent review, and immutable forecast. Use for a full daily run or forecast freeze; do not use for standalone factor R&D or matured-forecast scorekeeping.
---

**Repository path contract:** paths such as `config/...`, `scripts/...`, `docs/...`, `schemas/...`, `research/...`, and `workflows/...` are relative to the active project root (the directory containing `AGENTS.md` and `.codex/config.toml`), **not** relative to this installed Skill directory. Never walk `..` from the Skill installation to find project files. If no matching project root is active, do not invent one.

# Daily research run

Read the active project-root `workflows/daily-goal.md`, `docs/massive-mcp-data-plane.md`, and `docs/data-capability-boundary.md`. The packaged `references/daily-goal.md` is a synchronized fallback for reading the workflow when the Skill is installed outside the repository; it is not a substitute for an active project root when executing repository scripts.

## Workflow

1. Create one stable daily `run_id` and a new immutable `attempt_id`. On Windows, run native `scripts/control_plane/bootstrap.ps1` **before any bare Python command**. It must resolve and persist a working Python 3.11+ runtime (including direct uv-managed interpreter discovery when the PATH `python.exe` shim is broken) or write a durable BLOCKED bootstrap record and stop before MCP. When READY, use `run_python.ps1 -RuntimeFile <attempt-runtime.json>` for `preflight.py`, `discover_run.py`, request-gate commands, materialization, validation, pipeline, and forecast-freeze scripts. Never switch back to bare `python` within that attempt. Initialize the attempt-scoped Massive request ledger with `massive_request_gate.py init`; a non-Git snapshot is a verification limitation, not a market-data blocker.
2. Read `config/daily-capabilities.json`. Through `$massive-mcp-data-plane`, record discovery, dated Basic snapshot status, and actual authenticated access separately. Every provider-facing Massive `call_api` requires a request-gate permit and completion record. Run `evaluate_capabilities.py`. CORE failures block; ENRICHMENT failures degrade; EVENT_OPTIONAL failures are recorded/skipped unless explicitly required.
3. Acquire the fixed source set through Massive MCP and **durably materialize** every used dataset with `materialize_mcp_dataset.py`. Before multi-call phases, use the request gate's `plan` command; provider calls must remain serial and paced by permits. A `RATE_LIMIT` warning taints the attempt and requires a fresh attempt; do not retry to rehabilitate the same attempt. A transient MCP workspace is not evidence. Use exact staged row counts, bounded ordered `query_data` chunks, stable keys, canonical JSONL, and local SHA-256 verification. Seal only after durable materialization; `PARTIAL` is not downstream-eligible.
4. Run `data-steward` against the sealed acquisition, capability evaluation, and materialized data/metadata. CORE materialization/access/cutoff failures block. Missing ENRICHMENT normally yields explicit DEGRADED coverage. Validate the handoff and data-quality JSON against their schemas with `validate_artifact.py`.
5. If the gate permits continuation, run `scripts/pipeline/run_daily_pipeline.py`. The deterministic pipeline owns feature store, market state, factor ranks, residual/relative-value computation, macro-coverage summary, ensemble, research-only risk sizing, and forecast payload. Validate `pipeline-result.json` against `daily_pipeline_result.schema.json`.
6. Run `crypto-internals`, `relative-value`, `macro-regime`, and `institutional-intelligence` in parallel over the fixed deterministic artifacts. Missing enrichment is evidence of reduced coverage, not permission to invent a neutral signal. Validate all handoffs.
7. Reconcile those handoffs against deterministic outputs, then run `portfolio-risk`. Audit and seal the Massive request ledger with `massive_request_gate.py audit --seal`, then run a fresh `$methodology-audit` bound to the same `attempt_id`. A denied ENRICHMENT is acceptable only when explicitly degraded and no conclusion relies on the missing family.
8. If all mandatory gates permit it, freeze the pipeline-produced forecast payload with `freeze_forecast.py --request-ledger <sealed-ledger> --methodology-audit <PASS-audit>` and verify immutable rewrite rejection. A DEGRADED forecast is allowed only with complete CORE data, acceptable data quality, completed deterministic pipeline, rate-compliant acquisition, and a passing methodology audit.
9. Validate every produced JSON artifact against its declared schema and report exact executed checks.

## Completion

Complete only with a fresh attempt identity, capability evaluation, sealed COMPLETE/DEGRADED acquisition, verified materialized CORE datasets, a sealed PASS Massive request ledger, data-steward artifact, deterministic pipeline artifacts, reconciled agent evidence, methodology audit bound to the same attempt, and an immutable frozen forecast created before its target outcome.
