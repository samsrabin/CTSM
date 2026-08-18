---
name: nvp-plan-subagent-dispatch-enabled
description: Sam authorized subagent dispatch for the NVP stub plan; use fresh implementer and reviewer subagents per task
metadata: 
  node_type: memory
  type: project
  originSessionId: f40bf551-99cf-4468-b4c5-03351848a2a8
  modified: 2026-08-18T19:48:45.856Z
---

On 2026-08-18 Sam authorized this session to dispatch subagents as needed for the NVP stub implementation, overriding the default "don't spawn agents unless asked" posture. The plan's Execution Process depends on it: a fresh implementer subagent per task, then two reviewer subagents (spec-compliance, then code-quality).

**Why it needed saying:** the session was configured not to call the Agent tool unless the user requested it, which conflicted with the plan's mandated workflow. The authorization is standing for this work.

**How to apply:** dispatch per the plan. The implementer receives only its own task's text (as amended by that task's Step 0), the spec path, the harvest-worktree path, the checkout path, and the Global Constraints — never the whole plan, never the Self-Review section. Step 0 itself is never delegated: subagents cannot ask Sam anything. See [[number-your-questions]] for how to put Step 0's findings to him.
