---
name: user-runs-system-test-suites
description: "Sam runs the CTSM system test suites himself — never run run_sys_tests, clm_short, or aux_clm"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f40bf551-99cf-4468-b4c5-03351848a2a8
  modified: 2026-08-19T18:10:42.534Z
---

Never launch a CTSM system test suite. `run_sys_tests`, `clm_short`, and `aux_clm` are Sam's to run, foreground or background. Verification on your side stops at the case build (`qcmd -- ./case.build`) and the pFUnit unit tests (`run_tests.py`); after those pass, hand off and wait for him to report suite results.

**Why:** these suites submit hundreds of jobs to the shared queue under his account and take hours. Launching one uninvited spends his allocation and queue priority on a schedule he did not choose.

**How to apply:** write plan verification steps as "build check and unit tests, then STOP — the user runs the suite and reports the result." Never state or predict a suite outcome he has not given you. This is in the NVP plan's Global Constraints so implementer subagents inherit it — see [[nvp-plan-subagent-dispatch-enabled]].
