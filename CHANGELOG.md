## 0.3.4

- Fix installed-Skill path assumptions: project files are now resolved from the active project root, never by `../../../` traversal from a globally installed Skill. The daily Skill carries a synchronized `references/daily-goal.md` fallback.
- Harden Windows Python discovery across repo virtualenvs, versioned `py` launchers, Python registry installs, common distributions, recursive uv-managed installs, and all PATH/`where.exe` candidates.
- Rebind every successful launcher/shim to the actual `sys.executable` before governed execution.
- Add bounded self-healing: if no interpreter works and uv is available, provision CPython 3.12 only under `.runtime/python` with no system PATH/global installation.
- Persist candidate/provisioning diagnostics and add `python_runtime.schema.json`.
- Keep the pre-acquisition invariant: zero Massive provider calls until a Python >=3.11 executable is proven READY.

# Changelog

## 0.3.3 - 2026-09-29

- moved the Windows pre-acquisition bootstrap out of Python: `bootstrap.ps1` can now record attempt identity, static readiness, writable paths, source identity, prior attempts, Git availability, and runtime status even when `python.exe` is broken;
- hardened `run_python.ps1` to resolve Python 3.11+ via `py -3`, direct CPython install paths, PATH commands, and `uv python find >=3.11` with `--no-python-downloads --offline`, then execute the resolved interpreter directly instead of trusting a failing uv/PATH trampoline;
- added attempt-bound runtime descriptors and required Windows workflow stages to keep using that resolved runtime rather than reverting to bare `python`;
- added `config/python-runtime-policy.json` with explicit no-auto-install policy and `schemas/windows_bootstrap.schema.json` for durable bootstrap evidence;
- updated daily workflow/skills/architecture/docs/evals so runtime failure is recorded before acquisition and an existing uv-managed interpreter can be recovered without mutating the machine;
- added regression coverage for the bootstrap/runtime policy surface and kept provider request gating, deterministic materialization, and forecast-freeze invariants unchanged.

## 0.3.2 — 2026-09-29

Second qualification-hardening release driven by the live provider-rate compliance failure.

- added `config/massive-request-policy.json` with an executable default budget of five provider-facing Massive `call_api` starts per rolling 60 seconds and a 12-second minimum interval;
- added `massive_request_gate.py` with plan/init/permit/complete/audit+seal commands, cross-process ledger locking, strict serial completion, rolling-window validation, immutable policy binding, and tamper-detecting sealed-ledger digests;
- made any `RATE_LIMIT` warning taint the current attempt, halt further permits, and require a fresh attempt rather than allowing successful retries to erase process noncompliance;
- added `massive_request_ledger.schema.json` and strengthened Massive provenance with endpoint/parameter digests, client-captured permit/completion times, warning/outcome, returned row count, provider request ID when exposed, and pagination evidence;
- changed forecast freezing to independently require a sealed compliant request ledger plus a PASS methodology audit bound to the same attempt;
- updated the daily workflow, Massive data-plane skill, methodology auditor, and AGENTS guidance so all provider probes/pages/history calls traverse the gate while `search_endpoints`, `workspace`, and local `query_data` remain outside the provider-call budget;
- defined mid-attempt rate tightening as a new-attempt boundary so prior calls are never retroactively relabeled compliant;
- fixed the deterministic-pipeline test fixture to hash canonical UTF-8/LF bytes, removing the Windows CRLF-only digest mismatch seen in the qualification run;
- added source-tree identity fallback when Git is unavailable and expanded preflight/control-plane validation for the pacing policy and request gate;
- added focused regression tests for 25-call pacing, serial permits, rate-limit tainting, sealed-ledger validation, and forecast refusal on tainted acquisition evidence.

## 0.3.0 — Massive MCP data-plane correction

