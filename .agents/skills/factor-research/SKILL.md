---
name: factor-research
description: Investigate a preregistered quantitative signal hypothesis against a fixed provenance-complete dataset and produce candidate research evidence. Use for factor R&D; do not use to validate an already-researched candidate or to promote it.
---

**Repository path contract:** paths such as `config/...`, `scripts/...`, `docs/...`, `schemas/...`, `research/...`, and `workflows/...` are relative to the active project root (the directory containing `AGENTS.md` and `.codex/config.toml`), **not** relative to this installed Skill directory. Never walk `..` from the Skill installation to find project files. If no matching project root is active, do not invent one.

# Factor research

Own discovery/research, not independent validation or promotion.

## Inputs

Require an immutable registered hypothesis. Read `docs/research-state-model.md`, `docs/data-capability-boundary.md`, and `docs/massive-mcp-data-plane.md` whenever the proposed signal or explanation depends on Massive-backed data.

## Workflow

1. Verify the registered hypothesis identity and keep its question, signal family, universe, primary metric, expected sign, test period, and multiple-testing family fixed. If no valid registration exists, stop before testing.
2. If the required fixed dataset is absent, stale for the declared test window, or lacks acquisition provenance, have the primary thread use `$massive-mcp-data-plane` before research begins. Seal the acquisition manifest. Do not let result-driven refetching or post-hoc universe changes become an unlogged variant.
3. Delegate research to `factor-researcher`. If that independent research context is unavailable, stop with the missing capability rather than collapsing research and validation into one context. Record every parameter, horizon, filter, universe, and transformation variant attempted; do not discard failed variants.
4. Prefer evidence about cross-sectional monotonicity, rank robustness, parameter stability, regime behavior, turnover, and liquidity-aware comparisons over threshold mining.
5. Produce a candidate handoff with the hypothesis ID, candidate ID, attempted-variant ledger, source acquisition identity, result artifacts, limitations, and evidence paths. Do not issue a promotion verdict.
6. If the user's goal explicitly continues through the full lifecycle, hand the finished candidate to `$candidate-validation` and then `$methodology-audit`; otherwise stop at the research handoff.

## Completion

Complete when the registered hypothesis remains unchanged, the fixed data snapshot is provenance-complete, all attempted variants are accounted for, candidate evidence is inspectable, and downstream reviewers can reproduce which artifacts belong to the candidate. Materially new hypotheses require a new registration/version.
