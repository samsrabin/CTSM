---
name: match-the-merge-target
description: On the NVP stub branch, matching ctsm5.4.028_nvp outranks avoiding CTSM-side breakage; submodule pointers included
metadata:
  node_type: memory
  type: project
  originSessionId: f40bf551-99cf-4468-b4c5-03351848a2a8
  modified: 2026-08-27T00:00:00.000Z
---

The `hui-moss/permanent-nvp-layer` branch exists to be merged into
`ctsm5.4.028_nvp`. Minimizing the conflict set is the governing constraint, so
where a choice is neutral-to-bad for stock CTSM but matches the merge target,
**match the merge target.** The spec states this for design conventions; it
applies to submodule pointers too.

Concrete case, 2026-08-27: I recommended dropping the `cdeps` bump to
`42f9a6b06` because it rewrites the shared `CLM_USRDAT` 1PT stream into three
split streams and changes the forcing-file pattern to something that does not
match the files on disk, and because the ALP2 compset is `DATM%GSWP3v1` and does
not need it. The user: *"No, keep the cdeps changes. Remember that the entire
point of our branch is that we will eventually merge it into the NVP branch,
which (trust me) uses the same ccs_config and cdeps as what I'm telling you to
use."* Verified: `ctsm5.4.028_nvp` pins `ccs_config` at `b6387972b` (fork
`samsrabin/ccs_config_cesm`) and `cdeps` at `42f9a6b06`, in both `.gitmodules`
and the gitlinks.

**Posture on the resulting risk:** add no `ExpectedTestFails.xml` entries in
advance for a submodule bump. If the next `aux_clm` or `fates` run produces
unexpected failures, these submodule updates are the first thing to check.
Speculative expected-fail entries would only mask the signal.

**How to apply:** before recommending we diverge from `ctsm5.4.028_nvp` on
anything, check the worktree at `.worktrees/ctsm5.4.028_nvp` for what it does,
and say what the merge cost of diverging would be. "This would break a stock CTSM
test" is a fact worth reporting, not a reason to diverge on its own. Related:
[[nvp-plan-subagent-dispatch-enabled]].
