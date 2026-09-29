# Source basis

This package was derived from the supplied project materials and current OpenAI/Massive documentation available during the 2026-09-28 revision.

## Supplied project material

- initial control-plane/subagent architecture vision;
- daily multi-factor + regime + cross-asset intelligence engine research brief;
- Crypto Basic API Guide dated 2026-09-28;
- bundled dated Massive Basic endpoint catalog already present in the package.

## Massive guidance used for the revision

- Massive AI Tools quickstart: https://massive.com/docs/ai-tools/quickstart
- Massive Codex setup: https://massive.com/docs/ai-tools/clients/codex
- Massive hosted MCP server: https://mcp.massive.com/

The current Massive MCP tool surface was also exercised during this revision: endpoint discovery located the crypto grouped daily route; an authenticated grouped EOD call was stored in a Massive workspace; and SQL over that stored table succeeded. This verifies the workflow shape, not the user's local Codex authentication state.

## OpenAI guidance used for the revision

- Build skills / MCP dependencies: https://developers.openai.com/plugins/build/skills
- Build skills in Codex: https://learn.chatgpt.com/docs/build-skills
- Codex customization / Skills + MCP: https://learn.chatgpt.com/docs/customization/overview
- Codex MCP: https://learn.chatgpt.com/docs/extend/mcp
- Codex config basics: https://learn.chatgpt.com/docs/config-file/config-basic
- Codex advanced config: https://learn.chatgpt.com/docs/config-file/config-advanced
- Codex configuration reference: https://learn.chatgpt.com/docs/config-file/config-reference
- Codex subagents/custom agents: https://learn.chatgpt.com/docs/agent-configuration/subagents
- AGENTS.md guidance: https://learn.chatgpt.com/docs/agent-configuration/agents-md
- Codex skill creator reference: https://github.com/openai/codex/blob/main/codex-rs/skills/src/assets/samples/skill-creator/SKILL.md
- Codex 0.157.1 agent-role override source: https://github.com/openai/codex/blob/rust-v0.157.1/codex-rs/core/src/agent/role.rs
- Codex 0.157.1 agent-role discovery source: https://github.com/openai/codex/blob/rust-v0.157.1/codex-rs/agent-roles/src/loader.rs
- Codex 0.158.0 agent-role override source: https://github.com/openai/codex/blob/rust-v0.158.0/codex-rs/core/src/agent/role.rs
- Codex 0.157.1 config schema source: https://github.com/openai/codex/blob/rust-v0.157.1/codex-rs/config/src/config_toml.rs

## Design principles applied

- Massive MCP, not ad-hoc REST/API-key code, owns Massive external acquisition;
- the static Basic catalog is a dated entitlement boundary, while MCP endpoint search is current capability/schema discovery;
- acquire/fix the source set before parallel analytical agents run;
- keep each Skill focused on a recognizable goal and use support skills for shared acquisition/entitlement logic;
- use deterministic code/SQL for calculations, persistence, immutability, and state transitions;
- separate factor discovery, independent validation, adversarial audit, and promotion authority;
- preserve point-in-time data boundaries, failed variants, and immutable forecast-time state;
- require inspectable completion evidence and explicit failure/stop branches;
- treat evaluation corpora as test inputs, not proof of skill effectiveness.

## Python runtime bootstrap

- Astral uv Python versions documentation: `https://docs.astral.sh/uv/concepts/python-versions/` — documents interpreter discovery, managed versus system Python, and Windows discovery behavior.
- Astral uv CLI reference: `https://docs.astral.sh/uv/reference/cli/` — documents `uv python find` and `--no-python-downloads`; v0.3.4 uses uv to locate existing interpreters and, only when necessary, to provision a repository-local CPython runtime under `.runtime/python` without system PATH mutation.

- OpenAI Agent Skills documentation: Skills are self-contained directories and supporting material belongs in `references/`, `scripts/`, and `assets/`; repo-scoped and user-scoped installs are distinct deployment locations. https://developers.openai.com/api/docs/guides/tools-skills
