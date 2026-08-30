# CTSM Testing Skills — Design

**Status:** design, not yet implemented. Written 2026-08-30.

## What this document is

We are packaging a body of testing guidance — built up the hard way during the NVP
("moss layer") development work — into a form that any CTSM developer working with an
LLM assistant can pick up and use.

Today that guidance lives in a single file, on a single branch, in a single checkout: the
"Global Constraints" section of `.claude/plans/2026-08-18-nvp-stub-implementation-of-velvety-harp.md`.
It is good material. It is also invisible to every other piece of CTSM work, including the
same person's other checkouts.

This document explains what we are extracting, why those particular pieces, and in what
order. It deliberately contains no implementation steps.

**Audience:** someone who understands unit testing in general, but not necessarily CTSM's
unit testing, and who may be new to how Claude is configured. Terms are defined below.

---

## Terms

### Claude-side terms

**Claude Code** — the command-line tool that runs Claude as a coding assistant inside a
repository. Everything below is configuration for it.

**Context window** — the working memory of a single conversation. Everything the assistant
has been told competes for the same finite space, so *what gets loaded, and when* is a real
design question rather than a detail. This is the central constraint behind most of the
choices in this document.

**`CLAUDE.md`** — a file of instructions that is loaded into **every** conversation,
automatically. Good for short, always-relevant rules. Bad for large reference material,
because it costs context whether or not the conversation needs it.

**Skill** — a self-contained folder holding a `SKILL.md` file: a reference guide for a
technique, pattern, or tool. Unlike `CLAUDE.md`, a skill is **loaded on demand**. Each skill
carries a one-line `description` saying *when* it applies; the assistant reads those
descriptions, decides which skills are relevant to the task at hand, and loads only those.
This is the key property: a 300-line reference can exist without costing anything until the
moment it is needed.

Skills can be installed for one user (in their home directory), or committed into a
repository so that everyone working in that repository gets them. We are doing the latter.

**Memory** — a short note recording a fact about a specific person, project, or working
relationship ("this developer prefers X", "this project is blocked on Y"). Memories live in
the repository under `.claude/memory/` and an index of them is loaded every session. Memories
are for *context*, not for *technique*.

**Hook** — a small program that runs automatically at a fixed point in the assistant's
operation. A `PreToolUse` hook runs *before* the assistant is allowed to take an action, and
can block it. Where a skill says "please don't do X", a hook makes X impossible. Hooks are
for mechanical rules; skills are for judgment.

**Subagent** — a separate, fresh Claude instance dispatched by the main conversation to do
one bounded piece of work, which reports back when done. It starts with no knowledge of the
parent conversation beyond what it is explicitly handed. This matters a lot below: anything a
subagent needs to know must either be pasted into its instructions or be discoverable by it
as a skill.

**Plan file** — a working document in `.claude/plans/` describing a piece of work in enough
detail to execute it task by task. The NVP plan is one; this document is another.

**superpowers** — a third-party collection of skills, already installed here, covering general
software practice: test-driven development, code review, planning, and so on. Relevant
because we should extend it rather than duplicate it.

### CTSM-side terms

**pFUnit** — the unit testing framework CTSM uses for Fortran. Test files have a `.pf`
extension and are run through a preprocessor before compilation.

**CIME** — the infrastructure layer that builds and runs the model. It also provides CTSM's
**system tests**: whole-model runs, checked for things like "did it complete" and "did the
conservation checks stay closed". A system test is defined by an entry in a test list, and its
configuration is layered on by small namelist fragments called **testmods**.

**Baseline** — a saved set of outputs from a previous run, used to detect whether a change
altered results that were supposed to stay identical.

**Test suite** — a named collection of system tests submitted together. CTSM's suites submit
hundreds of jobs to a shared HPC queue and take hours.

---

## The problem

Four things are wrong with the status quo.

1. **The guidance is trapped.** It lives in one branch's plan file. Another CTSM checkout —
   even the same developer's — cannot see it. Another CTSM developer certainly cannot.

2. **It is loaded at the wrong times.** The plan pastes the whole ~90-line constraints block
   into every subagent dispatch, including tasks that touch no tests at all, while any
   conversation *outside* that plan gets none of it.

