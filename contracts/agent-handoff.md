# Agent handoff contract

Subagents should return compact structured evidence, preferably JSON matching `schemas/agent_handoff.schema.json`.

Required fields:

- `agent`
- `run_id`
- `status`
- `summary`
- `claims[]`
- `evidence[]`
- `warnings[]`
- `uncertainty[]`

A handoff is not authoritative state. The primary thread reconciles handoffs against source artifacts and deterministic checks.

For Massive-backed daily/research work, at least one `evidence[]` entry must identify the sealed acquisition manifest or a deterministic artifact that itself binds to that acquisition. A subagent may not replace that fixed source set with a fresh MCP observation without creating a new governed acquisition/run boundary.

Statuses are role-specific but should be explicit (`PASS`, `DEGRADED`, `BLOCK`, `PROMOTE`, `REJECT`, `INCONCLUSIVE`, `INVALID_EXPERIMENT`, etc.).

Evidence entries should identify a repository path plus an optional digest/record identifier. Avoid unsupported narrative confidence scores when a concrete artifact can be cited instead.
