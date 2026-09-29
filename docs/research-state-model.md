# Research state model

## Candidate lifecycle

```text
REGISTERED
  -> RESEARCHED
  -> VALIDATED
  -> AUDITED
  -> PROMOTED | REJECTED | INCONCLUSIVE | INVALID
```

Only deterministic code may write promotion state.

## Required evidence before promotion

A candidate may be promoted only if all are true:

1. hypothesis was preregistered and its multiple-testing family is declared;
2. data-quality status is `PASS`;
3. independent `statistical-validator` verdict is `PROMOTE`;
4. validation checks pass for chronology, leakage, multiple testing, uncertainty, parameter stability, regime dependence, turnover, cost scenarios, and OOS evidence;
5. `methodology-auditor` status is `PASS` for the same candidate and hypothesis;
6. validation and audit evidence arrays are non-empty and identities agree;
7. promotion has not already been recorded.

The gate does not authorize trading, network access, or external writes. It only controls this repository's research-state transition.

## Audit subjects

Methodology audits are explicit about subject identity:

- candidate audits use `subject_type = candidate` and bind `subject_id`, `candidate_id`, and `hypothesis_id`;
- daily-run audits use `subject_type = daily_run` and bind `subject_id` plus `run_id`.

A missing or ambiguous subject identity cannot satisfy a candidate promotion gate.

## Forecast lifecycle

A forecast is created before its target outcome exists and written immutably to `research/forecasts/`. Rewriting the same forecast ID is forbidden. Stored forecasts carry a content digest; the research cutoff may not occur after forecast creation. For a daily run, the freeze transition additionally requires a sealed PASS Massive request ledger and a PASS methodology audit bound to the same attempt; orchestration prose cannot substitute for either artifact.

Once the target horizon matures, scorekeeping writes a separate outcome artifact under `research/outcomes/` that binds to the forecast ID and digest. Never rewrite the original forecast with realized results. If the repository has no authoritative deterministic scorer for the registered metric, scorekeeping is inconclusive rather than model-invented.

## Replay qualification state

`OFFLINE_REPLAY` is a separate qualification mode, not a daily-run or provider state. A replay PASS proves only that a fixed, explicitly labelled fixture passed durable-materialization checks and the deterministic downstream code reproduced its expected artifacts. It never transitions a daily attempt to provider-qualified, never satisfies authenticated capability probes or request-ledger gates, and is not eligible for the live forecast freeze transition.

## Bootstrap state

A daily attempt begins in a platform bootstrap state before any provider request is permitted. Native `bootstrap.ps1` on Windows and `bootstrap.sh` on Linux are authoritative for this step because neither requires Python for its initial controls. Each writes an attempt-scoped bootstrap artifact whether the runtime probe succeeds or fails. `READY` binds the attempt to a tested Python 3.11+ runtime descriptor; `BLOCKED` forbids Massive acquisition. The control plane never converts a missing runtime into permission to improvise calculations or install software outside the bounded repository-local policy.


## Windows runtime bootstrap hardening

On Windows, provider acquisition is downstream of a Python-independent PowerShell bootstrap. Repository paths resolve from the active project root, never the installed Skill directory. The resolver records every candidate outcome, checks repo virtualenv/Windows registry/common installs/uv/PATH, rebinds launchers to the actual interpreter executable, and may provision only a repository-local CPython under `.runtime/python` via uv. No system PATH mutation or global Python installation is permitted. Massive calls remain forbidden until Python >=3.11 executes successfully and the runtime descriptor is persisted.

## Linux runtime bootstrap hardening

On Linux/Codex Cloud, `bootstrap.sh` performs the corresponding Python-independent checks and `run_python.sh` resolves and revalidates the concrete interpreter. Versioned PATH or pyenv shims are evidence sources only: the descriptor and every governed execution use the probed `sys.executable`. Provisioning, when required and permitted, remains confined to `.runtime/python`; a failed binding produces BLOCKED evidence and authorizes no provider calls.
