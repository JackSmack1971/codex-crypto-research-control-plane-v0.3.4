# Codex Crypto Research Control Plane

**Version 0.3.4 — portable Skill paths + repo-local runtime self-healing**

A project-level Codex CLI control plane for an end-of-day systematic crypto research engine built around **Massive MCP as the source-data plane**.

The fixed research chain remains deterministic around the external acquisition boundary:

`Massive MCP acquisition -> point-in-time universe -> feature store -> market state -> factors -> regime -> residual model -> ensemble -> risk -> forecasts -> OOS scorekeeping`

Codex is the research director. Massive MCP provides authenticated endpoint discovery/retrieval and transient workspaces. Named subagents inspect, interpret, validate, and challenge a fixed governed dataset. Python/SQL owns normalization, calculations, persistence, immutability checks, and research-state transitions.

## Massive MCP is required

The project config includes:

```toml
[mcp_servers.massive]
url = "https://mcp.massive.com/"
```

Massive's current Codex integration uses the hosted streamable-HTTP MCP server with host-managed OAuth. No Massive API key belongs in this repository.

Before a governed market-data workflow, confirm Codex can see/authenticate the server:

```powershell
codex mcp list
# only if authentication is not already complete:
codex mcp login massive
```

The workflow must never bypass Massive MCP. Access failure is evaluated by capability severity: crypto CORE failures block; denied cross-asset ENRICHMENT degrades coverage; EVENT_OPTIONAL sources are skipped/recorded unless an active research design explicitly requires them.

Two support skills keep the boundary explicit:

- `$massive-basic-endpoints` — dated 2026-09-28 Basic-plan entitlement/capability snapshot; not live retrieval.
- `$massive-mcp-data-plane` — current endpoint verification, authenticated MCP calls, pagination, workspace/SQL use, cutoff discipline, and immutable acquisition provenance.

Important: the control plane records endpoint discovery, dated Basic-snapshot eligibility, and actual authenticated access separately. Discoverability is not entitlement proof, and a provider `NOT_ENTITLED` response takes precedence over the static snapshot.

## Install into a repository

Copy the contents of this directory into the repository root and review the files before enabling them. The repository must be trusted for project `.codex/config.toml` to load.

Then run validation through the runtime resolver rather than assuming the PATH `python` command is healthy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\control_plane\run_python.ps1 .\scripts\control_plane\validate_control_plane.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\control_plane\run_python.ps1 .\scripts\control_plane\validate_evals.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\control_plane\run_python.ps1 .\scripts\control_plane\run_tests.py
```

For a live daily attempt on Windows, the first executable control is `scripts/control_plane/bootstrap.ps1`, not Python. It performs the minimum pre-acquisition checks and attempt discovery without Python, writes a durable bootstrap record even on failure, and resolves a real Python 3.11+ interpreter. `run_python.ps1` now enumerates repo `.venv`, versioned `py` launchers, the Windows Python registry, common CPython/Conda/Scoop locations, uv-managed installs recursively, all PATH/`where.exe` candidates, and `uv python find`. Any successful launcher is rebound to the actual `sys.executable`. If none works, bootstrap may provision CPython 3.12 only into the repository-local `.runtime/python` directory via uv; it does not alter system PATH or perform a global Python install. Acquisition remains forbidden until the resolved executable proves Python >=3.11.

After bootstrap is READY, every deterministic Python stage is invoked through the attempt-bound runtime descriptor. The daily workflow then initializes the attempt-scoped Massive provider-request ledger, deterministically paces every provider-facing `call_api`, materializes MCP results durably, runs the deterministic pipeline, delegates analytical review, and freezes the forecast only if the mandatory gates permit it.

## Kick off the full daily workflow

The repository owns the orchestration details. The normal Codex kickoff should be declarative rather than restating every stage:

```text
/goal Execute today's complete governed end-of-day crypto research workflow through the strongest valid terminal state. Use the repository control plane exactly, do not stop after planning, and do not ask me to manually orchestrate repository-defined stages.
```

If a research date/cutoff is supplied explicitly, use it instead of `today`. A retry for the same date must create a fresh `attempt_id`; prior attempts remain immutable. The default Massive provider budget is five `call_api` starts per rolling 60 seconds with at least 12 seconds between starts. A `RATE_LIMIT` warning taints the attempt and requires a new attempt; successful retries cannot rehabilitate the tainted one.

For release packaging, remove interpreter/test caches first and run through the resolver:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\control_plane\run_python.ps1 .\scripts\control_plane\validate_control_plane.py --package
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\control_plane\run_python.ps1 .\scripts\control_plane\build_manifest.py --generated-at 2026-09-29
```

Codex CLI 0.157.1 auto-discovers the nine named role files from `.codex/agents/`; the included `.codex/config.toml` caps per-session subagent concurrency, sets the V1 nesting cap to one child level, and declares the Massive MCP URL. It does not itself grant filesystem, credential, brokerage, or arbitrary external-write authority. OAuth remains host-managed. Role no-mutation rules are behavioral constraints, not a sandbox boundary.

## Skill/project path contract

