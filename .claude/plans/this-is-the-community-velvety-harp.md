# NVP layer at index 0 — stub implementation plan (merge target: `ctsm5.4.028_nvp`)

## Context

CTSM columns stack snow layers at indices `snl(c)+1 : 0` (bottom snow always index 0) above soil layers `1 : nlevgrnd`. The goal is a **non-vascular plant (NVP — mosses, lichens) layer at index 0** when `use_nvp` is enabled. Matter and energy must be conserved at all times.

An existing implementation lives on branch `ctsm5.4.028_nvp` (audited in §9; worktree retained in the session scratchpad). It contains good physics but also structural conservation bugs, missed sites, and a disabled-validation posture. **The meta-design, per collaboration needs:** implement a corrected, minimal ("stub") NVP on a **new branch from the `ctsm5.4.028` tag**, built so it can later be **merged into `ctsm5.4.028_nvp`**. Where this plan and the existing implementation disagree on design, **we adopt the existing implementation's conventions** — with the exceptions in §1 — so that merge conflicts are minimized and the conflicts that do occur are deliberate bug-fix deliveries.

Stub scope: `use_nvp` off (bit-for-bit with `ctsm5.4.028`), or on with **constant, namelist-prescribed** NVP thickness/coverage/properties on istsoil/istcrop columns — **including `dz_nvp = 0`** (no moss biomass: the layer slot exists structurally with zero thickness and every flux skips over it). The zero-thickness state is first-class, both for testing the stub and because after the merge, FATES will produce istsoil/istcrop columns with no moss. No FATES dependency in the stub.

This is a planning document; implementation follows after approval.

---

## 0. Primer: the vertical-grid variables

All allocated in [ColumnType.F90:137-140](src/main/ColumnType.F90:137). Depths are positive downward from the soil surface; snow (above the surface) has negative depths.

| Variable | Meaning | Bounds |
|---|---|---|
| `dz(c,j)` | Thickness of layer `j` | `-nlevsno+1 : nlevmaxurbgrnd` |
| `z(c,j)` | Depth of layer `j`'s node (midpoint), where temperature/state lives | same |
| `zi(c,j)` | Depth of the **interface at the bottom of layer `j`** | `-nlevsno : nlevmaxurbgrnd` |
| `snl(c)` | Stock: −(number of snow layers); top snow layer is `snl(c)+1` | per column |

`zi(c,0)` = interface below layer 0 = **the soil surface**, hardwired to 0.0 ([initVerticalMod.F90:265,312](src/main/initVerticalMod.F90:265)). Snow geometry is rebuilt each step downward from it: `z(c,j) = zi(c,j) - 0.5*dz(c,j); zi(c,j-1) = zi(c,j) - dz(c,j)`.

Geometry with NVP (matches the existing branch): soil surface stays the 0 datum, `zi(c,0) = 0` remains true, NVP occupies depth `[-dz_nvp, 0]`, so `zi(c,-1) = -dz_nvp` is the NVP top = snow bottom, and the snow recursion — with `j=0` included — reproduces this automatically. Soil depths and the Richards solve are untouched.

---

## 1. Design decisions (final, post-review)

**Adopted from the existing implementation** (for mergeability; our original designs recorded as future changes in §8):

1. **Per-column `col%jbot_sno(c)`** (bottom-snow index: 0 or −1) and `col%nvp_layer_active(c)`, `col%dz_nvp(c)`, `col%frac_nvp(c)` — same names, same members of ColumnType. **Our modification: static assignment.** Set once at initialization: `jbot_sno = -1` on istsoil/istcrop columns when `use_nvp`, `0` everywhere else; never flipped at runtime. This keeps lakes/glaciers/wetland/urban columns literally untouched (their `jbot_sno` stays 0, all shared routines reduce to stock) while avoiding every activation/deactivation conservation bug on the existing branch.
2. ~~`snl` counts the NVP layer~~ — **superseded (user decision): we keep OUR honest `snl`.** `snl(c)` remains "−(number of snow layers)" on every column; the moss slot is *not* counted. Snow occupies `snl(c)+1+jbot_sno(c) : jbot_sno(c)`; the top snow layer is `snl(c)+1+jbot_sno(c)`, provided by a ColumnType function **`get_jtop_snow(c)`** (per our original plan). Loop bounds change algebraically (`do j = get_jtop_snow(c), col%jbot_sno(c)`) instead of relying on per-site opt-out guards, so a missed site fails loudly (wrong range) rather than silently treating moss as snow. This diverges from their branch's `snl = −(N_snow+1)` convention and will generate more merge conflicts — accepted deliberately, because the honest-`snl` scheme is intimately tied to the static-`jbot_sno` design and eliminates their `snl`-arithmetic bug class outright (`snl == -1` is again a legal state meaning one snow layer; their illegal `snl=-1 & jbot_sno=-1` state, their `snl==-1→0` fixups, and their `msno = abs(snl)-1` bookkeeping all disappear). `snl >= 0` "no snow" tests remain valid everywhere. Where their guards are keyed purely on `jbot_sno` (not on `snl` arithmetic) they still harvest cleanly.
3. **Thermal-solve layout**: NVP reuses **matrix row −1** (snow keeps the `j → j−1` map; NVP at physical 0 lands on the old bottom-snow row; ssw stays row 0; no new sub-blocks; `nband=5` unchanged). The existing snow↔soil coupling slots serve NVP↔soil.
4. **4-way subgrid split** (snow / exposed-NVP / exposed-soil / h2osfc) with their `frac_nvp_eff` formulation — adopted as equations, centralized per §4b. **Partial cover (`0 < frac_nvp < 1`) is a first-class, tested case in the stub** — including the `frac_sno_eff > frac_nvp` winter regime where their branch creates energy — so the closure fixes in §3/§4b are mandatory correctness work, not defensive hardening.
5. **Aerosol handling as theirs** (moss excluded from snow-aerosol optics/mass via their guards; the stranded-slot behavior accepted for now).
6. **Restart scheme as theirs**: NVP geometry/state rides in the existing snow restart slots (`DZSNO[0]`, `ZSNO[0]`, `ZISNO[-1]`, `SNLSNO`, `levtot[0]`), plus their `NVPLayerRestart` pattern (`DZ_NVP`, `FRAC_NVP`, `JBOT_SNO` via restUtilMod) — with `interpinic_flag` corrected to `'skip'` on `JBOT_SNO`.
7. **Names and parameters as theirs** wherever they exist: module `NVPParamsMod` (`thk_dry_nvp`, `csol_nvp`, `watsat_nvp`), module `NVPLayerDynamicsMod`, flux names (`qflx_nvp_infl_col`, `qflx_nvp_drain_col`, `qflx_nvp_to_snow_col`, `qflx_ev_nvp*`), history names (`H2ONVP`, `T_NVP`, …), guard idioms.

