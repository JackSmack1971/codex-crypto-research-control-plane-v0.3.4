# Daily `/goal`

This workflow is the live provider path. Offline deterministic qualification uses `python3.12 -B scripts/control_plane/qualify_replay.py`; its `OFFLINE_REPLAY` artifact cannot satisfy any capability-probe, request-ledger, acquisition-provenance, methodology-audit, or forecast-freeze requirement below.

Use one stable daily `run_id` and a fresh `attempt_id` for every retry.

```text
/goal Execute one complete governed end-of-day crypto research attempt for <DATE> through the strongest valid terminal state.

Use the repository control plane exactly. Do not stop after planning.

0. NATIVE BOOTSTRAP / ATTEMPT IDENTITY
- Stable run_id: <DATE>-eod.
- Create a unique attempt_id; never overwrite a prior attempt.
- Select the native control path from the runtime platform: Windows uses `bootstrap.ps1` -> `run_python.ps1`; Linux/Codex Cloud uses `bootstrap.sh` -> `run_python.sh`.
- On Windows, **do not start with bare `python`, `python3`, or a PATH shim**. First run `scripts/control_plane/bootstrap.ps1` in native PowerShell from the active project root. Repository paths are rooted at the directory containing `AGENTS.md` and `.codex/config.toml`; never resolve project files by walking upward from an installed Skill directory. The bootstrap performs required-file/writability/source-identity/prior-attempt checks without Python and always writes `research/runs/<attempt>.bootstrap.json` plus `research/runs/<attempt>.python-runtime.json`.
- On Linux/Codex Cloud, **do not start with bare `python`, `python3`, or a PATH shim**. First run `scripts/control_plane/bootstrap.sh --run-id <run> --attempt-id <attempt> --research-cutoff <cutoff>` from the active project root. It performs the same Python-independent checks and writes the same attempt-scoped bootstrap and runtime artifacts.
- The native runtime resolver tests an attempt-bound runtime and platform-appropriate candidates. Windows includes versioned `py`, registry, common installs, uv and PATH; Linux includes repo virtualenvs, concrete versioned commands, pyenv-resolved installs, uv-managed interpreters, PATH, and `uv python find >=3.11`. Any successful launcher is rebound to `sys.executable`; governed scripts thereafter execute the resolved interpreter directly, not the launcher/shim.
- If no existing interpreter executes and uv is available, bootstrap is authorized to provision CPython 3.12 **only inside `.runtime/python` in this repository** using `uv python install --install-dir ... --no-bin`. It must not modify system PATH or perform a global Python install. `.runtime/` is untracked disposable infrastructure. Acquisition is still forbidden until the newly provisioned interpreter passes the same executable probe.
- If bootstrap remains BLOCKED after bounded repo-local provisioning, stop before MCP calls and preserve the full candidate/provisioning diagnostics. Git unavailability is a reported verification limitation, not by itself a research blocker.
- If bootstrap is READY, validate `research/runs/<attempt>.python-runtime.json` against `schemas/python_runtime.schema.json`, then run all repository Python scripts through the selected native wrapper: Windows uses `scripts/control_plane/run_python.ps1 -RuntimeFile research/runs/<attempt>.python-runtime.json ...`; Linux uses `scripts/control_plane/run_python.sh --runtime-file research/runs/<attempt>.python-runtime.json ...`. Do not revert to bare `python` or `python3` later in the attempt.
- Run Python `preflight.py` and `discover_run.py` through that bound runtime before acquisition, then initialize `research/runs/<attempt>.massive-request-ledger.json` through the same wrapper with `massive_request_gate.py init`.
- The default provider-facing budget is defined in `config/massive-request-policy.json` and currently enforces at most five Massive `call_api` starts per rolling 60 seconds with at least 12 seconds between permits.
- Before any planned multi-call phase, run `massive_request_gate.py plan --request-count <N>` through the bound runtime and record the minimum start span. Reconcile any newer user pacing instruction before that phase. If the user tightens the provider-rate constraint below the attempt's sealed policy snapshot, stop issuing permits and start a fresh attempt under the tighter policy; do not retroactively relabel earlier calls compliant.

1. EFFECTIVE MASSIVE CAPABILITY PROBE
- Read config/daily-capabilities.json.
- Through Massive MCP, independently record endpoint discovery, dated Basic snapshot status, and actual authenticated access for each applicable capability. Every provider-facing `call_api` probe requires a request-gate permit and immediate completion record.
- Write an attempt-scoped capability probe report and run evaluate_capabilities.py.
- CORE failure => BLOCKED.
- ENRICHMENT failure => DEGRADED coverage, not automatic BLOCK.
- EVENT_OPTIONAL unavailable => record unavailable/skip unless this run explicitly requires it.
- Never bypass Massive MCP.

2. FIX AND DURABLY MATERIALIZE THE SOURCE SET
- Acquire point-in-time crypto universe and cutoff-day grouped crypto cross-section first. Every provider-facing `call_api` acquisition must pass through the attempt request gate; do not issue parallel provider calls.
- Materialize both with scripts/control_plane/materialize_mcp_dataset.py through the bound runtime; transient MCP workspace tables do not count as durable evidence.
- From that fixed cross-section, deterministically select the configured top-N eligible USD pairs and anchors according to config/daily-model.json.
- Acquire the configured historical lookback for that fixed selected universe through Massive MCP, using bounded calls and complete pagination.
- For the per-ticker history phase, plan the full request count before starting. The request gate, not model timing judgment, owns waiting between provider calls.
- For workspace tables, export ordered 100-200 row query_data chunks; materialize canonical JSONL; verify exact staged/local row counts, unique keys, and SHA-256 digests.
- Acquire/materialize accessible ENRICHMENT inputs (FX, stock, index) and relevant EVENT_OPTIONAL inputs without broadening the run after downstream results are seen.
- Capture exact client UTC timestamps around MCP calls when server timestamps/request IDs are unavailable; do not estimate them.
- After every provider call, complete its ledger entry with outcome, warning, row count, request ID when exposed, and pagination state. On the first `RATE_LIMIT` warning, stop the batch immediately: the gate marks the attempt TAINTED and no later retry may rehabilitate that attempt. Finish it BLOCKED and create a new attempt for recovery.
- Seal the acquisition only after durable materialization. PARTIAL is not downstream-eligible. DEGRADED is downstream-eligible only when every CORE dataset is COMPLETE and verified.

3. DATA-STEWARD GATE
- Delegate data-steward against the sealed acquisition, capability evaluation, and materialized metadata/data.
- CORE missing/denied/transient/incomplete/post-cutoff => BLOCK.
- Missing ENRICHMENT => normally DEGRADED if core remains valid.
- Validate the handoff against schemas/agent_handoff.schema.json and the data-quality artifact against schemas/data_quality_report.schema.json with validate_artifact.py.

4. DETERMINISTIC PIPELINE
- If data quality permits continuation, run scripts/pipeline/run_daily_pipeline.py through the bound runtime over the verified materialized data.
- Code owns feature calculations, rankings, residual model, market state, ensemble, research-only risk sizing, persistence, and forecast payload creation.
- Validate pipeline-result.json against schemas/daily_pipeline_result.schema.json.
- If the deterministic pipeline cannot execute or history coverage is insufficient, BLOCK rather than substituting prose calculations.

5. PARALLEL ANALYSIS
Run crypto-internals, relative-value, macro-regime, and institutional-intelligence in parallel over the fixed deterministic artifacts.
- Missing macro ENRICHMENT must be reported as DEGRADED/UNAVAILABLE coverage, never invented or silently neutralized.
- Institutional source unavailability is distinct from no material event.
- No agent may independently refresh the fixed run dataset.
- Validate every handoff artifact against agent_handoff.schema.json.

6. SYNTHESIS -> PORTFOLIO-RISK -> METHODOLOGY AUDIT
- Primary Codex reconciles deterministic outputs and the four handoffs.
- Run portfolio-risk on the deterministic research-only proposal.
- Before methodology audit, run `massive_request_gate.py audit --ledger <ledger> --seal`. Any spacing/window violation, incomplete request record, or observed `RATE_LIMIT` is blocking and requires a new attempt.
- Run methodology-auditor fresh and bind the artifact to both `run_id` and `attempt_id`. A denied ENRICHMENT is acceptable only when explicitly degraded and no claim depends on it. CORE failure, direct-network workaround, transient-only core data, cutoff leakage, or request-ledger noncompliance is blocking.
- Validate audit artifact against audit_report.schema.json.

7. FREEZE FORECAST
- If mandatory gates permit it, freeze the deterministic forecast payload with `freeze_forecast.py --request-ledger <sealed-ledger> --methodology-audit <PASS-audit>` before its target outcome exists. The freeze command independently rejects a noncompliant/unsealed ledger, a non-PASS audit, or an audit bound to a different attempt.
- Verify immutable rewrite rejection.
- A DEGRADED forecast is permitted only when CORE is complete, the data-steward permits continuation, the deterministic pipeline completes, and methodology audit passes while preserving the degradation in source evidence.

8. VERIFY
- Validate every produced JSON artifact against its declared schema using validate_artifact.py through the bound runtime. Validate the native bootstrap artifact against `schemas/windows_bootstrap.schema.json` on Windows or `schemas/linux_bootstrap.schema.json` on Linux, and validate the runtime-resolution artifact against `schemas/python_runtime.schema.json` once Python is available.
- Run validate_control_plane.py, relevant tests, and Git checks when a Git checkout is actually available.
- Report exact commands and outcomes, not inferred success.

Final report: status; run_id/attempt_id; cutoff; effective capability matrix; acquisition/materialization digests; data-quality result; deterministic pipeline result; four analytical handoffs; portfolio-risk result; methodology audit; frozen forecast path/digest if any; executed verification; files created; unresolved limitations.
```
