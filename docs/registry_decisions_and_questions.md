# Model registry — design decisions and open questions

Companion to `docs/model_registry_design.md`. LCLS registry is implemented and verified against
real models; FACET-II is not registered yet.

---

## Part A — Design decisions

### A1. Any element may be a start/end point; screens are enumerated as a hint

**Revised 2026-09-02 per supervisor.** An earlier draft restricted handoffs to diagnostics. That is
lifted: any element in the lattice may be used, with `CATHODE` as the canonical name for models
starting at the front of the machine.

Screens are still listed per model (`handoff_points`) for two reasons: discovery, and as a typo
check — screens are enumerated exhaustively, so a screen-shaped name absent from the list is
definitely wrong and is rejected early rather than failing deep inside Tao. Anything else passes
through to the engine. There are 3323 elements in `cu_hxr`, so exhaustive validation is not on the
table.

`CATHODE` is the first entry that makes `element_aliases` non-empty: Bmad calls it `CATHODE`, IMPACT
calls it `GUN`.

### A2. Reference plane is the element ENTRANCE

**A midpoint default was considered and rejected on evidence.** Bmad's `-slice_lattice` begins at an
element's *entrance* and cannot begin at a midpoint:

| element | L | entrance | centre | Bmad slice begins at |
|---|---|---|---|---|
| `QE01` | 0.108 | 8.440049 | 8.494049 | **8.440049** |
| `L0A` | 3.095 | 1.459000 | 3.006622 | **1.459000** |

IMPACT's `impact.ele[name]["s"]` is also the entrance, though IMPACT *could* express a midpoint
since `impact.stop` is a float. So a midpoint default would be implementable in IMPACT but not in
Bmad, making the two engines silently disagree by half an element length — the exact class of bug
this design is meant to prevent. Entrance is the only plane both engines express identically.

The separate issue of identical elements sitting at slightly different `s` in the two lattices
(FACET differs by up to ~3.9 mm, growing downstream; LCLS agrees exactly) is unaffected by this
choice and remains unpoliced — see A3.

### A2b. Duplicate PVs at the handoff are unregistered from the downstream stage

**Revised 2026-09-02 per supervisor.** An earlier draft moved the downstream start to the *next*
element (an `element_after` dict) to dodge the collision. That dict is now gone.

Both stages include the handoff element, so both publish its PVs and `StagedModel` would reject the
pair as duplicates. Instead the overlap is computed after construction and removed from the
downstream stage, which lets the handoff be expressed as the real element name (`YAG03`, not
`DL02A2`). `lume.actions` provides `unregister_action_variable(name)` and `supported_variables` is a
property over `_action_variable_by_name`, so this is clean public API. Verified on a real Bmad model:
318 vars → 312 after removing the six `YAGS:IN20:351:*` PVs, model still functional.

The upstream stage owns the handoff PVs because it is the stage that actually tracks the beam to
that plane.

**One safety rule added:** a *writable* overlap raises instead of being dropped. Writable overlap
means both stages are driving the same magnet — the extents overlap rather than meeting at a plane —
and silently dropping it downstream would leave that stage tracking with a stale value. Measured
that the real YAG03 overlap is entirely read-only, so the rule does not fire in normal use.

### A3. No positions stored — compatibility is name equality plus list-index ordering

`handoff_points` lists are ordered by lattice position, so ordering is checkable by index without
storing metres.

**Consequence:** the FACET IMPACT geometry disagrees with the Bmad geometry by up to ~3.9 mm at
`PR10571`, growing downstream (LCLS agrees exactly, to nine decimals). This is documented as a
physics caveat and deliberately **not** policed by the registry. Trigger for revisiting is recorded
in the design doc's "deliberately deferred" table.

### A4. Builders referenced as `"module:function"` strings, resolved lazily

The existing builders import `pytao` / `torch` / `impact` inside their function bodies via
`import_optional`. Holding real callables in the registry would force importing every engine module
just to import the registry. As strings, `models_available` and `list_handoff_points` work with **zero
optional dependencies installed** — verified.

### A5. Registry declares each model's params; unknown kwargs are rejected

Kwarg routing across stages is a table lookup, not signature introspection, so error messages can
name the candidate stages. Trade-off: adding a parameter to a builder means also adding it to the
registry. That cost buys real error messages and a truthful `models_available`.

Routing rules: broadcast params (`n_particles`) go to every stage declaring them; a param declared
by exactly one stage routes there; declared by more than one and not broadcast is an error naming
the candidates; `"<model_name>.<param>"` always wins.

### A6. Element names normalised to upper case at the API boundary

Found by testing. Without it, `handoff_loc='yag03'` silently bypassed the A2b collision check and
started Bmad *at* the screen, resurfacing the duplicate-PV failure. Also fixes IMPACT, where
`impact.ele[...]` is a case-sensitive dict lookup.

### A7. `track_beam=True` forced on every stage in a chain

An earlier draft said non-terminal stages only. Wrong, and caught by testing: a non-final stage must
*produce* `final_particles`, but a non-first stage must also *accept* `initial_particles`, and
`lume_bmad` raises `Cannot set initial_particles when track_type is not 'beam'`. In a two-stage
surrogate → Bmad chain the Bmad stage is terminal and still needs it.

