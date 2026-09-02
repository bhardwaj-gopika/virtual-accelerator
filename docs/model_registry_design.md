# Model registry + unified `get_model` — design proposal

Status: **implemented for LCLS** in `virtual_accelerator/registry/`. FACET-II entries are not
registered yet; §7 (screen PV prefixes) should land before they are.

Goal: one entry point for every model, a registry of what exists and how to configure it, and
enough per-model metadata to stitch stages together safely.

Scope: **any lattice element may be a start/end point**, with `CATHODE` as the canonical name for
models starting at the front of the machine. No element catalog is needed, because the only element
names that differ between engines are the gun and the RF cavity segments (see §1), so a small
per-model alias dict covers it. Screens are enumerated per model as a discovery aid and a typo check.

Reference plane is the element **entrance** — see §5.

---

## 1. Evidence: why a list of names is enough

Checked against the real lattice files, not assumed.

**Diagnostics already agree between Bmad and IMPACT, in both facilities.** The suspected
`YAG03`/`YAG3` mismatch does not exist. Confirmed screen-by-screen:

| facility | diagnostic | Bmad | IMPACT-T |
|---|---|---|---|
| LCLS | YAG02, YAG03, OTR1, OTR2 | same | same |
| FACET | PR10241, PR10465, PR10471, PR10571 | same | same |

Bmad aliases match `utils/cu_hxr_profmon_info.yaml` exactly (`OTR2[alias]=OTRS:IN20:571`,
`YAG03[alias]=YAGS:IN20:351`), so the profmon YAMLs already are a de-facto standard-name list —
this proposal just makes them addressable per model.

Note that the *element names* agreeing is separate from the *PVs* agreeing — the latter is broken
for FACET, see §7.

**The divergences that exist are all in non-diagnostic elements**, i.e. things that are never
handoff points:

| element | Bmad | IMPACT-T |
|---|---|---|
| gun / cathode | `CATHODE` / `CATHODEF` | `GUN` / `GUNF` |
| L0A cavity | `L0A` (one lcavity) | `L0A_entrance`, `L0A_body_1`, `L0A_body_2`, `L0A_exit` |

So the alias dict carries only the gun (`CATHODE` → IMPACT `GUN`). Cavity segmentation is one-to-many
and cavities are not sensible handoff planes, so they are simply not registered as handoff points.

Two facts that don't need machinery but should be written down:

- IMPACT z and Bmad slice starts are both the element *entrance*; the lattice CSV's `SumL` is the
  element *centre*. For a quad these differ by half the length (FACET `QA10361`: 4.3103893 vs
  4.4123893). This is why the entrance is the reference plane and the CSV's `SumL` is not used for it.
- FACET IMPACT geometry disagrees with the Bmad geometry by up to ~3.9 mm at `PR10571`, growing
  downstream. LCLS agrees exactly. Real, but a physics caveat rather than something the registry
  should police.

---

## 2. Registry

One table. Models only; no separate element registry.

```python
@dataclass(frozen=True)
class ModelEntry:
    name: str                        # "bmad_cu_hxr"
    description: str                 # what models_available prints
    facility: str                    # "lcls" | "facet2"
    engine: str                      # "bmad" | "impact" | "surrogate" | "cheetah"
    builder: str                     # "virtual_accelerator.models.cu_hxr:get_cu_hxr_bmad_model"
    extras: tuple[str, ...]          # pip extras needed, e.g. ("bmad",)
    params: dict[str, Any]           # param name -> default, for validation + discovery
    broadcast_params: frozenset[str] # params safe to send to every stage, e.g. {"n_particles"}

    handoff_points: tuple[str, ...]  # suggested elements, ORDERED by lattice position
    start_param: str | None          # builder kwarg for start, None if fixed
    end_param: str | None            # builder kwarg for end, None if fixed
    default_start: str | None
    default_end: str | None

    element_aliases: dict[str, str] = field(default_factory=dict)
    # standard name -> this engine's local name. Empty today; escape hatch only.
```

