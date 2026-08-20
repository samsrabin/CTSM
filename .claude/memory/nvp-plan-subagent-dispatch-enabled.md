---
name: nvp-plan-subagent-dispatch-enabled
description: Sam authorized subagent dispatch for the NVP stub plan; use fresh implementer and reviewer subagents per task, and re-dispatch rather than taking the work over yourself
metadata:
  node_type: memory
  type: project
  originSessionId: f40bf551-99cf-4468-b4c5-03351848a2a8
  modified: 2026-08-20T14:16:03.758Z
---

On 2026-08-18 Sam authorized this session to dispatch subagents as needed for the NVP stub implementation, overriding the default "don't spawn agents unless asked" posture. The plan's Execution Process depends on it: a fresh implementer subagent per task, then two reviewer subagents (spec-compliance, then code-quality).

**Why it needed saying:** the session was configured not to call the Agent tool unless the user requested it, which conflicted with the plan's mandated workflow. The authorization is standing for this work.

**Re-dispatch; do not take the work over.** On 2026-08-20 a fix subagent's process died before it ran, leaving the tree untouched. I started applying its ~10 fixes by hand instead. Sam interrupted: *"Please re-dispatch the agent rather than doing it yourself. And remember to do that in the future as well."* When a subagent is lost, stopped, or returns nothing, re-dispatch the same prompt — the orchestrator's job is dispatching and adjudicating, not doing implementation work. Reading files to verify a claim or to write a dispatch prompt is fine; editing the target files is not.

**How to apply:** dispatch per the plan. The implementer receives only its own task's text (as amended by that task's Step 0), the spec path, the harvest-worktree path, the checkout path, and the Global Constraints — never the whole plan, never the Self-Review section. If the tree already carries orchestrator edits (plan, MERGE_NOTES), tell the agent explicitly to leave those files alone. Step 0 itself is never delegated: subagents cannot ask Sam anything. See [[number-your-questions]] for how to put Step 0's findings to him.
