# Virtual Accelerator (VA) Registry — README
## Overview
The virtual_accelerator.registry module provides a unified interface for loading, configuring, and chaining accelerator simulation models for the LCLS copper linac (CU). Models can be used standalone or chained together to simulate the full beamline from cathode to end.

### Installation
```bash
pip install git+https://github.com/slaclab/virtual-accelerator.git
```

### Quick Start
```python
from virtual_accelerator.registry import (
    get_model,
    models_available,
    list_handoff_points,
    common_handoff_points,
)
from virtual_accelerator.registry.models import MODELS
```

### Available Models
Print all registered models and their descriptions:

```python
>>> print(models_available)
impact_cu_inj     IMPACT-T LCLS injector, cathode -> YAG03
bmad_cu_hxr       Bmad CU-HXR linac, injector handoff -> END
surrogate_cu_inj  NN LCLS injector surrogate, cathode -> OTR2
cheetah_cu_hxr    Cheetah nc_hxr, cathode -> END
```

### Handoff Points
Each model exposes a set of suggested handoff points — named locations where beam tracking can start or stop, and where chained models exchange beam state.

```python
>>> for m in ["impact_cu_inj", "bmad_cu_hxr", "surrogate_cu_inj", "cheetah_cu_hxr"]:
...     print(m, list_handoff_points(m))

impact_cu_inj     ('CATHODE', 'YAG02', 'YAG03')
bmad_cu_hxr       ('CATHODE', 'YAG02', 'YAG03', 'OTRH1', 'OTRH2', 'OTR1', 'OTR2', 'OTR3', 'OTR4', 'OTR11', 'OTR12', 'OTR21', 'OTRDMP', 'END')
surrogate_cu_inj  ('CATHODE', 'OTR2')
cheetah_cu_hxr    ('CATHODE', 'END')
```

### Shared Handoff Points
`common_handoff_points()` returns the locations two models can actually hand over at
— the intersection of their handoff points, with `CATHODE` excluded since nothing is
upstream of it.

```python
>>> common_handoff_points("impact_cu_inj", "bmad_cu_hxr")
('YAG02', 'YAG03')

>>> common_handoff_points("surrogate_cu_inj", "bmad_cu_hxr")
('OTR2',)

>>> common_handoff_points("cheetah_cu_hxr", "bmad_cu_hxr")
()
```

### Element Aliases
Some handoff point names are aliases for internal model element names:

```python
>>> print(MODELS["impact_cu_inj"].element_aliases["CATHODE"])
GUN
```

### Loading a Single Model
Use get_model() with a model ID and an optional end_ele to stop tracking at a specific screen.

```python
>>> get_model("bmad_cu_hxr", end_ele="TD11")
<lume_bmad.model.LUMEBmadModel object at 0x150a9d370>

>>> get_model("impact_cu_inj", end_ele="YAG03")
<impact.model.distgen.distgen_impact_model.LUMEDistgenImpactModel object at 0x1666b6450>
```

### Error: Unknown Model Name
Model IDs must be exact. Partial names are not supported:

```python
>>> get_model("bmad_cu_hx", end_ele="TD11")
KeyError: "Unknown model 'bmad_cu_hx'. Available: bmad_cu_hxr, cheetah_cu_hxr, impact_cu_inj, surrogate_cu_inj"
```

### Error: Invalid End Element
end_ele must be one of the model's listed handoff points:

```python
>>> get_model("impact_cu_inj", end_ele="otr99")
ValueError: 'OTR99' is not an available end screen for 'impact_cu_inj'.
Suggested points: CATHODE, YAG02, YAG03
```

## Staged Models
Pass a list of two model IDs to get_model() to chain an injector model into a linac model. The upstream model hands off beam particles to the downstream model at a shared handoff point.

surrogate_cu_inj → bmad_cu_hxr — no `handoff_loc` needed, it is inferred from the
surrogate's fixed end (OTR2):
```python
>>> m = get_model(["surrogate_cu_inj", "bmad_cu_hxr"], end_ele="OTR4", n_particles=500)

>>> m.set({"QUAD:IN20:525:BCTRL": -10.0})

>>> print(m.get("OTR4_beam")["norm_emit_y"])
5.850087235892218e-07

>>> print(m.get("OTRS:IN20:711:Image:ArrayData").shape)
(1040, 1392)

>>> print([n.split("#")[0] for n in m.lume_model_instances[1].get("name")][:3])
['BEGINNING', 'OTR2', 'DE06D']
```

impact_cu_inj → bmad_cu_hxr — hand off at YAG03:

```python
>>> model = get_model(
...     ["impact_cu_inj", "bmad_cu_hxr"],
...     handoff_loc="YAG03",
...     end_ele="TD11",
...     n_particles=1000,
... )

>>> model.set({"QUAD:IN20:525:BCTRL": -7.5})

>>> print(model.get("OTR4_beam")["norm_emit_y"])
2.3638227838794528e-07
```

### Handoff Validation
`handoff_loc` must be a point both stages share. Anything else is rejected before any
model is built, so you do not pay for an IMPACT run to find out:

```python
>>> get_model(["impact_cu_inj", "bmad_cu_hxr"], handoff_loc="OTR4")
ValueError: 'OTR4' is not a shared handoff point for 'impact_cu_inj' -> 'bmad_cu_hxr'.
Available: YAG02, YAG03

>>> get_model(["impact_cu_inj", "bmad_cu_hxr"], handoff_loc="CATHODE")
ValueError: 'CATHODE' cannot be a handoff location: nothing is upstream of it.
```

