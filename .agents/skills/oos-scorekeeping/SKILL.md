---
name: oos-scorekeeping
description: Score a matured immutable forecast against realized outcomes obtained from a provenance-complete source. Use only after the target horizon has matured; do not use to generate forecasts or backtests.
---

**Repository path contract:** paths such as `config/...`, `scripts/...`, `docs/...`, `schemas/...`, `research/...`, and `workflows/...` are relative to the active project root (the directory containing `AGENTS.md` and `.codex/config.toml`), **not** relative to this installed Skill directory. Never walk `..` from the Skill installation to find project files. If no matching project root is active, do not invent one.

# OOS scorekeeping

Own the forecast-to-realized-outcome ledger. Forecast-time state is immutable.

## Inputs

Read the frozen forecast from `research/forecasts/` and `schemas/outcome_record.schema.json`. Realized Massive-backed outcome data must either already exist as an inspectable governed artifact or be acquired through `$massive-mcp-data-plane` with a separate sealed acquisition record.

## Workflow

1. Verify the forecast exists, has not been rewritten, and its target horizon has matured. If maturity cannot be established, stop `INCONCLUSIVE`.
2. If realized outcome data is not already provenance-complete, acquire it through Massive MCP via `$massive-mcp-data-plane`. Do not fetch with direct REST/SDK/API keys and do not alter the original forecast's source snapshot.
3. Use repository-owned deterministic scoring code for the registered metric. This control-plane skill does not invent a scoring formula; if no authoritative scorer exists, stop and identify that missing mechanism.
4. Keep realized/post-forecast information out of the frozen forecast. Persist a separate outcome record under `research/outcomes/` that binds to the forecast ID and content digest.
5. Verify the outcome record is schema-compatible and the source artifacts/acquisition record used for realized data are inspectable.

## Completion

Complete only when a matured forecast has one evidence-linked outcome record produced by deterministic scoring, the original forecast is byte-for-byte unchanged, and missing/stale realized data is reported rather than backfilled.