`start_param` / `end_param` replace the earlier `can_start_anywhere` flag: they carry the same
information (`None` means the extent is fixed) while also recording what each builder *calls* the
parameter, which differs between engines.

`handoff_points` is a discovery aid and typo check, **not** a restriction — any lattice element may
be used as a start/end point. See §5 for how duplicate PVs at the handoff are resolved.

Three choices worth calling out:

**`builder` is a `"module:function"` string, not a callable.** The existing builders lazily import
`pytao` / `torch` / `impact` inside the function body via `import_optional`. A real callable in the
registry would force importing every engine module just to import the registry, breaking
`models_available` for anyone without all extras installed.

**`handoff_points` is ordered by lattice position.** Ordering is then checkable by list index
instead of by metres, which is what lets the design drop positions entirely.

**No data files, no generator script.** The lists are hand-maintained Python literals in
`registry/models.py`. They are short, they change only when a lattice model changes, and a diff is
readable. Revisit only if they start drifting from the lattice.

```
virtual_accelerator/registry/
├── __init__.py     # get_model, models_available, list_handoff_points
└── models.py       # the ModelEntry table
```

---

## 3. Model catalog

| registry name | facility | engine | builder | key params | suggested handoff points |
|---|---|---|---|---|---|
| `impact_cu_inj` | lcls | impact | `get_cu_inj_impact_model` | `n_particles=100`, `end_element="OTR2"` | CATHODE, YAG02, YAG03, OTR1, OTR2 |
| `bmad_cu_hxr` | lcls | bmad | `get_cu_hxr_bmad_model` | `start_element="OTR2"`, `end_element="END"`, `track_beam=False`, `custom_beam_path=None` | CATHODE, all 12 profmon screens, END |
| `surrogate_cu_inj` | lcls | surrogate | `get_cu_hxr_injector_surrogate_model` | `n_particles=1000` | CATHODE, OTR2 (fixed extent) |
| `cheetah_cu_hxr` | lcls | cheetah | `get_cu_hxr_cheetah_model` | `n_particles=1000` | — |

Naming convention: `<engine>_<lattice>`.

**Not yet registered** — FACET-II, pending §7:

| registry name | facility | engine | builder | key params | suggested handoff points |
|---|---|---|---|---|---|
| `impact_f2e_inj` | facet2 | impact | `get_facet_impact_model` | `n_particles=100`, `end_element="PR10571"` | PR10241, PR10465, PR10471, PR10571 |
| `bmad_f2_elec` | facet2 | bmad | `get_facet_bmad_model` | `start_element="L0AFEND"`, `end_element="END"`, `track_beam=False`, `custom_beam_path=None` | PR10241, PR10465, PR10471, PR10571, PR10711 |
| `surrogate_f2e_inj` | facet2 | surrogate | ⚠ **does not exist yet** | `n_particles=10000`, `surrogate_inputs="machine"` | PR10241 (fixed end) |

Notes on the lists:

- `impact_cu_inj` omits `OTRH1`/`OTRH2` (laser heater is unmodeled in the deck: `!!! Unmodeled:
  Laser Heater from 9.076892 m to 10.690580 m`) and `OTR3`/`YAG01` (lines commented out —
  `YAG01` is marked `!!! Broken:`). `OTR4` is past `stop_1` at z=16.5.
