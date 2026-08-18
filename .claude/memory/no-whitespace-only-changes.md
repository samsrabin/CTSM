---
name: no-whitespace-only-changes
description: Never change a line only for whitespace — no re-aligning neighbors for a longer new name, no stripping trailing whitespace on untouched lines
metadata:
  type: feedback
---

Do not modify a line when the only change is whitespace. Specifically: do not re-align an existing declaration block or `use` block so a longer new name fits, do not strip trailing whitespace from lines you had no other reason to touch, and do not reindent untouched code. Let a new line be wider than its neighbors instead.

**Why:** Whitespace-only edits inflate the diff, land in `git blame` against Sam's name, and in this repo manufacture merge conflicts with the `ctsm5.4.028_nvp` branch for no benefit. He raised it after two tasks in a row picked up this churn.

**How to apply:** Before finishing any change, verify `git diff --numstat` and `git diff -w --numstat` report identical counts for every file; if they differ, find the whitespace-only lines and restore them. This is in the NVP plan's Global Constraints so implementer subagents get it too — see [[nvp-plan-subagent-dispatch-enabled]].