**Ours, for the stub** (differences from their branch — intentional merge conflicts):

8. **NVP thickness/coverage are fixed namelist parameters** (`dz_nvp`, `frac_nvp` constants applied to all NVP columns; **`dz_nvp = 0` is a supported value** meaning moss absent — the slot exists, the skip invariant (§2) governs). No FATES coupling; geometry is static for the run. Their FATES-prognostic path replaces this at merge time.
9. **Shortwave: constant transmissivity parameter.** Radiation reaching the NVP surface splits between NVP absorption and transmission to soil layer 1 by a namelist transmissivity constant. Two limiting requirements: (a) on columns where the moss layer has zero thickness, all radiation passes through to soil layer 1, exactly as if no moss existed; (b) setting the namelist transmissivity to 1 must reproduce stock energy deposition everywhere. Their Beer's-law/SNICAR machinery is deliberately NOT brought in — when our branch is merged into theirs, this stub code will conflict with their actual transmissivity code, and the resolution will be theirs. (Their SNICAR layer-0 insertion technique is the eventual home; see §9b.)
10. **No FATES requirement**: the stub's `use_nvp` works in standard CLM configurations (their build-namelist check tying `use_nvp` to FATES will conflict at merge — deliberate; the resolution will be theirs).
11. **Balance checks stay armed, no debug output.** All `endrun`s live; nothing added to the log outside `if (use_nvp)`-guarded, rate-limited diagnostics if any.
12. **Their bugs are fixed where we touch the code** (§4/§5 flag each): these are deliberate merge conflicts whose resolution is "take ours."

**Deferred entirely** (recorded in §8): dynamic thickness conservation, fractional-cover closure proof, Beer transmissivity, init_interp support, cross-flag restart guards, clean aerosol pass-through, and the **global** variant of our `jbot_sno` scheme (the honest-`snl` half IS adopted, per decision 2).

---

## 2. The indexing contract (static per-column `jbot_sno`, honest `snl`)

- `col%jbot_sno(c)` ∈ {0, −1}, set at init from `use_nvp` and column type (−1 iff istsoil/istcrop); constant thereafter. `col%nvp_layer_active(c)` set alongside (kept for merge compatibility even though redundant — their code tests both).
- `snl(c)` keeps its stock meaning everywhere: −(number of snow layers). On NVP columns snow occupies `snl+1+jbot_sno … jbot_sno` (i.e., `snl … −1`); NVP always at 0 with `dz(c,0) = dz_nvp`, `z(c,0) = -dz_nvp/2`, `zi(c,-1) = -dz_nvp` (set at init; the snow-geometry recursions reproduce it when anchored per §4d).
- First snow layer is created **at index `jbot_sno` with `snl = -1`** (adapt their `Bulk_InitializeSnowPack` version to honest `snl`); max snow layers on NVP columns is `nlevsno-1` (their `DivideSnowLayers` cap, re-expressed without the `msno = abs(snl)-1` adjustment).
- Idiom transformations (each reduces to stock when `jbot_sno = 0`):

| Stock idiom | Replacement |
|---|---|
| `do j = snl(c)+1, 0` (snow loops) | `do j = get_jtop_snow(c), col%jbot_sno(c)` |
| `snl(c)+1` as top-layer index (~127 uses) | `get_jtop_snow(c)` |
| hardcoded bottom-snow `(c,0)` (capping, `PhaseChangeH2osfc`, `snl_btm=0`, neighbor tests) | `(c, col%jbot_sno(c))` |
| `j <= 0` / `j < 1` "is snow" tests | `j <= col%jbot_sno(c)` |
| snow slices `(:, -nlevsno+1:0)` | per-column ranges via `jbot_sno` (gathers where slices were passed) |
| geometry recursion anchor `zi(c,0)` | `zi(c, col%jbot_sno(c))` |

