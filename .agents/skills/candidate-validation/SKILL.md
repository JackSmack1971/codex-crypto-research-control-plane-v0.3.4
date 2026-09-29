---
name: candidate-validation
description: Independently validate an already-researched signal candidate before any promotion decision. Use when validation evidence is requested for a candidate; do not use for initial factor research or the final methodology audit.
---

**Repository path contract:** paths such as `config/...`, `scripts/...`, `docs/...`, `schemas/...`, `research/...`, and `workflows/...` are relative to the active project root (the directory containing `AGENTS.md` and `.codex/config.toml`), **not** relative to this installed Skill directory. Never walk `..` from the Skill installation to find project files. If no matching project root is active, do not invent one.

# Candidate validation

Own the independent statistical-validation stage. A `PROMOTE` verdict means only "eligible for the deterministic promotion gate"; it is not a state transition.

## Inputs

Require a preregistered hypothesis plus candidate research artifacts. Read `docs/research-state-model.md`, `docs/data-capability-boundary.md`, `docs/massive-mcp-data-plane.md`, and `schemas/validation_report.schema.json` when validating the candidate.

## Workflow

1. Bind the candidate to exactly one registered hypothesis. A missing registration or identity mismatch is `INVALID_EXPERIMENT`.
2. Delegate validation to a fresh `statistical-validator` context. If independent context cannot be obtained, return `INCONCLUSIVE`; do not reuse the factor-research context as the validator.
3. Verify chronology, leakage, multiple-testing correction, uncertainty, parameter stability, regime dependence, turnover, pessimistic cost scenarios, OOS evidence, and (for Massive-backed inputs) the sealed acquisition identity/cutoff used by the candidate. Missing acquisition provenance is material missing evidence. Missing material evidence is `INCONCLUSIVE`; an invalid temporal or leakage design is `INVALID_EXPERIMENT`; a valid candidate that fails the registered criteria is `REJECT`.
4. Persist a validation artifact under `research/validations/` matching the schema. Do not create or modify promotion state.

## Completion

Complete only when the validation artifact is schema-compatible, its candidate/hypothesis identities agree with the inspected inputs, its evidence paths are inspectable, and the verdict is exactly `PROMOTE`, `REJECT`, `INCONCLUSIVE`, or `INVALID_EXPERIMENT`.