Standard chains:

| Upstream | Downstream | Handoff |
|---|---|---|
| `impact_cu_inj` | `bmad_cu_hxr` | YAG03 |
| `surrogate_cu_inj` | `bmad_cu_hxr` | OTR2 (inferred) |

LCLS needs two handoff planes because its injector models end at different places and
neither can move. The NN surrogate predicts `OTRS:IN20:571` (OTR2) at 135 MeV and
cannot produce a beam at YAG03, which sits before L0B at 64 MeV.

### Overlapping Variables Are Handled For You
Both stages include the handoff element, so both publish its PVs — an IMPACT model
stopped at `YAG03` keeps the screen (it prunes to `s <= stop`) and so does a Bmad model
sliced from `YAG03`. `StagedModel` would reject the pair as duplicates.

`get_model()` resolves this automatically: the upstream stage owns those PVs, because it
is the stage that tracks the beam to that plane, so they are unregistered from the
downstream stage before the chain is assembled. Nothing is required of the caller.

The removal is surgical — only genuine collisions go. At YAG03 the IMPACT stage publishes
four PVs; the Bmad stage publishes those four plus `:X` and `:Y` centroid readbacks that
IMPACT does not provide. So the four move to IMPACT and the two Bmad-only ones stay:

```python
>>> m = get_model(["impact_cu_inj", "bmad_cu_hxr"], handoff_loc="YAG03", end_ele="TD11")
>>> imp, bmad = m.lume_model_instances

>>> sorted(v for v in imp.supported_variables if "IN20:351" in v)
['YAGS:IN20:351:Image:ArrayData', 'YAGS:IN20:351:Image:ArraySize0_RBV',
 'YAGS:IN20:351:Image:ArraySize1_RBV', 'YAGS:IN20:351:RESOLUTION']

>>> sorted(v for v in bmad.supported_variables if "IN20:351" in v)
['YAGS:IN20:351:X', 'YAGS:IN20:351:Y']
```

A *writable* overlap raises instead of being dropped. That means both stages drive the
same magnet — their extents overlap rather than meeting at a plane — and dropping it
downstream would leave that stage tracking a stale value.

### Targeting One Stage With kwargs
Plain kwargs apply to whichever stage declares them. `n_particles` is a *broadcast*
parameter, so it reaches every stage that accepts one; `start_ele` and `end_ele` apply to
the first and last stage respectively.

To target a specific stage, prefix the parameter with the model ID:

```python
>>> m = get_model(
...     ["impact_cu_inj", "bmad_cu_hxr"],
...     handoff_loc="YAG03",
...     **{"impact_cu_inj.n_particles": 200, "bmad_cu_hxr.end_ele": "TD11"},
... )
```

The dotted form always wins and is never ambiguous. Both the `get_model` spelling
(`end_ele`, `start_ele`) and the underlying builder spelling (`end_element`,
`start_element`) are accepted:

```python
>>> "bmad_cu_hxr.end_ele"      # same as
>>> "bmad_cu_hxr.end_element"
```

Ambiguity is an error rather than a guess. A non-broadcast parameter declared by more than
one stage must be qualified:

```python
>>> get_model(["impact_cu_inj", "bmad_cu_hxr"], end_element="TD11")
ValueError: 'end_element' is ambiguous across stages (impact_cu_inj, bmad_cu_hxr).
Qualify it, e.g. "impact_cu_inj.end_element=...".
```

Unknown parameters are rejected outright, listing what is accepted:

```python
>>> get_model("bmad_cu_hxr", n_particle=5)
ValueError: 'n_particle' is not a parameter of any stage.
Accepted: custom_beam_path, end_element, start_element, track_beam
```

To see what a model accepts:

```python
>>> MODELS["bmad_cu_hxr"].params
{'start_element': 'OTR2', 'end_element': 'END', 'track_beam': False, 'custom_beam_path': None}

>>> MODELS["impact_cu_inj"].broadcast_params
frozenset({'n_particles'})
```

## API Reference
```get_model(spec, *, handoff_loc=None, start_ele=None, end_ele=None, **kwargs)```

| Parameter | Type | Description |
|---|---|---|
| `spec` | str or list[str] | Model ID, or `[upstream, downstream]` to chain |
| `handoff_loc` | str | Where the stages exchange beam. Inferred from the upstream model's standard end when omitted. Must be in `common_handoff_points()` |
| `start_ele` | str | Element to start tracking from (first stage) |
| `end_ele` | str | Element to stop tracking at (last stage) |
| `**kwargs` | any | Builder parameters. Prefix with `"<model_id>."` to target one stage |

For staged chains `get_model()` also removes variables that both stages publish at the
handoff, and forces beam tracking on for every stage that supports it.

```models_available```
Printable summary of all registered models and their descriptions.

```list_handoff_points(model_id: str) -> tuple[str, ...]```

Returns the suggested handoff point names for a given model, in lattice order. A
discovery aid, not a restriction.

```common_handoff_points(*model_ids: str) -> tuple[str, ...]```

Returns the handoff points shared by all named models, in lattice order, excluding
`CATHODE`. Use it to see where two models can legally hand over.
