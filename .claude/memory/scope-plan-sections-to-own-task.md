---
name: scope-plan-sections-to-own-task
description: "Keep each per-task plan section scoped to its own task; when corrected, fix the instance rather than documenting a rule against it"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f40bf551-99cf-4468-b4c5-03351848a2a8
  modified: 2026-08-18T18:51:58.452Z
---

In a plan with per-task review gates, each task's section covers that task and nothing else. Do not front-load later tasks' open questions, known issues, or cleanup notes into an earlier task's section.

**Why:** A per-task gate exists so a question gets answered when the relevant code is in front of you and the tasks it depends on have landed. Hoisting those questions into Task 0 asks the user to decide without the context that would make the decision good, and defeats the gate.

**How to apply:** Put each concern in the section that owns it. When the user corrects a mistake like this, fix that specific instance only — do not also add a defensive rule, scoping note, or meta-commentary to the document to keep it from recurring. That over-reach is the same error one level up: they interrupted exactly that follow-up edit.
