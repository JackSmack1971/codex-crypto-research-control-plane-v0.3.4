# Skill evaluation corpus

These files make the five user-facing research workflow skills measurable without claiming runtime performance that has not been observed. The two Massive acquisition/entitlement skills are support skills invoked from those workflows.

## Routing corpus

`routing_cases.jsonl` contains:

- 20 positive prompts that should activate one of the five workflow skills;
- 20 clear negatives that should activate none of those five workflow skills;
- 10 neighboring/ambiguous prompts that test the boundaries between research, validation, audit, daily execution, scorekeeping, and deterministic state transition.

Run each routing case repeatedly against the same Codex version/configuration and record the selected skill, if any. Report precision, recall, and neighbor false-activation rate. The target is precision >= 0.90, recall >= 0.90, and neighbor false activation <= 0.15.

## Task/failure corpus

`task_cases.jsonl` contains 10 representative workflow scenarios and 12 failure scenarios with success criteria fixed before execution. The acquisition/runtime failures cover MCP unavailability, discoverable-but-unentitled routes, enrichment access denial that must degrade rather than block, transient/truncated MCP materialization, and missing deterministic runtime stages that must fail preflight before large acquisition.

For behavioral validation, compare runs from the same starting state with the skill available versus a no-skill baseline. Track task success, failure recovery, policy/autonomy violations, premature completion, unnecessary continuation, direct-network bypass attempts, and at least two execution-cost measures such as tokens, tool calls, commands, or wall time.

Do not convert these static cases into a validated-performance score until repeated runtime evidence exists.

The failure corpus also covers installed-Skill/project-root separation and bounded repo-local Python provisioning when no existing interpreter executes.
