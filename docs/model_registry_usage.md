# Virtual Accelerator (VA) Registry — README
## Overview
The virtual_accelerator.registry module provides a unified interface for loading, configuring, and chaining accelerator simulation models for the LCLS copper linac (CU). Models can be used standalone or chained together to simulate the full beamline from cathode to end.

### Installation
```bash
pip install git+https://github.com/slaclab/virtual-accelerator
```

### Quick Start
```python
from virtual_accelerator.registry import get_model, models_available, list_handoff_points
from virtual_accelerator.registry.models import MODELS
```

### Available Models
Print all registered models and their descriptions:

```python
>>> print(models_available)
impact_cu_inj      IMPACT-T LCLS injector, cathode -> YAG03
bmad_cu_hxr_yag03  Bmad CU-HXR linac, YAG03 -> END (pairs with impact_cu_inj)
bmad_cu_hxr_otr2   Bmad CU-HXR linac, OTR2 -> END (pairs with surrogate_cu_inj)
surrogate_cu_inj   NN LCLS injector surrogate, fixed cathode -> OTR2
cheetah_cu_hxr     Cheetah nc_hxr
```

### Handoff Points
Each model exposes a set of handoff points — named screen locations where beam tracking can start or stop, and where chained models exchange beam state.

```python
>>> for m in ["impact_cu_inj", "bmad_cu_hxr_yag03", "bmad_cu_hxr_otr2", "surrogate_cu_inj", "cheetah_cu_hxr"]:
...     print(m, list_handoff_points(m))

impact_cu_inj      ('CATHODE', 'YAG02', 'YAG03', 'OTR1', 'OTR2')
bmad_cu_hxr_yag03  ('CATHODE', 'YAG02', 'YAG03', 'OTRH1', 'OTRH2', 'OTR1', 'OTR2', 'OTR3', 'OTR4', 'OTR11', 'OTR12', 'OTR21', 'OTRDMP', 'END')
bmad_cu_hxr_otr2   ('CATHODE', 'YAG02', 'YAG03', 'OTRH1', 'OTRH2', 'OTR1', 'OTR2', 'OTR3', 'OTR4', 'OTR11', 'OTR12', 'OTR21', 'OTRDMP', 'END')
surrogate_cu_inj   ('CATHODE', 'OTR2')
cheetah_cu_hxr     ()
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
>>> get_model("bmad_cu_hxr_otr2", end_ele="TD11")
<lume_bmad.model.LUMEBmadModel object at 0x150a9d370>

>>> get_model("impact_cu_inj", end_ele="OTR2")
<impact.model.distgen.distgen_impact_model.LUMEDistgenImpactModel object at 0x1666b6450>
```
Note: Unrecognized element types (e.g. solrf, Lcavity, Unknown) are skipped during model initialisation. These warnings are informational and do not prevent the model from loading.

### Error: Unknown Model Name
Model IDs must be exact. Partial names are not supported:

```python
>>> get_model("bmad_cu_hxr", end_ele="TD11")
KeyError: "Unknown model 'bmad_cu_hxr'. Available: bmad_cu_hxr_otr2, bmad_cu_hxr_yag03, cheetah_cu_hxr, impact_cu_inj, surrogate_cu_inj"
```

### Error: Invalid End Element
end_ele must be one of the model's listed handoff points:

```python
>>> get_model("impact_cu_inj", end_ele="otr99")
ValueError: 'OTR99' is not an available end screen for 'impact_cu_inj'.
Suggested points: CATHODE, YAG02, YAG03, OTR1, OTR2
```

## Staged Models
Pass a list of two model IDs to get_model() to chain an injector model into a linac model. The upstream model hands off beam particles to the downstream model at a shared handoff point.

surrogate_cu_inj → bmad_cu_hxr_otr2
```python
>>> m = get_model(["surrogate_cu_inj", "bmad_cu_hxr_otr2"], end_ele="OTR4", n_particles=500)

>>> m.set({"QUAD:IN20:525:BCTRL": -10.0})

>>> print(m.get("OTR4_beam")["norm_emit_y"])
5.850087235892218e-07

>>> print(m.get("OTRS:IN20:711:Image:ArrayData").shape)
(1040, 1392)

>>> print([n.split("#")[0] for n in m.lume_model_instances[1].get("name")][:3])
['BEGINNING', 'OTR2', 'DE06D']
```

impact_cu_inj → bmad_cu_hxr_yag03

When impact_cu_inj is the upstream model, use bmad_cu_hxr_yag03 (which starts at YAG03) and specify handoff_loc:

```python
>>> model = get_model(
...     ["impact_cu_inj", "bmad_cu_hxr_yag03"],
...     handoff_loc="YAG03",
...     end_ele="TD11",
...     n_particles=1000,
... )

>>> model.set({"QUAD:IN20:525:BCTRL": -7.5})

>>> print(model.get("OTR4_beam")["norm_emit_y"])
2.3638227838794528e-07
```

### Pairing Rules
Upstream and downstream models must share a compatible handoff location. Mismatched pairs raise a descriptive error:

```python
>>> get_model(["surrogate_cu_inj", "bmad_cu_hxr_yag03"], end_ele="TD11", n_particles=500)
ValueError: 'surrogate_cu_inj' hands off at 'OTR2' but 'bmad_cu_hxr_yag03' starts at 'YAG03'.
Use 'bmad_cu_hxr_otr2' instead.

```
Valid pairs:

| Upstream | Downstream	| Handoff Location |\
| impact_cu_inj | bmad_cu_hxr_yag03 | YAG03 |\
| surrogate_cu_inj |	bmad_cu_hxr_otr2 | OTR2|


### Advanced: Stripping Overlapping Variables
When building chained models manually, use _strip_overlapping_variables to remove output variables from the downstream model that are already owned by the upstream model. This avoids variable conflicts.

```python
from virtual_accelerator.models.cu_hxr import get_cu_hxr_bmad_model
from virtual_accelerator.registry import _strip_overlapping_variables

bm = get_cu_hxr_bmad_model(start_element="YAG03", end_element="OTR4", track_beam=True)

# Identify overlapping variables
yag = sorted(v for v in bm.supported_variables if "IN20:351" in v)

# Construct a mock upstream model exposing only those variables
class Up:
    supported_variables = {n: bm.supported_variables[n] for n in yag}

# Strip them from the downstream model
removed = _strip_overlapping_variables(Up(), bm, "upstream", "bmad_cu_hxr")

>>> print(removed)
['YAGS:IN20:351:Image:ArrayData', 'YAGS:IN20:351:Image:ArraySize0_RBV',
 'YAGS:IN20:351:Image:ArraySize1_RBV', 'YAGS:IN20:351:RESOLUTION',
 'YAGS:IN20:351:X', 'YAGS:IN20:351:Y']

>>> print(len(bm.supported_variables))  # 318 → 312
312
```

Note: _strip_overlapping_variables is a private utility. Prefer using get_model() with a list of model IDs, which handles this automatically.

## API Reference
```get_model(spec, *, end_ele=None, start_ele=None, handoff_loc=None, n_particles=None)```

|Parameter | Type |	Description |\
|spec |	str or list[str] |	Model ID or [upstream, downstream] pair|\
|end_ele |	str |	Screen name to stop tracking at|\
|start_ele | str | Screen name to start tracking from|\
|handoff_loc |	str |	Explicit handoff point when chaining models|\
|n_particles |	int	 | Number of macro-particles for beam tracking|

```models_available```
Printable summary of all registered models and their descriptions.

```list_handoff_points(model_id: str) -> tuple[str, ...]```

Returns the available handoff point names for a given model.