Installed Skills are portable instruction packages, not the repository root. Skill instructions resolve repository paths from the active project root containing `AGENTS.md` and `.codex/config.toml`; they never walk `../../../` from the installed Skill directory. The daily Skill also bundles a synchronized `references/daily-goal.md` reading copy, following OpenAI's supporting-resource pattern.

## Primary workflows

- `workflows/daily-goal.md` — Massive MCP acquisition through immutable daily forecast
- `workflows/research-goal.md` — preregistered factor lifecycle against a fixed dataset
- `.agents/skills/daily-research-run/` — full daily run
- `.agents/skills/factor-research/` — preregistered factor discovery/research
- `.agents/skills/candidate-validation/` — independent statistical validation
- `.agents/skills/methodology-audit/` — final adversarial methodology/acquisition review
- `.agents/skills/oos-scorekeeping/` — matured-forecast outcome scoring
- `.agents/skills/massive-mcp-data-plane/` — support skill for governed MCP acquisition
- `.agents/skills/massive-basic-endpoints/` — support skill for dated Basic entitlement limits

The two Massive skills are support skills. The five research lifecycle skills retain the user-facing routing corpus.

## Agent roster

The primary Codex thread acts as `research-director`. It may explicitly delegate to:

1. `data-steward`
2. `crypto-internals`
3. `relative-value`
4. `macro-regime`
5. `institutional-intelligence`
6. `factor-researcher`
7. `statistical-validator`
8. `portfolio-risk`
9. `methodology-auditor`

The primary thread acquires and fixes the Massive source set before daily analytical delegation. `data-steward` audits that fixed set. Analytical agents should not each refetch their own broad market state.

## Deterministic research governance

The repository now contains the full operational spine that the first live qualification run proved was missing:

- `bootstrap.ps1` performs the Windows pre-acquisition bootstrap without Python, records source/prior-attempt/writability evidence, resolves a real Python 3.11+ interpreter, and may provision a disposable repo-local CPython 3.12 under `.runtime/python` before failing;
- `run_python.ps1` binds deterministic scripts to that resolved executable, records every failed candidate probe, scans the Windows registry/uv installs/PATH comprehensively, and never falls back to an unverified shim;
- `preflight.py` performs the deeper Python-stage readiness check once the governed runtime has been resolved;
- `massive_request_gate.py` serializes provider-facing Massive `call_api` starts, enforces the configured rolling rate budget, records an auditable request ledger, taints the attempt on any rate-limit response, and seals only compliant ledgers;
- `evaluate_capabilities.py` applies CORE / ENRICHMENT / EVENT_OPTIONAL policy to authenticated MCP probes;
- `materialize_mcp_dataset.py` converts bounded MCP query chunks into immutable canonical JSONL with truncation rejection, exact row-count checks, unique-key checks, and SHA-256 binding;
- `seal_acquisition.py` accepts downstream-eligible `COMPLETE` or `DEGRADED` manifests only when every CORE dataset is successfully accessed and durably verified;
- `scripts/pipeline/run_daily_pipeline.py` computes the repository-owned feature store, market state, multi-factor ranks, residual signal, macro coverage, ensemble, research-only risk sizing, and forecast payload;
- `validate_artifact.py` performs schema validation of actual run artifacts;
- forecast freezing now independently requires both a sealed compliant Massive request ledger and a PASS methodology audit bound to the same attempt; hypothesis registration, promotion gates, and OOS records remain immutable/evidence-bound;
- package validation rejects direct-network/API-key bypasses, transient caches, seeded runtime research artifacts, and invalid model/capability configuration.

This is a research-state/data-integrity gate, not a Codex permission boundary.

## Evaluation assets

`evals/routing_cases.jsonl` contains 20 positive routing prompts, 20 clear negatives, and 10 neighboring/ambiguous cases for the five user-facing research skills. `evals/task_cases.jsonl` contains 10 representative tasks and 12 failure scenarios, including MCP unavailability and “discoverable but not Basic-entitled” capability failures. These are evaluation inputs, not proof of runtime performance.

## Daily operational configuration

- `config/daily-capabilities.json` defines which Massive capabilities are CORE, ENRICHMENT, or EVENT_OPTIONAL.
- `config/daily-model.json` fixes the initial operational universe/history/factor-weight parameters (top 25 liquid USD pairs, 120-calendar-day requested history, >=60 observations, robust rank weights).
- `config/python-runtime-policy.json` declares the minimum deterministic runtime and forbids automatic runtime installation by the control plane.
- `config/massive-request-policy.json` makes provider pacing executable policy rather than prompt advice. The default is five `call_api` starts per rolling 60 seconds, minimum 12 seconds apart, serial completion, and new-attempt recovery after a rate-limit response.
- Release packages intentionally contain no date-specific run/acquisition/forecast artifacts. Each retry receives a new `attempt_id` under one stable daily `run_id`.

## Data boundary

The supplied research vision prioritizes cross-sectional factor research, breadth/regime modeling, residual-return modeling, and cross-asset context while explicitly rejecting unsupported microstructure/on-chain claims. The supplied crypto Basic guide constrains crypto to EOD data with two years of history and excludes crypto trades/last trade, snapshots, WebSockets, and flat files.

See:

- `docs/massive-mcp-data-plane.md`
- `docs/data-capability-boundary.md`
- `docs/architecture.md`
