---
name: report-outcomes-not-process
description: "Hand-offs carry the end state, what is outstanding, and what needs a decision — nothing about review rounds, fix rounds, or how the work got there"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f40bf551-99cf-4468-b4c5-03351848a2a8
  modified: 2026-08-21T22:46:47.901Z
---

Leave the process out of a hand-off entirely. Nothing about what a review stage caught, what changed between amendments, which agent found what, what you verified yourself versus took on report, or whether the reviews were worth running. Two narrow exceptions: a review outcome that changed the plan, and anything you need to ask the user about.

The bar is higher than "keep it brief". Asides framed as "two things worth knowing" — a defect that turned out to appear twice, an accepted exception to a mechanical gate — do not clear it. If it would not change what they do next, it does not go in.

**Why:** They review the commits themselves, so intermediate history is noise they must read past to reach the parts that need them. They have raised this twice: first when a hand-off led with review findings and a "the review earned its keep" paragraph, then again when a trimmed version still carried a round-by-round summary and two process footnotes.

**How to apply:** Three parts only — what the change now does, what is outstanding, what needs a decision. Verification results stay: they are end state, not process. Keep them to the result (counts, pass/fail), never the procedure that produced them. See [[number-your-questions]] for the decisions part and [[no-dispatch-while-a-question-is-open]] for when to stop.