- **MCP-001 — Make Massive MCP the mandatory source-data plane.** Added the project-scoped `mcp_servers.massive` configuration using the official `https://mcp.massive.com/` streamable-HTTP endpoint. Repository instructions now prohibit silent direct REST/SDK/API-key/web fallbacks for Massive-backed workflows.
- **MCP-002 — Add a dedicated acquisition support skill.** Added `$massive-mcp-data-plane` with an OpenAI MCP dependency declaration, current endpoint discovery -> API call -> pagination -> workspace/SQL -> cutoff -> sealed-manifest workflow.
- **MCP-003 — Separate entitlement from discoverability.** Reframed `$massive-basic-endpoints` as a dated Basic entitlement/capability guard. The package now explicitly rejects the assumption that an endpoint found by Massive MCP is necessarily included in Basic.
- **MCP-004 — Fix daily ordering.** Massive acquisition and source freezing now precede `data-steward`; `data-steward` remains the first specialist reviewer. Analytical subagents consume the fixed run instead of independently refetching broad market data.
- **MCP-005 — Add durable acquisition provenance.** Added `massive_acquisition_manifest.schema.json`, `seal_acquisition.py`, an example manifest, immutable acquisition storage, and tests. `COMPLETE` acquisition records require Basic inclusion, current-doc verification, complete pagination, and complete dataset status.
- **MCP-006 — Extend research/OOS/audit semantics.** Factor research fixes its data snapshot before exploration; OOS realized data uses Massive MCP provenance; methodology/statistical review now checks acquisition identity, cutoff, entitlement, pagination, and refetch contamination.
- **MCP-007 — Harden package validation.** Validator now covers all seven skills (five workflow + two support), verifies the Massive config and skill dependency, checks nine schemas, and rejects Python direct-network/API-key bypass patterns.
- **MCP-008 — Expand failure evaluation.** Added explicit cases for missing/unauthenticated Massive MCP and discoverable-but-not-Basic crypto routes.
- **MCP-009 — Documentation correction.** Updated README, architecture, data boundary, sources, and `/goal` prompts around the actual Massive MCP operating model and host-managed OAuth.

## 0.2.1 — control-plane optimization

- **F-001 — Remove a false role-level sandbox signal.** Removed `sandbox_mode = "read-only"` from all nine custom role files. Exact Codex 0.157.1 and 0.158.0 role-override code does not project `sandbox_mode` into the child role configuration. Added explicit no-mutation developer instructions and documented that hard filesystem/tool authority remains a parent/session runtime concern.
- **F-002 — Make validation match the real permission boundary.** Updated `scripts/control_plane/validate_control_plane.py` to reject reintroduction of role-local `sandbox_mode` instead of falsely treating it as enforced read-only isolation.
- **F-003 — Restore the valid V1 recursion control.** The original validator rejected `agents.max_depth` as obsolete even though Codex 0.157.1 exposes it for V1 agent nesting. Added `max_depth = 1` to `.codex/config.toml`, matching the package rule against recursive child spawning, and changed validation to require that value. V2 does not use this setting, so the behavioral root rule remains necessary there.
- **F-004 — Preserve native role auto-discovery.** Exact Codex 0.157.1 source confirms project-layer `.codex/agents/*.toml` files are discovered automatically. No redundant `[agents.<role>]` declarations were added.
- **F-005 — Preserve the already-good hot context.** Left `AGENTS.md` and all five skill entrypoints materially unchanged because the measured project instruction chain is only 2,272 bytes, all skill references resolve, and substantive hot-context noise is 0%.
- **F-006 — Improve compatibility provenance.** Added exact Codex role/discovery/config source links to `SOURCES.md` and a cold-memory runtime-role boundary note to `docs/architecture.md`.
- **F-007 — Release metadata.** Bumped `VERSION` to `0.2.1` and regenerated `CONTROL_PLANE_MANIFEST.json` from file bytes without executing package scripts.

No model, approval, sandbox, credential, brokerage, or arbitrary external-write setting was made more permissive.

## 0.3.1 - 2026-09-29

Qualification-hardening release driven by the first live daily-run failure evidence.

- added stable run / unique attempt semantics and prior-run discovery; removed seeded date-specific run artifacts from the release package;
- added local execution preflight before MCP acquisition;
- split Massive capability evidence into endpoint discovery, dated Basic snapshot status, and authenticated access;
- added explicit CORE / ENRICHMENT / EVENT_OPTIONAL capability severity and deterministic evaluation;
- changed denied stock/index macro inputs from unconditional blockers to explicit DEGRADED enrichment when crypto core remains valid;
- added durable MCP materialization protocol with bounded chunks, truncation rejection, exact staged/local row-count checks, unique keys, canonical JSONL, SHA-256, and immutability;
- expanded acquisition manifests with attempt identity, access/materialization evidence, retrieval-time source, and COMPLETE/DEGRADED semantics;
- added a repository-owned deterministic daily pipeline for feature store, crypto market state, multi-factor ranking, BTC/ETH/market residual signal, macro coverage, ensemble, research-only risk sizing, and forecast payload;
- added real artifact schema validation rather than JSON-parse-only checks;
- hardened data-steward, macro, institutional, risk, and methodology roles around missing enrichment vs missing core;
- added failure evals for entitlement degradation, transient/truncated MCP staging, and missing deterministic runtime stages;
- package validation now rejects seeded runtime research artifacts and validates the capability/model configuration.
