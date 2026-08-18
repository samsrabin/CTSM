---
name: number-your-questions
description: "Ask Sam one question at a time, or number them so he can answer each directly"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f40bf551-99cf-4468-b4c5-03351848a2a8
  modified: 2026-08-18T19:48:36.844Z
---

When putting questions to Sam, either ask exactly one, or number them (1., 2., 3.) so he can reply point-by-point. Do not bury multiple questions in prose paragraphs.

**Why:** He answers by referring to the numbers ("1. I have env vars that make the command work as written. 2. Keep the case as I set it up. 3. Sure"). Unnumbered questions scattered through prose make that impossible and cost a round trip.

**How to apply:** At any review gate that ends in questions — every task's Step 0 in [[nvp-plan-subagent-dispatch-enabled]] work, for instance — collect the questions into a numbered list at the end of the message, separate from the findings that motivated them.