3. **It is mixed together.** Genuinely universal practice ("a test that has to change
   mid-task is a finding, not a formality"), CTSM-specific mechanics ("adding a `.pf` file
   requires clearing the test build directory first, or the runner silently executes the old
   set of tests"), and NVP-specific facts ("this test site has no lake or glacier landunit")
   all sit in one list. Only the first two kinds should travel.

4. **It was expensive to learn.** Much of it is annotated with how it was discovered — "found
   the hard way", "corrected by the user", "this happened at Task 5b". Leaving that where only
   one branch can see it wastes it.

Skills solve all four: they are committed to the repository, loaded only when relevant,
separable by scope, and readable by anyone.

---

## What we are building

Four skills. Names are provisional and will be settled when each is written.

### C. `ctsm-unit-tests` — CTSM-specific reference

*How to build, run, and write a pFUnit test in CTSM, and what will bite you.*

Covers the mechanics of running the unit test suite, including a trap in which re-running the
tests incrementally silently executes the *previous* set of tests while reporting complete
success; the build configuration the tests actually compile under, including several places
where the documented behaviour and the real behaviour differ (one compiler check is silently
disabled by a later flag; another setting turns a divide-by-zero into an immediate abort
rather than a NaN); two hard limits in the pFUnit preprocessor that produce baffling compile
errors; the inventory of test fixtures CTSM already provides, so that nobody rebuilds one; how to
hand-build the few structures that have no fixture; and how to run a single test over several
different inputs, a pFUnit capability CTSM supports but has never once used, so there is no
example in the codebase for anyone to copy.

**Why it is not project-specific:** it applies to every CTSM checkout and every CTSM
developer. It is specific to CTSM, but CTSM is not a project — it is a codebase many projects
happen inside.

### A. `writing-tests-before-the-implementer` — universal discipline

*Test-driven development when a different agent writes the tests than writes the code.*

The arrangement: a dedicated test-writing agent runs before the implementing agent, writes
and runs the tests, and commits them on their own. The implementer that follows is told it
may not edit a test file — making the tests pass without touching them is the job.

The supporting rules make that arrangement mean something. Tests are labelled by what kind of
evidence they carry: a test of behaviour the change *alters* must fail at the test commit and
pass at the end, and those two commits are the proof — anyone can check out the first one and
watch it fail. A test of behaviour the change must *preserve* is green throughout, so
red/green proves nothing about it and it owes a mutation instead: break the thing under test,
confirm that specific assertion fails, restore it, report which assertion caught what. Test
commits are standalone and never amended, because amending destroys exactly the commit a
reviewer would check out. And at the end of a task, the diff of test files from the test
commit to the final commit must be empty — that is the guarantee that no test was quietly
reshaped to match the code that was eventually written.

**Why this is worth writing down:** the existing `superpowers` skills do not cover it.
Their test-driven-development skill assumes one agent writing tests and code in alternation.
Their subagent-driven-development skill assumes one implementer per task who "implements,
tests, commits". Neither has a separate test author, the red-evidence commit, or the
anti-retrofit check. This is an addition to that family, and it cross-references both.

**Why it matters more than it sounds:** in the NVP work, most tasks are small index
rewrites where what the code does and what the code *should* do look identical to a reader.
A test written after the implementation encodes the bug just as readily as the fix.

### D. `ctsm-system-tests` — CTSM-specific reference

*How to add or change a CTSM system test, and who is allowed to run the suites.*

Covers what a system test can and cannot actually assess, and the resulting rule to prefer a
unit test wherever the requirement can be reached that way; how to register a test and how
test names work, since the full name is the key used for both baselines and for the
expected-failures list; the mechanism for landing a test before the capability it tests
exists, and the trap of doing that to a test that is also serving as a baseline reference;
several testmod rules that fail silently when got wrong; which machine and compiler
combinations catch which classes of bug; how to derive a wallclock limit from existing
entries rather than guessing it; how to verify a change by building a case, including a cache
refresh the build system does not perform for you when a source file is added; and when a
commit may still be amended and when it may not.

This skill also absorbs a rule about who runs the suites — see below.

### B. `designing-unit-test-cases` — universal judgment

*What makes a test case actually pin something down, and how to make it readable.*

Two halves.

**Fixtures that do not test what you think.** A fixture that holds some dimension constant,
equal, or symmetric is blind to a whole class of bug along that dimension. Identical per-slot
values hide indexing errors. Markers built as a product collide, so a transposition is
invisible. A scale factor of one makes both legs of a scale-and-unscale operation the
identity, so dropping either is invisible. A configuration already at capacity cannot
demonstrate a cap. And the subtlest: a fixture that is a *fixed point* of the transformation
being tested — where applying the transformation one step too far reproduces the fixture
exactly — gives a guard against over-application zero coverage.

**Tests a human can read.** Name a test for the condition it exercises and the code path that
condition drives, never for an input value — a number in a name means nothing to a reader who
has not memorised the threshold it is meant to exceed, and it goes stale when the threshold
moves. Where two tests differ along one axis, name that axis in both. Open every test with a
one-sentence summary that stands alone, contains no numbers, and says what the routine under
test must do rather than what the test code does. Give the quantities a test depends on names
instead of bare literals. State what an array's dimensions are.

**Why it is separate from A:** the two trigger at different moments — A when structuring a
task, B when actually writing a file — and separate descriptions are found more reliably than
one merged one.

---

## What stays behind

Everything keyed to the NVP work stays in the NVP plan: the required set of NVP system tests
and the facts about the test site that force it; the cold-start requirement and the restart
variable behind it; the NVP-specific suite categories; the local convention that "stock"
means a column without a moss layer; and the specific argument about which balance check is
skipped on the timestep a snow layer dissolves.

The test for whether something travels is simple: **would this still be true, and still be
useful, to a CTSM developer who has never heard of the moss layer?**

---

## Two memories, absorbed

Two existing memories in `.claude/memory/` turn out to be skill content rather than context.

The rule for telling them apart: **a memory earns its place when the fact is about *this*
person, *this* project, or *this* working relationship. Strip the attribution and the dates;
if what remains still stands on its own, it was skill content wearing a memory's clothes.**

**`unit-tests-are-test-first`** is skill A almost in full, with attribution attached. Every
rule in it comes with a stated mechanism that survives the strip. Its substance moves into A
and the memory retires — a memory that duplicates a committed skill is a drift hazard, and the
copy loaded every session is the one that goes stale unnoticed.

**`user-runs-system-test-suites`** reads as a personal preference but is not one. Its
justification is that a suite submits hundreds of jobs to a shared queue, billed to a named
human's allocation, for hours, on a schedule that human owns. That is true for every CTSM
developer without modification. Its substance moves into D: an assistant may verify a change
as far as the build and the unit tests, and then hands off — it does not launch a suite, and
it never characterises a suite result it was not given.

---

## One hook

The suite rule has a **triggering mismatch**. Skill D naturally announces itself when someone
is *authoring* a system test, but the moment the rule is needed is when an assistant has
finished a change and is reaching for a way to verify it — which may not look like a
system-test task at all, and so may not load D.

Two fixes, both worth doing. Widen D's description so it also announces itself for verifying
a CTSM change, not only for adding tests. And add a `PreToolUse` hook that blocks the suite
launch commands outright.

This follows a principle from the skill-authoring guidance we are using: if a rule is
enforceable by pattern-matching, automate it, and save documentation for judgment calls. The
suite launcher names are a fixed, short list. That is a hook, not a paragraph.

---

## One upstream documentation fix

CTSM's own unit-testing document, `src/README.unit_testing`, is eleven lines long and its
substance is a recommendation to reuse the existing build directory for an incremental
rebuild. That is exactly the practice that silently runs the previous set of tests after a new
test file is added. The documentation steers the reader into the trap and presents it as a
feature.

That is a bug affecting humans, not only assistants, so it gets fixed in CTSM rather than
merely documented around in a skill. The fix is a brief note in that file.

The two changes are complementary rather than redundant: the README serves the reader who opens
it, and the skill triggers on the *symptom* — a test count that did not change — for the reader
who did not. We are not running a control to measure how much each contributes on its own,
because the README note is warranted for human readers whatever it does for an assistant.

## Where they live

Committed into this repository under `.claude/skills/`, one folder per skill.

This checkout is a **staging area**. The finished skills get copied to a separate branch
where the broader "LLM-assisted development in CTSM" work is happening, and from there
proposed to the wider project. Two consequences for how they are written:

- Nothing NVP-specific and nothing person-specific may survive into the skill text, so that
  each one transplants cleanly.
- Repository-committed skills version alongside the code they describe. When the unit test
  runner changes, the skill describing it can change in the same pull request. This is the
  main argument for committing them rather than installing them per-user.

---

## How we will build them

Skills are documentation, but they are documentation whose only purpose is to change
behaviour — which means they can be tested, and the guidance we are following insists that
they are. The shape is the same as test-driven development:

1. **Observe the baseline first.** Give an agent a realistic task *without* the skill and
   record what it actually did: where it went wrong and how it justified itself — and, where it
   went right, what the right answer cost it. Build jobs submitted, compile errors hit,
   wall-clock, and which facts it had to derive that the checkout could simply have handed it.
2. **Write the guidance**, leading with whatever the baseline showed was scarce.
3. **Verify against the same measure the baseline used**, then close the gaps. Where the
   baseline was a failure, re-run and answer any new evasion explicitly. Where it was a success
   that cost too much, re-run and check that the cost fell. A skill that moves neither is a
   finding about the skill, not about the agent.

**A deliberate departure from the guidance we are following.** The skill-authoring guidance
says a rule whose baseline agent already gets it right should not be written at all. We are
keeping such rules, marked in the plan as not proven necessary, because a single agent getting
something right once is weak evidence that agents get it right reliably — these models are
stochastic, and the cost of a rule that turns out to be redundant is much lower than the cost
of a trap that reappears on a bad day. The mark is recorded in the plan's evidence appendix and
**not** in the skill text, because a rule annotated "this may be unnecessary" invites the
reader to skip it. The appendix then doubles as the worklist for a later pruning pass, once
there is enough evidence to prune on — but **not on the proven/unproven axis**. Pruning on "did
an agent fail without this" would cut the time-saving facts first, and those are the ones that
pay off on every run rather than only in the fraction of runs where an agent goes wrong. Prune
on whether a fact ever gets used.

**A baseline that succeeds is a result, not a null.** Recorded here because it was a surprise,
and because it should shape A, B and D rather than being rediscovered from scratch each time.
C's six baselines, run 2026-08-30, came back five-of-six with the agent doing the right thing
unaided: it found the water-type fixture factory and got its call order right first try, read
the whole compiler flag line instead of stopping at the first match, and reached for pFUnit's
parameterized-test decorator with no example anywhere in the codebase to copy. What those agents
lost was submitted build jobs. Counted from the transcripts afterwards, the two scenarios that
hit a trap — an incremental rebuild that reported complete success while running the previous set
of tests, and a preprocessor limit whose rule was sitting unremarked in the neighbouring test
file — cost seven and nine PBS jobs, against two or three for each of the other four. Those two
were also the largest writing tasks, so job count confounds task size with trap cost; what is
unconfounded is that only the preprocessor scenario produced a compile error at all. Reaching for
an unfamiliar tool was *not* expensive: the scenario that derived parameterized-test syntax from
the pFUnit preprocessor's own source, with no example in the codebase, cost three jobs. For a reference skill, then, "did the agent fail?" is the wrong question
and produces a table of unproven rules; "what did the right answer cost, and how much of that
was avoidable?" is the one that discriminates.

This does not automatically transfer. A is classified below as a discipline skill and B as a
pattern skill, and both may behave quite differently under a baseline — an agent that skips
writing a test first is failing, not paying. But the classification is a prediction, and each
skill's baseline should be read as a test of it rather than as a confirmation.

The *design* of step 1 differs by what kind of skill it is, and this is the part worth stating
up front:

| Skill | Kind | What its baseline test looks like |
|---|---|---|
| C | Reference | Can an agent find the right fact and apply it? Where are the gaps? |
| A | Discipline | Does an agent hold the line under pressure — time, sunk cost, a failing test sitting in front of it? |
| D | Reference, with judgment | Retrieval and gap testing, plus pressure testing on the rules that ask for restraint |
| B | Pattern | Does an agent recognise when the pattern applies, and apply it correctly? |

Two further notes.

**Wording matters where guidance competes with an incentive.** Rules like "prefer a unit test
to a new system test type" ask an agent to do less than it wants to. Guidance of that kind
gets its exact wording tested against a no-guidance control, several times over, because
single samples are not informative. Rules that merely state a fact — a command, a flag, a file
path — do not need this.

**Skill B needs a human gate.** Whether a test's one-sentence summary is genuinely readable is
a taste judgment, and an agent scoring its own output on readability is close to worthless.
B is cheap in agent time and expensive in reviewer time; that is worth knowing before we
reach it.

---

## Order

1. **C — `ctsm-unit-tests`.** First because it is immediately useful on unrelated CTSM work,
   and because it is the most self-contained: mostly facts, verifiable by running things.
2. **A — `writing-tests-before-the-implementer`.** Second because the NVP plan depends on it
   and has ten-plus tasks still to run.
3. **D — `ctsm-system-tests`.** Third; also absorbs a memory and gains a hook, so it is the
   largest in scope.
4. **B — `designing-unit-test-cases`.** Last because it needs the most reviewer attention.

Each is planned and built one at a time, not batched. All four are intended to land before the
NVP branch does.

---

## Open questions and risks

**Whether the NVP plan switches over to skill A mid-flight.** Authoring A is not the same
decision as making the remaining NVP task dispatches depend on it. The argument for *not*
switching: a subagent that fails to load a CTSM reference skill fails loudly — the build
breaks, or the test runner reports something obviously wrong — whereas a subagent that fails
to load A fails silently, because a test retrofitted to the implementation still passes.
Current default is to write A, commit it, and leave the NVP plan's inline copy in place until
that branch lands, with the skill marked canonical. Not yet decided.

**Drift between the plan's inline copy and the skill.** A consequence of the above, and the
reason it should not be a permanent arrangement.

**Discoverability from a subagent.** A subagent only knows what it is handed or what it finds.
Skill descriptions have to be good enough that the right one is picked up without being named,
and dispatches that depend on a skill should say so explicitly.

**Acceptance by the wider project.** Out of scope here. These are being written to be
proposable, not proposed.
