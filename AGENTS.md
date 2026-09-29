# Research control-plane guidance

The primary Codex thread is the research director for an end-of-day systematic crypto research platform.

## Project-root and installed-Skill boundary

Skills may be repo-scoped or installed outside the repository. All repository paths in Skill instructions (`config/...`, `scripts/...`, `docs/...`, `schemas/...`, `research/...`, `workflows/...`) resolve from the **active project root** containing this `AGENTS.md` and `.codex/config.toml`, never from the Skill installation directory. Do not use `../..` traversal from a global Skill to infer the project root. The daily Skill carries a synchronized `references/daily-goal.md` reading fallback, but executable repository work still requires an active project root.

## Mandatory Massive data path

Use the **Massive MCP server** as the authoritative external data-access plane for every Massive-backed workflow in this repository. Do not bypass it with direct REST/HTTP calls, `curl`, `requests`, `httpx`, a Massive/Polygon SDK, copied API keys, or web search unless the user explicitly changes the architecture.

For Massive-backed work:

1. use `$massive-basic-endpoints` only as the dated Basic-entitlement/capability snapshot;
2. use `$massive-mcp-data-plane` for current endpoint discovery and retrieval;
3. use Massive MCP endpoint search before relying on uncertain parameters or response fields;
4. use Massive MCP API execution for the actual source data, following pagination to completion;
5. prefer one shared Massive workspace per governed run when tables/SQL are useful;
6. seal an acquisition manifest before downstream research treats the source set as fixed.

Massive MCP endpoint discovery is **not entitlement proof**. The MCP catalog can expose endpoints outside the user's Basic entitlement. A dated Basic snapshot entry supports plan eligibility only for that snapshot; an access-denied response or unknown snapshot entry must not be silently worked around.

Before acquisition, evaluate `config/daily-capabilities.json` using three separate facts for each capability: current endpoint discovery, dated Basic-snapshot status, and actual authenticated access. `CORE` failures block; `ENRICHMENT` failures degrade coverage when the crypto core remains valid; `EVENT_OPTIONAL` failures are recorded/skipped unless an active registered design explicitly requires them. Never silently fall back to another market-data source.

## Windows bootstrap invariant

On Windows, the pre-acquisition control path must not assume that the `python` command is healthy. Start a fresh daily attempt with native `scripts/control_plane/bootstrap.ps1`, which performs static/writability/prior-attempt checks without Python and proves a working Python 3.11+ executable. The resolver enumerates repo virtualenvs, versioned `py` launchers, Windows Python registry installations, common CPython/Conda/Scoop paths, recursive uv-managed installs, all PATH/`where.exe` candidates, and `uv python find`. Any successful launcher is rebound to the actual `sys.executable`; governed stages never continue through an unverified shim.

If no existing interpreter executes and uv is available, bootstrap may perform one bounded self-repair: provision CPython 3.12 under this repository's `.runtime/python` directory with no system PATH/global installation. The newly provisioned executable must pass the same probe. If bootstrap still returns BLOCKED, make **zero Massive provider calls**, preserve the full candidate/provisioning evidence, and report remediation. If bootstrap returns READY, bind the attempt to the emitted runtime descriptor, validate it against `schemas/python_runtime.schema.json`, and invoke every repository Python script through `scripts/control_plane/run_python.ps1 -RuntimeFile <attempt-runtime.json>`. Do not fall back to bare `python` later in the same attempt.

Provider-facing Massive `call_api` requests are governed by `config/massive-request-policy.json` and `scripts/control_plane/massive_request_gate.py`. Initialize one attempt-scoped request ledger before the first authenticated data probe. Obtain a permit before every `call_api`; the gate serializes starts and enforces the rolling request cap. Record each outcome immediately. A Massive `RATE_LIMIT` warning taints the attempt and requires a fresh attempt; later successful retries do not erase the process violation. `search_endpoints`, `workspace`, and `query_data` are MCP control/local-workspace operations and are outside this provider-call budget unless the policy is explicitly changed.

## Ownership boundaries

Use Massive MCP for external Massive data discovery/retrieval and transient MCP workspace operations.

Use deterministic code/SQL for durable MCP materialization, row-count/digest checks, normalization, research-cutoff checks, joins, feature calculation, ranking, regressions, bootstrap/resampling, multiple-testing correction, scoring, persistence, immutable sealing, and research-state transitions. A model recommendation or tool result is evidence, not a state transition.

Use model reasoning for hypothesis formation, interpretation, anomaly investigation, independent review, adversarial critique, and explanation.

Agent or Skill instructions never grant runtime authority. Filesystem, shell, network, MCP/app, secret, approval, and external-write permissions remain controlled by Codex/runtime policy. OAuth credentials are host-owned; do not copy credentials into repository files.

## Research discipline

- Treat `docs/data-capability-boundary.md` as the evidence boundary.
- Treat `docs/massive-mcp-data-plane.md` as the acquisition contract.
- Preregister a hypothesis before broad parameter search.
- Keep discovery/research separate from independent validation.
- Never let the factor researcher approve its own candidate.
- Never promote from prose alone; promotion requires deterministic gate evidence.
- Freeze each forecast before its target outcome exists.
- Preserve failed, rejected, inconclusive, and invalid experiments.
- Report uncertainty and unsupported claims explicitly.
- Do not let a fresh post-cutoff MCP observation leak into a frozen run merely because a subagent can access the same MCP server.

## Multi-agent use

Spawn subagents when the user explicitly requests delegation or when an activated control-plane workflow requires a named independent role. Do not delegate ordinary work merely because custom agents exist. Prefer independent read-heavy analysis in parallel, then a synthesis barrier.

Daily workflow: primary thread creates a fresh attempt, runs the native Windows bootstrap when applicable, binds a working deterministic runtime, runs local Python preflight through that runtime, initializes the Massive request ledger, probes effective Massive access through the request gate, acquires/stages the fixed source set through that same gate, durably materializes and seals it, then `data-steward` audits that fixed set. Repository code runs the deterministic daily pipeline before `crypto-internals`, `relative-value`, `macro-regime`, and `institutional-intelligence` analyze its outputs in parallel; then `portfolio-risk`; then `methodology-auditor`; primary thread seals/audits the request ledger and freezes the deterministic forecast payload only when both request compliance and methodology review pass.

Research workflow: primary thread fixes any required source snapshot through Massive MCP; `factor-researcher` -> `statistical-validator` -> `methodology-auditor`; the primary thread adjudicates from artifacts and deterministic gate results.

Do not allow child agents to recursively spawn agents unless a user explicitly changes that boundary.

## Evidence

Prefer actual artifacts, Massive MCP call evidence, sealed acquisition manifests, and executed checks over agent summaries. When completing work, report changed files, commands actually run, outcomes, and unresolved blockers.
