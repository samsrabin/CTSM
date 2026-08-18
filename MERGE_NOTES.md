# MERGE_NOTES — NVP stub (`use_nvp`) branch

Working notes for merging this branch into `ctsm5.4.028_nvp`. Every deliberate
divergence from that branch gets a row in "Intentional merge conflicts" as the
task that creates it lands, so the merge rehearsal (Task 17) has a checklist to
compare the real conflict set against.

Plan: `.claude/plans/2026-08-18-nvp-stub-implementation-of-velvety-harp.md`
Spec: `.claude/plans/this-is-the-community-velvety-harp.md` (governs on conflict)

## Workspace

| | |
|---|---|
| Checkout | `/glade/work/samrabin/ctsm_hui-moss-permanent-nvp-layer` |
| Working branch | `hui-moss/permanent-nvp-layer`, based on the `ctsm5.4.028` tag |
| Harvest worktree (read-only) | `.worktrees/ctsm5.4.028_nvp`, detached at `103082a17` — the commit the spec audited, so its `:NNNN` line references hold verbatim |
| Build-check case | `test-bld/` (FATES compset, `DEBUG=TRUE`, 10x15) |

`test-bld` and `.worktrees` are listed in `.gitignore` under "DELETE THESE BEFORE
MERGING" — neither belongs in the merge.

## Verification commands

Run before every commit. Unit tests are required for any commit touching Fortran.

Build check:

```bash
cd test-bld && qcmd -- ./case.build
```

Unit tests:

```bash
cd src && qcmd -- ../cime/scripts/fortran_unit_testing/run_tests.py --build-dir unit_tests.temp
```

Namelist-touching tasks additionally run `bld/unit_testers/build-namelist_test.pl`.

**Intermediate commits are only expected to hold for `use_nvp = .false.`.** The
`use_nvp = .true.` path is not coherent until the full task stack has landed —
`jbot_sno` is set (Task 3) before the snow lifecycle is reindexed to respect it
(Task 5), among others. `use_nvp=T` validation belongs to Task 17.

## Verification results

Filled by Task 17. One row per spec §10 gate.

| Gate | Configuration | Result |
|---|---|---|
| Bit-for-bit vs `ctsm5.4.028` | `use_nvp=.false.` | |
| Golden zero-thickness | `use_nvp=T, dz_nvp=0, frac_nvp=0` vs `use_nvp=F` | |
| Partial-cover closure | `frac_nvp=0.3`, `0.7`, winter-crossing | |
| Exact restart | `ERS`, `use_nvp=T, dz_nvp>0` | |
| Merge rehearsal | trial merge into `ctsm5.4.028_nvp` | |

## Intentional merge conflicts

Where this branch deliberately differs from `ctsm5.4.028_nvp`. "Resolution"
records which side wins at merge time.

| File | Why ours differs | Resolution |
|---|---|---|

## Deferred items

Out of scope for the stub; recorded in spec §8 with full rationale.

| Item |
|---|
| Global (non-per-column) `jbot_sno` with uniformly shifted special columns |
| Dynamic (FATES-prognostic) thickness with conservation |
| Beer's-law transmissivity + SNICAR layer-0 optics |
| FATES-side fractional-cover aggregation fix |
| Clean aerosol pass-through-and-discard (un-strand the moss slot) |
| Non-overloaded restart + init_interp third-segment support |
| Water-tracer support for NVP fluxes |
| NVP↔soil interface heat-flux history field |
