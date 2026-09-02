---
name: no-dispatch-while-a-question-is-open
description: "Never dispatch a subagent or start work in the same turn as a question to the user — wait for the answer, even for work that looks separable"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f40bf551-99cf-4468-b4c5-03351848a2a8
  modified: 2026-08-21T22:26:58.295Z
---

When you put a question to the user, that turn ends. Do not dispatch a subagent, start a build, or begin edits alongside it, and do not answer your own question and carry on. Wait for their reply. This holds even when the pending question looks carved out of the work you want to start — "the rest is independent" is not a reason.

**Why:** They have to read and think about the question, and an agent editing the same files while they do that puts them under pressure and makes the thing they are reasoning about a moving target. They stopped a dispatch mid-flight over exactly this: I asked them to weigh in on a naming decision, then in the same message answered it myself and launched an agent on the other seven items in the same files. The NVP plan's Step 0 already says "STOP and put to the user ... proceed only after the user answers"; the failure was applying that to two of three questions and not the third, which had come back as "expand more on the situation" rather than a decision.

**How to apply:** Before any dispatch, check whether an unanswered question is outstanding — including one where they asked for more explanation, which is not an answer. If so, send the explanation alone and stop. Batch questions so the wait happens once; see [[number-your-questions]]. Related: [[nvp-plan-subagent-dispatch-enabled]] authorizes dispatching, but says nothing about *when*.
