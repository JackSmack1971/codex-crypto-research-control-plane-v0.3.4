---
name: massive-basic-endpoints
description: Select and validate Massive REST capabilities documented as Included on the Basic plan in the 2026-09-28 snapshot. Use when a governed Massive MCP task must establish the snapshot entitlement/freshness boundary; do not treat this static catalog as live retrieval or current entitlement proof.
---

**Repository path contract:** paths such as `config/...`, `scripts/...`, `docs/...`, `schemas/...`, `research/...`, and `workflows/...` are relative to the active project root (the directory containing `AGENTS.md` and `.codex/config.toml`), **not** relative to this installed Skill directory. Never walk `..` from the Skill installation to find project files. If no matching project root is active, do not invent one.

# Massive Basic entitlement router

This support skill chooses the narrowest Massive capability represented as **Included on Basic** by the supplied dated snapshot. It is an entitlement/capability guard for `$massive-mcp-data-plane`, not a replacement for Massive MCP.

## Mandatory boundaries

- Treat `references/endpoint-catalog.json` as a **dated 2026-09-28 snapshot**, not permanent proof of current eligibility.
- An endpoint present in the catalog was represented as **Included on Basic** by the supplied source. An endpoint absent from the catalog is **unknown**, not excluded and not permitted.
- Massive MCP endpoint discovery can expose capabilities outside Basic. Discovery alone never upgrades an `UNKNOWN` snapshot status to `INCLUDED`.
- Preserve each row's `basic_limit` semantics. Do not promote end-of-day, daily, periodic, or delayed data to real-time.
- Do not invent parameters, response fields, pagination, authentication, ticker syntax, or undocumented limits. Current parameter/schema verification belongs to Massive MCP.
- Prefer a non-deprecated capability when it satisfies the same need.

## Workflow: Asset → Need → Snapshot limit → MCP verification

1. Identify the market: `stocks`, `options`, `indices`, `forex`, `crypto`, `futures`, or `economy`.
2. Identify the smallest data shape that answers the request.
3. Query the catalog deterministically when practical:

   ```bash
   python .agents/skills/massive-basic-endpoints/scripts/endpoint_lookup.py --market crypto --query "daily market summary"
   ```

   On Windows, if the normal `python.exe` launcher is blocked by the sandbox/runtime, use the no-Python PowerShell fallback:

   ```powershell
   .\.agents\skills\massive-basic-endpoints\scripts\endpoint_lookup.ps1 -Market crypto -Search "daily market summary"
   ```

   This fallback parses only the static catalog; it does not retrieve market data.
4. Compare plausible matches and select the narrowest capability. Read `references/decision-notes.md` only for the relevant special case.
5. Return the exact method/path, snapshot `basic_limit`, and status `INCLUDED` or `UNKNOWN`.
6. For any actual retrieval or current-schema claim, hand off to `$massive-mcp-data-plane`. Do not call the REST API directly.

## Evidence required before completion

A routing result is complete only when it establishes market, capability, exact documented method/path, snapshot `basic_limit`, and whether current MCP verification is still required.

If no catalog entry establishes the requested capability, report the snapshot as **UNKNOWN** rather than inferring plan access.

## Load only when needed

- `references/decision-notes.md` — bar-selection edge cases, market clocks, shared-path caveats, stock filing selection, futures recency, and deprecations.
- `references/provenance.md` — source coverage, transformation policy, and the one repaired description.
- `references/endpoint-catalog.json` — all snapshot entries; prefer the lookup script over loading the full file when one or a few endpoints are needed.
