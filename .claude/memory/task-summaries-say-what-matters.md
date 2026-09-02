---
name: task-summaries-say-what-matters
description: "When summarizing a task or design for another engineer, write one paragraph plus a short list of what actually matters — never an inventory of what gets touched"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f40bf551-99cf-4468-b4c5-03351848a2a8
  modified: 2026-08-26T23:48:30.305Z
---

The user asks for these to hand to a colleague who knows the domain but has read neither the spec nor the plan. Shape: **one reasonably-sized paragraph, optionally followed by a short numbered list.** Plain language. Assume domain fluency, assume zero project context.

The paragraph says what the task is for and what kind of work it is — e.g. "mostly mechanical reindexing that must reduce exactly to current behaviour in the off case". The list holds only what a reader could not deduce and would be hurt by not knowing: the behaviour that actually changes, a constraint that fixes the order of work, a trap. Two or three items at most.

Leave out: inventories of routines, files, or call sites; a component highlighted merely because it sees a large diff ("the bulk of the diff is X" was cut as unnecessary detail); process; anything already implied by the paragraph. Completeness means covering what matters, not covering everything.

**Why:** They are handing the summary to someone deciding whether they can pick the work up. An enumeration of touched code answers a question that reader does not have, and buries the two or three facts that would change how they proceed. They trimmed the same summary twice — first for length, then specifically for naming a subroutine on the strength of its change volume.

**How to apply:** Draft, then strike every sentence that only reports scope or size. What survives is the summary. Related: [[report-outcomes-not-process]], which applies the same bar to hand-offs of finished work.