- **The presence predicate, as named ColumnType functions** (alongside `get_jtop_snow`): `nvp_layer_exists(c)` = `jbot_sno(c) == -1` (the slot exists — says nothing about moss); `nvp_is_present(c)` = `nvp_layer_exists(c) .and. col%dz(c,0) > 0` (moss physically present); `nvp_is_empty(c)` = `nvp_layer_exists(c) .and. col%dz(c,0) == 0` (slot exists, no moss). All NVP physics ([physics] rows in §4) and all endmember-fraction usage gate on `nvp_is_present`; guard sites use these functions rather than re-deriving the conditions inline (their branch's inline re-derivation of equivalent conditions is where several of its inconsistencies came from).
- **The skip invariant** (the core of zero-thickness support): on a column where `nvp_is_empty(c)`, snow loops still never touch index 0, moss physics never runs, moss state holds no mass or energy, and **every flux that would enter the moss is routed to its downstream target in the same timestep** (percolation → drain hand-off, dew/frost → soil layer 1, radiation fully transmitted, h2osfc couplings → soil layer 1 — i.e., the stock routing). This is the h2osfc pattern (`frac_h2osfc /= 0` guards) and is what makes conservation provable. Specific numerical hazards a zero layer creates if unguarded: divisions by `dz(c,0)` in snow physics (`bw`, compaction, percolation `vol_ice`, combine-density tests) — these need no per-site guard because they live inside snow loops whose §2 bounds (`get_jtop_snow(c) : jbot_sno(c)`) never include index 0 on NVP columns, i.e., the exclusion comes from the loop structure itself; `fact(c,0) = 0` via its `dz` factor (never use `fact`-based storage terms for a zero-dz moss — §3); degenerate geometry (`z(c,0) = zi(c,-1) = zi(c,0) = 0` — §3 interface conductances); and floor/`max()` logic spontaneously giving the layer thickness or mass (`PostPercolation` guard, harvested).
- Note `get_jtop_snow(c)` = `snl(c)+1+jbot_sno(c)`: when `snl == 0` on an NVP column it returns 0 — the moss index — which is exactly right for "surface layer" usages when moss is present, but callers using it for surface temperature/state **must fall back to soil layer 1 when the presence predicate is false** (e.g., `t_soisno(c,0)` mirrors the soil-1/interface temperature there; §3).
- Since assignment is static, there are **no activation/deactivation transitions in the stub** — the entire class of their `UpdateNVPLayer` transition bugs (water invented on appear, heat dropped on disappear, `snl` never adjusted, snow geometry zeroed on inactive columns) is out of scope by construction; a change in namelist `dz_nvp` across a restart is handled like any parameter change (with the §7 consistency check). Our `NVPLayerDynamicsMod` still provides an init routine of the same name/shape so the merge lands their FATES-driven version on top of ours.
- **Do NOT apply these transformations where index 0/1 means something else**: `j == 0` in [ch4Mod.F90](src/biogeochem/ch4Mod.F90) and the SoilBiogeochem transport solvers is an atmosphere pseudo-layer (add a clarifying comment there during implementation); soil layer 1 stays 1 everywhere; matrix row 0 is ssw (§3).
- Array allocations are unchanged (their choice, adopted): bounds stay `-nlevsno+1 : …`; the moss occupies the index-0 slot and snow capacity on NVP columns drops to `nlevsno−1`.

---

## 3. Thermal solve (adopt their layout; fix their gaps)

### How the stock solve works ([SoilTemperatureMod.F90:396-434](src/biogeophys/SoilTemperatureMod.F90:396))

The heat equation is solved implicitly for the whole column at once: unknowns are end-of-step temperatures of every snow layer, the standing surface water (ssw/h2osfc — ponded water covering `frac_h2osfc` of the column; not a stacked layer, but it holds energy and exchanges with soil layer 1), and every soil layer, stacked into one vector: `A·T = r`. Layers exchange heat only with neighbors, so `A` is banded; [BandDiagonalMod.F90](src/biogeophys/BandDiagonalMod.F90) stores `nband = 5` diagonals — each row may reference two rows above and two below. Row mapping: snow layer `j` → row `j−1` (shift exists to vacate row 0), ssw → row 0, soil `j` → row `j`. `nband` is 5 not 3 because bottom snow (row −1) physically touches soil layer 1 (row +1) — the ssw row sits between them in the matrix but not in space. Assembly is from 7 sub-blocks (`bmatrix_snow`, `bmatrix_ssw`, `bmatrix_soil` + 4 coupling blocks) in `AssembleMatrixFromSubmatrices`, documented by an ASCII sparsity diagram at :2483-2519.

### With NVP (their design, adopted)

The `j → j−1` map is kept for all `j ≤ 0`, so **NVP at physical 0 lands on row −1** — the old bottom-snow row — and bottom snow (now physical −1) lands on row −2. ssw stays row 0, soil unshifted, no new sub-blocks, `nband` unchanged; the existing snow↔soil coupling slots (span 2) now carry NVP↔soil. With honest `snl`, the top-row bookkeeping becomes uniform: `jtop(c) = snl(c) + jbot_sno(c)` — which reduces to stock (`snl`) on non-NVP columns and, on NVP columns with no snow, gives `jtop = −1` (the moss row) with **no special case**, unlike their branch. Harvest their branch/guard placement in `SetRHSVec_*`/`SetMatrix_*` (NVP `j==0` tests ordered before the generic top-layer tests; soil `j==1` branches excluded on NVP columns), re-expressing any `snl`-arithmetic in their guards via `get_jtop_snow`/`jbot_sno`.

**Fixes we apply (deliberate conflicts):**
- **`fact(c,0)` and `fn(c,0)` when `snl == 0`** — their `ComputeHeatDiffFluxAndFactor` never computes them (guard `j >= snl+1` excludes `j=0`), leaving NaN/stale values consumed by the RHS/matrix/Phasechange/energy check (their Intel floating-invalid expected-fails). Extend the guard to include `j = 0` on NVP columns.
- **Moss↔soil conduction closure**: their moss-side weight (`frac_nvp`) and soil-side weight (`frac_sno_eff + frac_nvp_eff`) disagree outside `frac_sno_eff ≤ frac_nvp ≤ 1−frac_h2osfc`, creating energy every winter timestep when snow cover exceeds moss cover. Partial cover (`0 < frac_nvp < 1`) is first-class in the stub — including exactly that regime — so the weights must match identically for **all** admissible fractions: one derivation, used on both sides (a mandatory fix, not hardening).
- **`frac_h2osfc` double-subtraction** on NVP columns (their `frac_soil` already removes it; the stock trailing block removes it again) — make the NVP branches consistent with the stock convention.
- **`PhaseChangeH2osfc` `snl==0` branches** still overwrite `t_soisno(c,0)` — the moss temperature — with `t_h2osfc` (their `snl<0` reroutes are correct; harvest those). Reroute the `snl==0` cases too.
- **`errsoi` weighting**: their energy check weights moss storage 1.0 while the solve/Phasechange weight it `frac_nvp` — use one convention (per their per-moss-area `cv`, the column-level storage term is `frac_nvp·ΔT/fact`).
- Update the sparsity diagram and `SetRHSVec` docs for the NVP row (their branch left them stale, and stale comments caused at least one of their bugs).

### Zero-thickness moss (`dz_nvp = 0`) in the solve — explicit handling

When `jbot_sno(c) == -1` but `dz(c,0) = 0`, the geometry is degenerate (`z(c,0) = zi(c,-1) = zi(c,0) = 0`) and the moss node stores nothing. The row handling:

- **The moss row stays in the matrix** (deleting it would make the snow(row −2)↔soil(row 1) coupling span 3 rows and break `nband=5`). Its equation becomes a **flux-continuity (zero-heat-capacity node) equation**: `F_snow→moss − F_moss→soil = 0`, with the two conductances measured node-to-interface using the snow and soil **half-thicknesses** (both finite at `dz_moss = 0`). This is exactly energy-conserving (the node stores nothing) and algebraically equivalent to coupling snow directly to soil — the interface temperature simply materializes as `T(row −1)`. When there is also no snow (`snl == 0`), the row degenerates further to an identity tie `T(row −1) = T(soil 1)` — precisely the ssw precedent, where `t_h2osfc` is overwritten with `t_soisno(c,1)` after the solve when `frac_h2osfc == 0` ([SoilTemperatureMod.F90:429-433](src/biogeophys/SoilTemperatureMod.F90:429)).
- **Never use `fact(c,0)`-based terms for a zero-dz moss**: `fact` carries a `dz(c,j)` factor, so `fact(c,0) = 0` and every `…/fact(c,0)` expression divides by zero. The continuity row doesn't use `fact`; `Phasechange` must skip the moss layer when it holds no mass (guard on `wmass0 > 0` / presence predicate — nothing to melt anyway); the `errsoi` energy check must skip the moss storage term (`ΔT/fact`) when `dz(c,0) = 0` (the layer stores nothing, so skipping is exact, not an approximation).
- Interface conductances: the generic `tk` formula silently drops a zero-thickness layer's conductivity (numerator and denominator both collapse onto the neighbor) — make the collapse **explicit** via the presence predicate rather than relying on the algebra, so intent survives refactors.
- `t_soisno(c,0)` (and the `t_nvp_col` mirror) on `nvp_is_empty` columns: **set post-solve to the tied/interface value** (recommended) rather than left as NaN with explicit handling at every access point. The trade-off, considered:
  - *Tie value — pros*: the decisive one is that the 4-way blends multiply the moss temperature by `frac_nvp_eff = 0` on empty columns, and `0 × NaN = NaN` — so NaN poisons even **correctly guarded** blends unless every blend gains an extra conditional (more sites, more merge conflicts). The tie value also matches the ssw precedent (`t_h2osfc` overwritten when `frac_h2osfc == 0`), keeps restart/history files free of NaN/spval special-casing, and degrades gracefully in production if a guard is missed (a physically plausible value instead of NaN in the answers).
  - *Tie value — cons*: it can mask a missing `nvp_is_present` guard — a site that should gate but doesn't silently uses a plausible number instead of failing loudly (the "silent wrong" failure mode we criticized in their branch), and NaN-trapping debug builds can't help find such sites.
  - *Mitigation*: the golden zero-thickness test (§10) is the loud failure the NaN approach would have provided — any missed guard that matters shows up as a `use_nvp=T, dz_nvp=0` vs `use_nvp=F` difference — and it catches the cases NaN-trapping can't (a guard missing where the tie value is *wrong* but finite). So: tie value in the code, golden test as the tripwire.

**Harvest as-is**: NVP thermal conductivity law + `NVPParamsMod` parameters, per-moss-area `cv` with `thin_sfclayer` floor, interface-conductivity handling (`tk(c,0)` degenerates gracefully to the soil half-layer conductance for thin moss), the melt/freeze criteria (buried: plain `tfrz`, no supercooling; exposed: the dedicated `snl==0` initialization block), exclusion of NVP melt from `qflx_snomelt`/`qflx_snofrz` while keeping it in `xmf`, and the `t_nvp_col` mirror.

Local-variable glossary (for §3–§4): `thk(c,j)` = layer conductivity [W/m/K]; `tk(c,j)` = effective conductivity at the interface below `j`; `bw(c,j)` = snow bulk density (mass/volume, input to snow `thk`); `cv(c,j)` = heat capacity per area [J/m²/K]; `fn(c,j)` = conductive flux across the interface below `j` [W/m²]; `fact(c,j)` ≈ `dtime/cv` (geometric factor at the top layer) — flux × `fact` = temperature change; `hm(c,j)` = heat available for phase change in `Phasechange`.

---

## 4. Site inventory: build / harvest / fix

Everything below applies **only where `nvp_layer_exists(c)`** (§2); all guards must reduce to stock behavior otherwise (bit-for-bit). Additionally, every **[physics]**-flavored behavior (moss receiving/holding/emitting anything) gates on **`nvp_is_present(c)`**; where the slot is empty (`nvp_is_empty(c)`), the skip invariant routes each flux to its stock target in the same timestep. Nothing here may assume `frac_nvp = 1` — partial cover is first-class (§1.4). Note their branch never runs in the `jbot_sno=-1 & dz=0` state (it deactivates instead), so **all zero-thickness routing below is our work, not harvestable**. Rows marked **[harvest]** = take their code (possibly adjusted for static `jbot_sno`/honest `snl`); **[fix]** = their branch missed or broke it, we implement it correctly (deliberate merge conflict); **[stub]** = simplified v1 physics.

### 4a. Water

| Site | Disposition |
|---|---|
| `BulkFlux_SnowPercolation` ([SnowHydrologyMod.F90:1293](src/biogeophys/SnowHydrologyMod.F90:1293) stock) | **[harvest]** their three-way `j </==/> jbot_sno` rewiring: bottom snow drains uncapped into moss; moss emits zero percolation (moss outflow goes via the Darcy path below). **Zero-dz**: unchanged — the bottom-snow outflow computation doesn't depend on the receiver's thickness |
| `UpdateState_SnowPercolation`, `SumFlux_AddSnowPercolation` | **[harvest]** — moss receives `perc(c,-1)`; `qflx_snow_drain` books it (snow loses it, `h2osno_total` excludes moss, `errh2osno` closes); bottom percolation removed from `qflx_rain_plus_snomelt`. **Zero-dz [fix/new]**: water must NOT be deposited in a zero-thickness layer — route the bottom-snow outflow directly to the drain/soil hand-off in the same timestep (stock routing), so nothing is stored where nothing can be stored |
| `PostPercolation_AdjustLayerThicknesses`, `SnowCompaction`, `ZeroEmptySnowLayers` | **[harvest]** their `cycle`-at-`j==0` guards |
| NVP↔soil water exchange | **[harvest]** their `NVPWaterBalance_Column` Darcy exchange (upstream-weighted K, van Genuchten ψ/K from `NVPLayerDynamicsMod`), placed after `SnowWater`, before `SetQflxInputs`, feeding `qflx_infl` — their main paths are conservative. Runs only under the presence predicate (`cycle` otherwise — their inactive-column zeroing of the flux outputs is the right pattern). **[fix]** the `max(0, h2osoi_net)` clamp that creates water; **[fix]** the excess-ice fallback that drains ice as liquid with no latent-heat accounting (stub: cap moss ice at pore capacity in phase change so the ice-cap paths are unreachable — verify at any `frac_nvp`/`dz_nvp`) |
| `SetQflxInputs` ([SoilHydrologyMod.F90:340](src/biogeophys/SoilHydrologyMod.F90:340) stock) | **[fix]** the rain-through-snow leak: their soil-input partition withholds `frac_nvp_eff·(qflx_top_soil−…)` while crediting the moss zero whenever `snl<0`. One fraction definition, and every withheld amount must be credited to exactly one receiver (moss infiltration) in the same timestep. **Zero-dz**: `frac_nvp` contributes 0 (§4b), so nothing is withheld — stock partition |
| `RenewCondensation` ([SoilHydrologyMod.F90:2626](src/biogeophys/SoilHydrologyMod.F90:2626) stock) | **[fix]** (their branch: unmodified) — no-snow dew/frost must target the moss **when present**, soil layer 1 otherwise (stock), and the sublimation debit must not double-count against `qflx_ev_nvp` |
| Too-small h2osfc → `h2osoi_liq(c,1)` ([SurfaceWaterMod.F90:331](src/biogeophys/SurfaceWaterMod.F90:331)) | **[fix]** route to moss **when present**, soil layer 1 otherwise (their branch: unaddressed) |
| Richards solve ([SoilWaterMovementMod.F90:619](src/biogeophys/SoilWaterMovementMod.F90:619)) | unchanged — NVP stays outside the solve (both designs agree) |

### 4b. Energy and surface fluxes

The 4-way fractions: **one** derivation of `frac_nvp_eff` (their flux variant: `min(1−frac_h2osfc−frac_sno_eff, max(0, frac_nvp−frac_sno_eff))`, `frac_soil` as the remainder; sums to 1 by construction) computed in **one place** and used everywhere — their branch re-derives it inline ~15 times in two variants, which is where its closure bugs came from. **[fix]** by centralizing. The centralized derivation applies the presence predicate: **where `dz(c,0) = 0`, `frac_nvp` contributes 0** regardless of the namelist value, so every blend, partition, and withholding reduces to stock on moss-free columns (this single rule implements most of the skip invariant for the flux modules). **[harvest]** their blend structures:

- `t_grnd` / `t_grnd0` 4-way blends (three sites, updated together) — [harvest]
- `lw_grnd` in **both** places (`eflx_soil_grnd` and `eflx_lwrad_out`, plus both CanopyFluxes sites) — [harvest]; this two-places subtlety is a lesson their history paid for
- `qg`/`dqgdT` blend with the frozen-branch guard (`hr_nvp = 1` below freezing) — [harvest]; **[fix]** gate `frac_nvp_eff` on `nvp_layer_active` in SurfaceHumidityMod (their gap: bone-dry surface fraction when `frac_nvp>0` with no layer — unreachable in the stub, cheap to do right)
- per-surface resistances (`raiw_nvp`, `rnvp(fwet)`, frozen `rnvp_ice`, the dew-branch fix; CanopyFluxes `wtgq_*` 4-way) — [harvest]; factor `rnvp` into `NVPParamsMod` (theirs duplicates it in three files)
- `eflx_sh_nvp`/`qflx_ev_nvp` — [harvest] with **[fix]**: one consistent gate (`frac_nvp_eff > 0`) in both BareGroundFluxes and CanopyFluxes (theirs disagree), and resolve the non-veg-patch `hs_nvp` accumulation inconsistency — the turbulent flux the atmosphere sees and the flux the moss layer loses must match for any patch structure and any `frac_nvp`
- energy-balance check (`errsoi`) NVP terms — [harvest] their added `j=0` storage terms, with the §3 weighting fix

### 4c. Phase change

**[harvest]** their `Phasechange` NVP treatment wholesale (both the buried `snl<0` and the dedicated exposed `snl==0` block, the mixed `frac_nvp_eff`/`frac_nvp` weighting consistent with per-moss `cv`, melt-flux exclusions, `t_nvp_col` re-sync). **[fix]** `PhaseChangeH2osfc` `snl==0` branches (§3). Supercooling: moss uses the plain `tfrz` criterion, soil keeps supercooling — their choice, adopted.

### 4d. Snow layer combine/divide ([SnowHydrologyMod.F90](src/biogeophys/SnowHydrologyMod.F90))

- `CombineSnowLayers`: **[harvest]** their dz-merge suppression at `j+1==0`, the snow_depth/h2osno moss exclusions, and whole-pack disappearance (`zwice/zwliq` excluding moss; liquid → soil layer 1 — route liquid to moss instead **when the presence predicate holds**, soil layer 1 otherwise: **[fix]**, small). Likewise the vanishing-bottom-layer water hand-off into `j+1 = 0`: into moss when present, straight through to the stock target when `dz(c,0) = 0`. Re-express the loop bounds and neighbor tests per §2 (`do j = msn_old+1, jbot_sno`; `i == jbot_sno` bottom-neighbor test). With honest `snl`, their `snl==-1→0` fixup is unnecessary and **their single-layer combination bug does not arise**: the stock entry guard `snl(c) < -1` ("two or more snow layers") is already correct, and `snl=-1` is a legal one-layer state. Anchor the geometry recursion at `zi(c,jbot_sno)`.
- **[fix]** `qflx_sl_top_soil` accounting: their branch never sets it under NVP, leaving a systematic `errh2osno` residual — the vanishing-bottom-layer flux into moss needs its own booking consistent with the snow balance.
- **[fix]** aerosol merge at `j+1==0` (their guard covers `dz` only; aerosol masses strand in the moss slot) — under decision 5 (their aerosol setup) the minimal correct move is to not merge aerosols into the moss slot (drop them with the same disposal the whole-pack path uses).
- `DivideSnowLayers`: **[harvest]** the `nlevsno-1` cap and un-staging moss exclusion, but with honest `snl` the staging map `local = j - snl(c)` needs the `jbot_sno` offset instead of their `msno = abs(snl)-1` bookkeeping; `snl = -msno` stays stock. Delete their two unconditional debug blocks.
- First-layer creation (`Bulk_InitializeSnowPack`): **[harvest]** their placement at index `jbot_sno` with honest `snl = -1`. **[fix]** `InitSnowLayers` cold start (their branch: unmodified — puts cold-start snow in the moss slot, then NVP init destroys it). With static `jbot_sno` set before `InitSnowLayers`, apply the §2 bound transformation: cold-start snow lands at `≤ jbot_sno` and `snl` counts snow only.

### 4e. Snow capping ([SnowHydrologyMod.F90:3121](src/biogeophys/SnowHydrologyMod.F90:3121) stock)

**[fix]** entirely — their branch left all six routines slicing hardcoded index 0, which removes **moss** water and exports it as runoff while clobbering `dz(c,0)`. All `*_bottom` arguments become per-column `jbot_sno` gathers; moss is never capped.

### 4f. Radiation **[stub]**

Constant-transmissivity partition: of the flux reaching the NVP surface (penetrating the snowpack via SNICAR's existing "slot 1" output, or direct when snow-free), a namelist fraction is absorbed in the moss (slot 0 / `sabg_nvp`) and the rest goes to soil layer 1. Requirements: transmission ≡ 1 reproduces stock, and is **forced to 1 wherever `dz(c,0) = 0`** (a zero-thickness moss absorbs nothing — part of the skip invariant); `sabg_lyr` sums conserve (the [SurfaceRadiationMod.F90:830](src/biogeophys/SurfaceRadiationMod.F90:830) `endrun` stays armed — their branch bypassed it for NVP partial snow: **do not port the bypass**); `eflx_soil_grnd`/`sabg_chk`/the solve all see the same partition (their branch has an RHS solar term with no accounting counterpart and a double-count under layerless snow — both excluded by building the stub partition once, in one place). Ground albedo: a namelist NVP albedo replaces the soil albedo in the blend for the moss fraction (simplified from their Beer-effective form). Their SNICAR layer-0 insertion and Beer machinery arrive with the user's later merge.

### 4g. Aerosols (decision 5: theirs)

**[harvest]** their guards: `j <= col%jbot_sno(c)` in [AerosolMod.F90](src/biogeophys/AerosolMod.F90) mass/optics loops; deposition to `snl+1` is unaffected (top layer). The scavenging cascade's `qin` into the moss slot and the CombineSnowLayers merge strand mass there (cleared only on whole-pack disappearance) — accepted for the stub, recorded in §8 as an important future change.

---

## 5. Conservation accounting **[fix]** (their branch's biggest systematic gap)

- `ComputeLiqIceMassNonLake`: **[harvest]** their `snl==0` companion term for moss water mass. `ComputeHeatNonLake`: **[fix]** — they added the solid-moss heat but never the `snl==0` water-heat companion, so `heat(c)` jumps at every snow onset/melt-out. Add the mirrored term; use **one** predicate (`jbot_sno == -1`) not two.
- `CalculateTotalH2osno` ([WaterStateType.F90:891](src/biogeophys/WaterStateType.F90:891)): **[harvest]** their moss exclusion. `errh2osno` sources: **[harvest]** `qflx_nvp_to_snow_col` booking; the abandoned commented-out corrections around it are superseded by our §4d `qflx_sl_top_soil` fix.
- **[fix]** their `select type` downcast in `BalanceCheckMod` (layering violation): put the NVP fluxes where the generic check can see them without downcasting, or confine the correction to a bulk-only routine.
- `swe_old` ([SnowHydrologyMod.F90:502](src/biogeophys/SnowHydrologyMod.F90:502)): **[fix]** — their bare loop includes moss in SNICAR/aerosol scaling while `AerosolMod` excludes it; make it consistent (exclude).
- Water tracers: the stub updates bulk only, same as theirs — but **[fix]** at minimum an `endrun` if `use_nvp` is combined with active water tracers, so the inconsistency can't run silently.
- All six `BalanceCheckMod` `endrun`s **stay armed** (their branch has them commented out — never port that).

## 6. Special column types

By construction (static `jbot_sno = 0` outside istsoil/istcrop), lakes, glaciers, wetlands, and all urban columns run **bit-for-bit stock code**: every guard reduces algebraically to stock (and per decision 2, `snl` has its stock meaning on *every* column — NVP columns included), and the Lake modules need no changes (confirmed by their branch's experience). Add the defensive assertion their branch lacks: the init routine that sets `jbot_sno=-1` `endrun`s if the column is not istsoil/istcrop. Urban walls (`snl≡0`, `jbot_sno=0`): `j == snl+1 == 1` branches keep pointing at masonry layer 1 — unaffected.

## 7. Infrastructure

- **Namelist**: `use_nvp` (follows the `use_excess_ice` registration pattern: [clm_varctl.F90:451](src/main/clm_varctl.F90:451), [controlMod.F90](src/main/controlMod.F90), `namelist_definition_ctsm.xml` + `namelist_defaults_ctsm.xml` + `CLMBuildNamelist.pm` add_default). Stub parameters (`dz_nvp`, `frac_nvp`, transmissivity, NVP albedo, and the `NVPParamsMod` physics constants we expose) go in their `nvp_inparm` group name — **and get registered in the XML** (their branch's group is unregistered and unsettable; registering is a fix, and using their group/parameter names keeps the merge clean). Every default identical in Fortran and XML (three of theirs are inverted). Fortran-side validity checks: `dz_nvp >= 0` (zero is valid and meaningful); `frac_nvp` consistent with `dz_nvp` (nonzero coverage with zero thickness rejected); `endrun` on `use_nvp` + water tracers; no FATES requirement (deliberate conflict with their build check).
- **Restart** (decision 6: theirs): moss geometry/state rides in `DZSNO[0]`/`ZSNO[0]`/`ZISNO[-1]`/`levtot[0]` unchanged; plus `NVPLayerRestart` (`DZ_NVP`, `FRAC_NVP`, `JBOT_SNO`) with `interpinic_flag='skip'` on the integer flag and re-derivation of `nvp_layer_active` on read. With honest `snl`, `SNLSNO` keeps its documented meaning ("negative number of snow layers") — an improvement over their branch — though a `use_nvp=T` file read with `F` would still misalign the snow block by one slot (moss read as bottom snow), and the reverse direction would read a real snow layer as moss. **Guard now, fix later**: the presence of the NVP restart variables (`JBOT_SNO`/`DZ_NVP`) on the file is a cheap proxy for "written with `use_nvp=T`" — on restart read, `endrun` with an actionable message in both mismatch directions (file has them + `use_nvp=F` → "restart was written with use_nvp on; enable use_nvp or use a different initial file"; file lacks them + `use_nvp=T` → "restart predates use_nvp; cold-start or interpolate"). The *fix* (dedicated non-overloaded variables, init_interp support) remains deferred (§8). With static geometry, add the cheap consistency check: restart-implied `dz(c,0)` vs namelist `dz_nvp`. Our exact-restart test (§10) covers the same-flag case their suite never tested.
- **Cold start**: order matters — set `jbot_sno`/geometry **before** `InitSnowLayers` runs (§4d), then initialize moss water/ice to something physical and climate-agnostic (their `NVPColdStartIce` hard-assumes a frozen start; stub: partition initial pore water by initial temperature). Avoid their two-writers-in-sequence pattern (appear-branch liquid then cold-start-ice overwrite).
- **History**: **[harvest]** their `if (use_nvp)`-guarded fields (`H2ONVP`, `T_NVP`, `FWET_NVP`, `VWC_NVP`, flux fields) with the same names. `hist_set_snow_field_2d` ([histFileMod.F90:2209](src/main/histFileMod.F90:2209)) and the 19 `SNO_*` slices: with honest `snl`, `abs(snl)` correctly counts snow layers, but the fill routine's bottom-justification assumes snow ends at slot 0 — **[fix]** to end at `jbot_sno` so moss never appears as a bottom "snow" layer (their branch didn't address this at all).
- **Unit tests**: parameterize [unittestSubgridMod.F90](src/unit_test_shr/unittestSubgridMod.F90) snow setup over `jbot_sno` and run the SnowHydrology/TotalWaterAndHeat/Balance suites both ways.

## 8. Deferred / future changes registry (out of scope now)

| Item | Why deferred | Origin |
|---|---|---|
| Global (non-per-column) `jbot_sno` with uniformly shifted special columns | Would touch every shared snow routine *and* the Lake modules in ways `ctsm5.4.028_nvp` doesn't, multiplying merge conflicts for a benefit (uniform index semantics) that the static per-column scheme mostly captures anyway. The honest-`snl` half of our original scheme IS adopted (§1.2). Revisit only if the codebase is restructured wholesale | our original plan §1–2 |
| Dynamic (FATES-prognostic) thickness with conservation (activation/deactivation fluxes, dynbal reconciliation, `snl` adjustment) | Needs conservation machinery that doesn't exist yet in either branch (a mass/energy flux for every geometry change, `dynConsBiogeophys` awareness) and can't be tested without a driver of thickness change; their transition code is the buggiest part of their branch and must be redesigned, not harvested. Static thickness lets the stub validate everything else first | their branch |
| Beer's-law transmissivity + SNICAR layer-0 optics | The code already exists on their branch and will overwrite our constant-transmissivity slot at merge (resolution: theirs). Writing our own now would be duplicated effort producing extra, pointless conflicts | their branch |
| FATES-side fractional-cover aggregation fix (`frac_nvp` un-weighted patch sum can exceed 1; four inconsistent patch→column weighting conventions) | Lives entirely in `clmfates_interfaceMod`/FATES `bc_out`, which the stub never touches — the stub's `frac_nvp` is a namelist constant, and the CLM-side closure is fixed for ALL fractions in the stub (§3, §4b). This item only becomes live when FATES starts supplying the fractions, i.e., at/after the merge | their branch |
| Clean aerosol pass-through-and-discard (un-strand the moss slot) | In the static stub the stranded mass is inert: excluded from SNICAR/optics, never re-read as snow aerosol (no deactivation can re-expose it), and cleared on whole-pack disappearance — so behavior is near-equivalent to stock's discard, just delayed. It becomes a real bug only with dynamic activation (post-merge), which is when the cleanup should land | our decision 9 (superseded) |
| Non-overloaded restart (dedicated NVP state variables, clean snow slots) + init_interp third-segment support | Needs a restart-format design (new variables, backward compatibility, interpinic classes) that would diverge from their branch's format and complicate the merge; the §7 cross-flag `endrun` guard (now in scope) removes the silent-corruption risk in the meantime, at the cost of forbidding cross-flag restarts rather than supporting them | our original §8 |
| Water-tracer support for NVP fluxes | Every NVP water flux needs a tracer counterpart threaded through the bulk-and-tracers machinery — substantial surface area orthogonal to the stub's goals. The stub `endrun`s on the combination so the gap cannot run silently | audit finding |
| NVP↔soil interface heat-flux history field | Diagnostic only; explicitly deferred by user decision 11 | — |

## 9. Comparison with the existing implementation (audit record)

Audited at HEAD `103082a17` (146 commits over the `ctsm5.4.028` tag, ~4,200 insertions, 40 files; new `NVPLayerDynamicsMod.F90`/`NVPParamsMod.F90`; substantial FATES coupling). This section is the evidence base for §1's decisions and §4's harvest/fix labels.

### 9a. Design comparison (resolutions now in §1)

| Dimension | Their design | Resolution |
|---|---|---|
| Indexing | Per-column `jbot_sno`, `snl = −(N_snow+1)`, per-site opt-out guards | Per-column `jbot_sno` adopted with **static** assignment (§1.1); their `snl` redefinition **rejected** — we keep honest `snl` + `get_jtop_snow()` (§1.2), accepting the extra merge conflicts; missed-guard sites are §4's **[fix]** list |
| Special columns | Untouched by construction (activation only via FATES wrapper; no type assertion) | Adopted; assertion added (§6) |
| Thermal solve | NVP reuses row −1; no new blocks; `nband=5` | Adopted (§3) — better than our original "move ssw" layout |
| Endmembers | 4-way split, `frac_nvp_eff` re-derived inline ~15×, two variants | Equations adopted; **centralized** derivation (§4b); closure fixed for all fractions — partial cover (`0 < frac_nvp < 1`) is first-class and tested in the stub |
| Thickness | FATES-prognostic, daily; transitions non-conservative | **Ours**: fixed namelist (§1.8) |
| Shortwave | Beer's law + SNICAR layer-0 insertion (clean technique; buggy accounting) | **Stub**: constant transmissivity (§1.9); their machinery merges later |
| Aerosols | Excluded from optics; scavenged mass strands in the moss slot | Adopted (§1.5); cleanup deferred (§8) |
| Restart | NVP state overloads snow slots; `NVPLayerRestart` for the three new fields; no guards; albedo state unrestarted | Adopted (§1.6) with `interpinic_flag` fix; guards deferred (§8) |

### 9b. Scorecard

**Handled well (the §4 [harvest] list):** percolation three-way rewiring; `PostPercolation`/`SnowCompaction`/`ZeroEmptySnowLayers` guards; `DivideSnowLayers` cap and staging; first-snow-at-−1; NVP melt excluded from `qflx_snomelt` but kept in `xmf`; the dedicated `snl==0` phase-change block; conductivity/cv laws with guards; graceful interface-conductivity degeneracy; moss counted exactly once in `begwb/endwb`; excluded from `h2osno_total`; per-surface resistances incl. the dew-branch fix; 4-way `qg` blend with frozen guard; `lw_grnd` fixed in both places; SNICAR layer-0 insertion with `merge(-1, snl_btm, nvp_active)` bounds; Beer-effective ground albedo; van Genuchten/Mualem/evaporation-resistance physics; upstream-weighted Darcy exchange (main paths conservative); driver ordering; row −1 matrix reuse.

**Handled with bugs (the §3–§5 [fix] list):** CombineSnowLayers single-layer `Combo`-into-moss + missing `qflx_sl_top_soil` + stranded aerosol merge; `PhaseChangeH2osfc` `snl==0`; moss↔soil conduction weight mismatch; `frac_h2osfc` double-subtraction; `errsoi` weight inconsistency; solar double-count under layerless snow + unaccounted RHS solar term + bypassed `sabg_lyr` endrun; `frac_nvp` un-weighted patch sum used as divisor; inconsistent `eflx_sh_nvp` gates.

**Missing entirely (predicted by the original analysis; now §4/§5/§7 [fix] items):** `fact(c,0)`/`fn(c,0)` at `snl==0`; SnowCapping index-0 slices; `InitSnowLayers` cold start + no `snl` adjustment on activation; `RenewCondensation`; too-small-h2osfc routing; `h2osno_no_layers` heat still in soil layer 1; `ComputeHeatNonLake` `snl==0` water heat; water tracers; restart/init_interp guards; snow history fields; sparsity-diagram docs; **zero** exact-restart/threading/PE tests (12 tests, all SMS).

### 9c. Blocking defects (never port; fix before evaluating their branch)

1. **Six of seven balance-check `endrun`s commented out** ([BalanceCheckMod.F90] :679, :764, :891, :1088, :1142, :1159) — unconditional, all configurations; every "passing" test passed with conservation enforcement off.
2. **`use_nvp=.false.` not bit-for-bit**: ~128 debug writes, many unguarded (one reads an uninitialized loop variable; `print *` inside the Richards solver loop; whole-array dumps per timestep); unconditional `p2c` of a NaN-initialized NVP flux; changed `wrap_sunfrac` signature.
3. **Rain-through-snow water destruction** ([SoilHydrologyMod.F90:359-395] on their branch): soil-input partition withholds the moss share; moss credited zero whenever `snl<0`.
4. **`UpdateNVPLayer` zeroes bottom-snow geometry on inactive FATES columns** → their documented divide-by-zero expected-fails.
5. **Moss↔soil conduction weight mismatch** → energy created whenever `frac_sno_eff > frac_nvp`.
6. **`col%frac_nvp` can exceed 1** (un-weighted patch sum) and is used as a divisor; four inconsistent patch→column aggregation conventions.
7. **Restart interoperability**: silent corruption in both `use_nvp` mismatch directions; init_interp broken; NVP albedo state not restarted.
8. **Namelist hygiene**: three of four flags with inverted Fortran-vs-XML defaults; `nvp_inparm` unregistered; no Fortran-side FATES check.

## 10. Verification strategy

1. **`use_nvp = .false.` bit-for-bit vs the `ctsm5.4.028` tag** — the primary gate; proves every guard reduces to stock. (Their branch fails this; ours must not.)
2. **All balance checks armed at tight tolerance** throughout development — each §9c/§4 defect class trips a specific check (moss-as-snow → `errh2osno`; unrouted absorption → the `sabg_lyr` endrun; weighting mismatch → `errsoi`/`errseb`; water routing → `errh2o`).
3. **Exact-restart (`ERS`/`ERI`) with `use_nvp=T`** — absent from their suite; must pass with the adopted snow-slot restart scheme.
4. **Snow transition cases** on NVP columns: first snowfall onto moss (`snl 0→−2`), last layer vanishing (`−2→0`), single-layer combination (their bug's exact trigger), deep-pack subdivision at the `nlevsno−1` cap, layerless snow (`h2osno_no_layers > 0, snl==0`) over moss — the regime of their solar double-count and heat-accounting bugs.
5. **Golden zero-thickness invariant**: `use_nvp = .true.` with `dz_nvp = 0` must reproduce `use_nvp = .false.` answers — exactly if the flux-continuity moss row is eliminated algebraically, to roundoff otherwise. This single test exercises every skip path (§2 invariant, §3 degenerate row, §4 zero-dz routings, the §4b fraction rule) and is the second-strongest gate after bit-for-bit `use_nvp=F`.
6. **Partial-cover closure**: run with `0 < frac_nvp < 1` (e.g., 0.3 and 0.7) through winters, deliberately exciting both `frac_sno_eff < frac_nvp` and `frac_sno_eff > frac_nvp` (the regime where their branch creates energy) and `frac_h2osfc > 0` — water and energy balances must close exactly at every timestep. This is a first-class configuration, not an edge case.
7. **Sensitivity sanity**: transmissivity = 1 + tiny `dz_nvp` ≈ stock answers (not exact — a real moss layer conducts — but bounded and converging as `dz_nvp → 0`, which the golden invariant anchors); conservation must hold exactly at any parameter values.
8. **Unit tests** both ways per §7; standard aux_clm coverage for lake/glacier/urban configs to confirm bit-for-bit there.
9. **Merge rehearsal** (before declaring done): trial-merge the stub branch into `ctsm5.4.028_nvp` in a scratch worktree, confirm the conflict set is exactly the intentional list (§1.2 `snl`-bookkeeping sites, §1.8–1.12, §4 [fix] sites), and record the resolution direction for each in a MERGE_NOTES file on the branch.