- `impact_f2e_inj` includes `PR10571` because the file actually loaded is
  `ImpactT_template.in` (per `ImpactT.yaml`'s `input_file:` key). The checked-in `ImpactT.in` is a
  stale truncated artifact stopping at z=12.0 and omitting it — reading that file gives the wrong
  answer about available stop points. Worth an upstream issue.
- `bmad_f2_elec` defaults `start_element="L0AFEND"`, a marker rather than a screen. It exists in
  both engines (Bmad superimposed marker, IMPACT write-beam element) so it is a legitimate handoff
  plane. Since any element is now allowed, markers need no special treatment — they are simply listed
  in `handoff_points` where useful.

**Prerequisite:** `surrogate_f2e_inj` has no standalone builder — the `BeamOutputModel` is built
inline inside `get_facet_staged_model`. It needs extracting to
`get_facet_injector_surrogate_model()` to mirror `get_cu_hxr_injector_surrogate_model`, otherwise
it can't be a registry entry.

`get_cu_hxr_staged_model` / `get_facet_staged_model` become thin back-compat wrappers over
`get_model([...])`.

---

## 4. `get_model`

```python
def get_model(
    spec: str | Sequence[str],
    *,
    handoff_loc: str | Sequence[str] | None = None,
    start_ele: str | None = None,
    end_ele: str | None = None,
    **kwargs,
) -> LUMEModel:
```

```python
# single
model = get_model("bmad_cu_hxr", end_ele="OTR4", track_beam=True)

# staged, explicit handoff
model = get_model(["impact_cu_inj", "bmad_cu_hxr"],
                  handoff_loc="YAG03", end_ele="OTR4", n_particles=1000)

# staged, handoff inferred from the surrogate's fixed end (OTR2)
model = get_model(["surrogate_cu_inj", "bmad_cu_hxr"], end_ele="OTR4", n_particles=10000)
```

Every example above is registered and working today, except that the `impact_cu_inj` stage needs
the IMPACT-T executable (`conda install -c conda-forge impact-t`) on top of the Python package.

FACET-II is **not** registered yet, so this raises `KeyError` for now — see §3 and §7:

```python
model = get_model(["impact_f2e_inj", "bmad_f2_elec"], handoff_loc="L0AFEND")  # not yet
```

`start_ele` / `end_ele` on a staged call are the *overall* extent — first stage's start, last
stage's end. Interior extents come from `handoff_loc`.

### Discovery

```python
from virtual_accelerator.registry import models_available, list_handoff_points

print(models_available)
# impact_cu_inj    IMPACT-T LCLS injector, cathode -> OTR2
# bmad_cu_hxr      Bmad CU-HXR, gun -> undulator/dump
# ...

list_handoff_points("bmad_cu_hxr")
# ('YAG02', 'YAG03', 'OTRH1', 'OTRH2', 'OTR1', 'OTR2', 'OTR3', 'OTR4',
#  'OTR11', 'OTR12', 'OTR21', 'OTRDMP')
```

All 12 screens in `cu_hxr_profmon_info.yaml` were verified present in the `cu_hxr` lattice, in the
order shown.

### Kwarg routing

Because the registry declares each model's params, routing is a lookup, not signature
introspection:

1. Param in `broadcast_params` (e.g. `n_particles`) → sent to every stage that declares it.
2. Declared by exactly one stage → routed there.
3. Declared by more than one stage and not broadcast → `ValueError` naming the candidates.
4. `"<model_name>.<param>"` always wins.
5. Matching no declared param → rejected with a suggestion, not silently forwarded.

`track_beam=True` is forced on **every** stage that declares it, regardless of what the user
passes. An earlier draft said "non-terminal stages only", which is wrong and was caught by testing:
a non-final stage must *produce* `final_particles`, but a non-first stage must also *accept*
`initial_particles`, and `lume_bmad.model` raises `Cannot set initial_particles when track_type is
not 'beam'` otherwise. In a two-stage surrogate → Bmad chain the Bmad stage is terminal and still
needs it.

---

## 5. Compatibility checking

`StagedModel.validate_lume_model_instances` already checks mixin presence and duplicate variable
names — but only *after* both models are constructed, and `build_impact_model` calls
`impact.run()` during construction. So a duplicate-variable error costs a full IMPACT run before
it surfaces. The registry pre-validates from metadata alone, before instantiating anything.

All checks are name-based. No positions involved.

**C1 — same facility.** Staging `bmad_cu_hxr` onto `impact_f2e_inj` is rejected immediately.

**C2 — handoff is a legal point in both stages.** `handoff_loc` must be in the upstream stage's
`diagnostics` and in the downstream stage's. Plus the downstream stage must have a `start_param`,
which is what makes `get_model(["bmad_cu_hxr", "impact_cu_inj"], ...)` fail with "IMPACT models can
only start at the cathode" instead of something inscrutable from inside `set_stop_location`.

**C3 — duplicate PVs at the handoff are removed from the downstream stage.** This is the most
important rule in practice, and it was revised on 2026-09-02.

Both stages include the handoff element, so both publish its PVs. IMPACT's `set_stop_location`
prunes to `s <= stop`, so a model stopped at `YAG03` *keeps* the screen and publishes its six
`YAGS:IN20:351:*` image PVs; Bmad sliced from `YAG03` publishes the same six. `StagedModel` then
rejects the pair as duplicates — after paying for a full IMPACT run.

Resolution: compute the overlap after construction and unregister it from the **downstream** stage.
The upstream stage owns those PVs because it is the stage that actually tracks the beam to that
plane. `lume.actions` exposes `unregister_action_variable(name)` and `supported_variables` is a
property over `_action_variable_by_name`, so this is clean public API. Measured on a real Bmad model:
318 vars → 312 after removal, model still functional.

This lets the handoff be named for the real element (`YAG03`) rather than the drift after it. An
earlier draft instead moved the downstream start to `element_after[handoff]` (`DL02A2`); that dict is
gone. It also explains `start_element="DL02A2"` in `examples/staged_example.ipynb` — a workaround for
this collision, no longer needed.

**Safety rule:** a *writable* overlap raises rather than being dropped. Writable overlap means both
stages are driving the same magnet — extents overlapping rather than meeting at a plane — and
dropping it downstream would leave that stage tracking with a stale value. The real YAG03 overlap was
measured to be entirely read-only, so this does not fire in normal use.

**Caveat:** the only staged path runnable without the IMPACT-T binary does not exercise this.
Measured overlap between `surrogate_cu_inj` and `bmad_cu_hxr` is **zero** — the surrogate publishes
`OTRS:IN20:571:XRMS`/`YRMS` while Bmad publishes `Image:*`/`RESOLUTION`/`X`.

**C4 — beam handoff mechanics.** One place, in the registry, resolving an existing inconsistency:
`get_facet_staged_model` writes `final_particles` to a `NamedTemporaryFile` and passes it as
`custom_beam_path`, while `get_cu_hxr_staged_model` does neither and relies solely on the
`FinalParticlesMixIn` wiring in `StagedModel._set`. One of those is redundant or one is a latent
bug; the registry should own this in exactly one place.

Also worth noting for C4: `get_facet_staged_model` hardcodes `t0=3.15391398e-09`, `p0c=6.3e06`,
`z0=0.9420843`. That `z0` is exactly `PR10241`'s s-position — these are handoff-plane quantities,
so if a second FACET handoff plane is ever used they will need to move somewhere per-plane rather
than staying inline.

---

## 6. Deliberately deferred

Cut from the previous draft, with the trigger for reconsidering each:

| deferred | add it when |
|---|---|
| Element catalog generated from `lcls_elements.csv` | a handoff point is needed that isn't a diagnostic, or the hand-maintained lists start drifting from the lattice |
| s-positions on handoff points | we want to *numerically* verify a handoff rather than trust name equality |
| Tolerance-based position agreement check | ditto — this is where the FACET ~3.9 mm discrepancy would resurface |
| Physical-extent overlap check between stages | `StagedModel`'s duplicate-variable check proves insufficient in practice |
| PV names accepted as `start_ele` / `end_ele` | a control-room user asks for it; cheap to add later |

---

## 7. Screen PV prefixes — resolved, and a bug it exposes

**Resolved rule (supervisor, 2026-09-01): `PROF:` is correct for FACET VAs; `YAGS:`/`OTRS:` are
correct for LCLS / LCLS-II VAs.**

This explains an asymmetry in the current code that otherwise looks arbitrary:
`get_facet_bmad_model` carries a `custom_aliases` dict while `get_cu_hxr_bmad_model` carries none.
FACET needs it precisely *because* the lattice aliases (`YAGS:/OTRS:IN10:*`) are wrong for VA
purposes; LCLS needs none because its lattice aliases are already right.

### How each engine currently derives a screen's PV

- **Bmad** — `bmad/variables.py:375`: `base_pv = tao.ele(screen_name).head.alias`, i.e. the Tao
  element alias. `build_bmad_model` applies `custom_aliases` (factory.py:72-78) *before*
  `get_variables` (factory.py:86), so the override ordering is correct.
- **IMPACT** — `impact/variables.py`: `alias_dict[element_name]`, where `alias_dict` is
  `Element -> Control System Name` from `bmad/conversion/from_oracle/lcls_elements.csv`. There is
  **no** `custom_aliases` equivalent on this path.
- **Neither** reads the `name:` field of `utils/*_profmon_info.yaml`. Bmad uses that file only for
  `shape` and `pixel_size` (variables.py:379-382). So the `name:` field is currently dead data —
  even though it holds the correct value in every case.

### Consequence: FACET screen PVs are wrong today

| screen | Bmad yields | IMPACT yields | correct (per rule) |
|---|---|---|---|
| PR10241 | `PROF:IN10:241` ✓ | `YAGS:IN10:241` ✗ | `PROF:IN10:241` |
| PR10465 | `OTRS:IN10:465` ✗ | `OTRS:IN10:465` ✗ | `PROF:IN10:465` |
| PR10471 | `OTRS:IN10:471` ✗ | `OTRS:IN10:471` ✗ | `PROF:IN10:471` |
| PR10571 | `PROF:IN10:571` ✓ | `OTRS:IN10:571` ✗ | `PROF:IN10:571` |
| PR10711 | `PROF:IN10:711` ✓ | `OTRS:IN10:711` ✗ | `PROF:IN10:711` |

FACET Bmad is wrong for 2 of 5 screens (`custom_aliases` simply omits `PR10465`/`PR10471`); FACET
IMPACT is wrong for all 5. This directly affects `impact_f2e_inj` — the model about to be staged.

LCLS is consistent across all three sources (lattice alias, CSV `Control System Name`, and
`cu_hxr_profmon_info.yaml`), so it is unaffected either way.

### Proposed fix — no new data structure

Make `utils/*_profmon_info.yaml` the single source of truth for screen PVs, and have **both**
engines read `screen_config[name]["name"]` instead of the lattice alias / CSV. Then:

- Every FACET screen is fixed in both engines at once, because the YAML already holds the right
  values for all five.
- LCLS is a **no-op** — its YAML values already equal its lattice aliases and CSV entries.
- `custom_aliases` in `models/facet2.py` loses its screen entries entirely, keeping only
  `TCY10490 -> KLYS:LI10:51` (a TCAV, not a screen, and a separate question).
- The dead `name:` field becomes load-bearing, so it can no longer silently drift.

This is deliberately *not* the element catalog returning: it reuses a file that already exists and
already has the answer. Worth doing as a small standalone PR **before** the registry work, since
the registry shouldn't inherit a known-wrong PV mapping.

One fragility worth fixing alongside: `alias_dict[element_name]` in `impact/variables.py` is an
unguarded dict lookup, so any element absent from the CSV raises a bare `KeyError`.

---

## 8. Open questions

1. **Field name** — `diagnostics` or `handoff_points`? The FACET default start `L0AFEND` is a
   marker, not a diagnostic, so the latter is more honest.
2. **`TCY10490 -> KLYS:LI10:51`** — the one non-screen entry in FACET's `custom_aliases`. The
   lattice says `TCY10490[alias]=TCAV:IN10:490` and the CSV agrees. Is the `KLYS:` override
   deliberate in the same way the `PROF:` ones were? Same question, different device class.
3. **`models/runners.py` CLI** — its four hardcoded `--model` choices become `get_model(args.model)`,
   which is a strict improvement but changes the accepted values.
4. **`BmadModelSpec.database_relpath` is dead config** — declared at `bmad/factory.py:24`, never
   read in `build_bmad_model`. Unrelated to this work; noted while reading.