### A8. Hand-maintained Python literals — no generated data files, no CI regenerator

Per the "start simple" steer. The lists are short and change only when a lattice model changes, so a
diff is readable. Revisit if they drift from the lattice.

### A9. Registry naming convention `<engine>_<lattice>`

`impact_cu_inj`, `bmad_cu_hxr`, `surrogate_cu_inj`, `cheetah_cu_hxr`. See Q6.

### A10. Existing builders keep working; migration is deferred

`get_cu_hxr_staged_model` etc. are untouched so far. Proven equivalent to the registry path:
identical variable sets, identical Bmad slice, and beam moments differing by 1.6e-05 relative —
less than the 4.6e-05 run-to-run variation of the existing builder against *itself* (distgen
sampling noise). Migration to thin wrappers is queued behind end-to-end verification of the
IMPACT → Bmad path.

---

## Part B — Questions

### Blocking now

**Q1. `TCY10490 → KLYS:LI10:51` — deliberate, like the `PROF:` overrides?**
`models/facet2.py` overrides this alias, but the FACET lattice says `TCY10490[alias]=TCAV:IN10:490`
and the elements CSV agrees. This is the same shape of question as the screen-prefix one, but for a
TCAV rather than a screen. *Blocks the FACET PV fix, since that PR touches `custom_aliases`.*

**Q2. ANSWERED 2026-09-02.** `PROF:` applies to both engines, and more importantly: *"the csv
file usually doesn't have correct values"*. So `lcls_elements.csv` is **not** authoritative for PVs.
That confirms the fix — make `utils/*_profmon_info.yaml` the single source of truth for screen PVs
for both Bmad and IMPACT. It already holds correct values for both facilities, in a `name:` field
that neither engine currently reads. LCLS is a no-op. Note this narrows the CSV's role to element
*names* and `SumL`; its `Control System Name` column should not be trusted.

**Q3. ANSWERED 2026-09-02.** `element_after` is gone — replaced by unregistering overlapping
variables from the downstream stage (A2b). Simpler and more general.

### Naming and API — cheap now, expensive later

**Q4. Field name: `diagnostics` or `handoff_points`?**
`L0AFEND` is a marker, not a screen, so `diagnostics` is slightly dishonest (A1 caveat).

**Q5. Which stage should own the handoff screen?**
I gave it to the **upstream** stage, on the reasoning that it physically images the screen as its
last element. The alternative is to have IMPACT stop just *before* the screen and let the
downstream Bmad model own it. That changes which model reports the handoff-plane measurement, so it
is a physics/operations call rather than a code one.

**Q6. Are `impact_cu_inj` / `bmad_cu_hxr` / `surrogate_cu_inj` / `cheetah_cu_hxr` the names we want
users typing?** These become the public interface and are awkward to change once notebooks and
scripts use them.

**Q7. Should `get_model` accept PVs as `start_ele` / `end_ele`** (e.g. `"OTRS:IN20:571"` as well as
`"OTR2"`)? Cheap to add; plausibly what a control-room user reaches for first.

### Scope

**Q8. `runners.py` CLI back-compatibility.** Routing it through the registry changes the accepted
`--model` values (`cu_hxr_bmad` → `bmad_cu_hxr`, etc.). Alias the old names, or make a clean break?

**Q9. What else should be registered beyond LCLS cu_hxr and FACET-II?**
`examples/cheetah_diag0_model.ipynb` builds a diag0 Cheetah model inline with no factory function,
and a `models/sc_diag0.py` exists in stale build artifacts but not in current source. Is diag0
in scope? Are LCLS-II / nc_sxr models expected? This determines whether the flat
`<engine>_<lattice>` naming holds up.

**Q10. Who owns keeping the diagnostics lists in sync with the lattice?**
A8 chose hand-maintained literals. If upstream renames or adds a screen, nothing detects it
automatically. Acceptable, or should there be a CI check that reconciles the lists against
`$LCLS_LATTICE`?

---

## Verification status

| path | status |
|---|---|
| Discovery / validation / routing / overlap logic, no extras installed | 51 unit tests, ~1 s |
| `bmad_cu_hxr` single model | built on real lattice, correct slice and PVs |
| `surrogate_cu_inj` -> `bmad_cu_hxr` staged | built, quad set, beam propagated, real OTR4 image |
| Equivalence with `get_cu_hxr_staged_model` | identical vars and slice; within sampling noise |
| Removing overlapping variables, on a real model | 318 -> 312 vars, model still functional |
| `impact_cu_inj` -> `bmad_cu_hxr` staged | **NOT verified** -- needs the IMPACT-T executable |

**The last row matters more after this revision.** Removing overlapping variables is now the core
handoff mechanism, and the only staged path runnable here does not exercise it: measured overlap
between `surrogate_cu_inj` and `bmad_cu_hxr` is **zero**, because the surrogate publishes
`OTRS:IN20:571:XRMS`/`YRMS` while Bmad publishes `Image:*`/`RESOLUTION`/`X`. So the mechanism is
covered by unit tests and by a direct measurement on a Bmad model, but has never run inside a real
two-stage build. Closing that needs `conda install -c conda-forge impact-t`.
