# Working conventions for this branch

These are project conventions, not stylistic preferences. Each exists because
violating it has cost time, destroyed a measurement, or manufactured merge
conflicts here.

## The merge target governs

`hui-moss/permanent-nvp-layer` exists to be merged into `ctsm5.4.028_nvp`.
Minimizing the conflict set with that branch is the governing constraint, so
where a choice is neutral-to-bad for stock CTSM but matches the merge target,
**match the merge target** — for design conventions and for submodule pointers
alike. `ctsm5.4.028_nvp` pins `ccs_config` at `b6387972b` (fork
`samsrabin/ccs_config_cesm`) and `cdeps` at `42f9a6b06`, in both `.gitmodules`
and the gitlinks; this branch matches those deliberately, even though the
`cdeps` bump rewrites the shared `CLM_USRDAT` 1PT stream into three split
streams whose forcing-file pattern does not match the files on disk. The ALP2
compset is `DATM%GSWP3v1` and is unaffected by that.

Before proposing that we diverge from `ctsm5.4.028_nvp` on anything, check the
worktree at `.worktrees/ctsm5.4.028_nvp` for what it does, and state the merge
cost of diverging. "This would break a stock CTSM test" is a fact worth
reporting, not a reason to diverge on its own.

Add no `ExpectedTestFails.xml` entries in advance for a submodule bump. If an
`aux_clm` or `fates` run produces unexpected failures, the submodule updates are
the first thing to check; speculative expected-fail entries would only mask that
signal.

## No whitespace-only changes

Do not modify a line when the only change is whitespace: no re-aligning an
existing declaration or `use` block so a longer new name fits, no stripping
trailing whitespace from lines you had no other reason to touch, no reindenting
untouched code. Let a new line be wider than its neighbours instead.

Whitespace-only edits inflate the diff, land in `git blame` against whoever made
them, and manufacture merge conflicts with `ctsm5.4.028_nvp` for no benefit.
Before finishing any change, check that `git diff --numstat` and
`git diff -w --numstat` report identical counts for every file; if they differ,
find the whitespace-only lines and restore them.

## Tasks run strictly in order

Every task in a plan is order-critical: Task N+1 does not begin until Task N is
finished, even when the two touch different files. Finishing a task can change
what a later task is measuring — running a baseline after the fix it is meant to
baseline destroys the measurement with no way to recover it — and overlapping
tasks make a review gate meaningless, because the reviewer can no longer tell
which task produced what.

Write plans so each task ends with an independently reviewable deliverable, and
do not batch or interleave, even to save a dispatch. Where an ordering is
load-bearing rather than merely conventional, say so *in the plan* and say what
breaks if it is violated; a plan that only implies its ordering will get
reordered by someone optimizing for parallelism.

## Each plan section covers its own task

In a plan with per-task review gates, each task's section covers that task and
nothing else. Do not front-load later tasks' open questions, known issues, or
cleanup notes into an earlier section. A per-task gate exists so a question gets
answered when the relevant code is in front of you and the tasks it depends on
have landed; hoisting the question into Task 0 asks for a decision without the
context that would make it a good one.

When a mistake like this is corrected, fix that instance only. Do not also add a
defensive rule, scoping note, or meta-commentary to the document to keep it from
recurring — that over-reach is the same error one level up.

## A failed verification is a stop

Distinguish two kinds of negative result.

A **claim that turns out false** — a trap that no longer reproduces, a
documented behaviour that is not real — has one action: cut it, record it,
report it, keep going. A false claim is never retained as merely unproven.

A **capability that does not work** is a stop. When a step that exists to
confirm something comes back negative, and the consequence is that the
deliverable can no longer do what it was scoped to do, stop and report it. Do
not pick a fallback: documenting the failure as a known limitation, dropping the
affected section, and working around it are the same move — shrinking the
deliverable without the user ever choosing that. Whether to fix the
infrastructure, proceed with a caveat, or wait depends on things only they know,
and a negative result is often a finding about the codebase rather than about
the task.

Write this distinction into plans explicitly, at the step, since the default
pull is to route around and keep momentum.

## Do not dispatch while a question is open

When you put a question to the user, that turn ends. Do not dispatch a subagent,
start a build, or begin edits alongside it, and do not answer your own question
and carry on — even when the pending question looks carved out of the work you
want to start. "The rest is independent" is not a reason: an agent editing the
same files while the user is reasoning about the question makes the thing they
are reasoning about a moving target.

Before any dispatch, check whether an unanswered question is outstanding —
including one where the user asked for more explanation rather than deciding,
which is not an answer. If so, send the explanation alone and stop. Batch
questions so the wait happens once.

## Subagent dispatch mechanics

Dispatching subagents at all requires the user's authorization; it is not a
project default. Where a plan's execution process does call for them (a fresh
implementer per task, then reviewers):

- An implementer receives only its own task's text as amended by that task's
  review gate, the spec path, the harvest-worktree path, the checkout path, and
  the plan's Global Constraints — never the whole plan, never the Self-Review
  section. If the tree already carries orchestrator edits (the plan itself,
  `MERGE_NOTES.md`), tell the agent explicitly to leave those files alone.
- A task's review gate is never delegated: subagents cannot ask the user
  anything.
- When a subagent is lost, stopped, or returns nothing, re-dispatch the same
  prompt. The orchestrator dispatches and adjudicates; it does not take over the
  implementation work. Reading files to verify a claim or to write a dispatch
  prompt is fine; editing the target files is not.
- Long, deep, read-heavy investigation goes to a subagent as well, on Opus,
  passed as `model: "opus"` explicitly rather than by inheritance, since an
  agent definition can carry its own model. Split it so each agent owns a
  bounded, checkable piece and returns findings the orchestrator adjudicates.

## Summaries written for another engineer

A summary of a task or design for another engineer — someone fluent in the
domain who has read neither the spec nor the plan — is one reasonably-sized
paragraph, optionally followed by a short numbered list. Plain language, assume
domain fluency, assume zero project context. The paragraph says what the task is
for and what kind of work it is, e.g. "mostly mechanical reindexing that must
reduce exactly to current behaviour in the off case". The list holds only what a
reader could not deduce and would be hurt by not knowing: the behaviour that
actually changes, a constraint that fixes the order of work, a trap. Two or
three items at most.

Leave out inventories of routines, files, or call sites; a component highlighted
merely because it sees a large diff; process; anything already implied by the
paragraph. The reader is deciding whether they can pick the work up, and an
enumeration of touched code buries the two or three facts that would change how
they proceed. Draft, then strike every sentence that only reports scope or size;
what survives is the summary.

## Do not assume pronouns

Never infer anyone's pronouns — the user's, the branch namesakes', upstream CTSM
and FATES developers', issue reporters'. A name is not evidence of pronouns, and
neither is a branch name. Guessing wrong misgenders a real person; the neutral
default never does.

Address the user in the second person ("your branch", "the names you gave me"),
which is both correct and better writing; use they/them for third parties. This
covers commit messages, plan and spec prose, code comments, and dispatch prompts
to subagents, not just chat.
