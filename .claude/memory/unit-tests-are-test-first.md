---
name: unit-tests-are-test-first
description: "Unit tests are written and committed before the implementation, by a separate agent; test commits are standalone and never amended once run"
metadata:
  type: feedback
---

Sam wants unit tests written **test-first**, not alongside or after the code. On the NVP plan this became: a dedicated test-writing subagent, dispatched after a task's Step 0 and *before* the implementer, writes the task's tests, **runs them**, and lands them in their own commit. The implementer that follows may not touch a `.pf` file, and the tests must reach green **unchanged** by the end of the task.

Two hard rules he stated as rules, not preferences:

1. **Commits that add or change unit tests are always standalone commits.**
2. **They are never `git commit --amend`ed once they have been run.** This overrides any amend-the-commit review loop: a review finding against a test becomes a new commit.

A test that has to change mid-task is a **finding**, not a formality — it means the requirement was misread before implementation started. Allowed, but it gets its own commit and is reported.

**Why:** amending destroys the evidence. The point of the early commit is that a reviewer can check it out, run the suite, and watch the test fail against the pre-change code — a mutation that was not chosen after the fact by whoever wrote the test, and one `git` can verify instead of trusting a reported binary count. Amend it and that commit stops existing; allow the test to be edited later and it silently becomes a test written to match the code.

**How to apply:** the writer labels each test red-first (behaviour the change alters — fails at the test commit) or green-throughout (behaviour the change must preserve — these still owe an explicit mutation, since red/green tells you nothing about them). `git diff <test-commit>..HEAD -- '*.pf'` coming back empty is the check. Caveat that bit us in planning: a test calling a procedure that does not exist yet is **not** a red test, it is a broken build and nothing runs — so where a change adds a new callable, its tests commit at the earliest point they compile. Related: [[nvp-plan-subagent-dispatch-enabled]].
