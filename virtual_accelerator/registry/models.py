"""Registry of available virtual-accelerator models.

Currently LCLS only; FACET-II entries are not registered yet.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelEntry:
    """Metadata describing one model and how to configure it.

    ``builder`` is a ``"module:function"`` string rather than a callable so that
    importing this module does not import pytao / torch / impact. Discovery must
    work with no optional dependencies installed.
    """

    name: str
    description: str
    facility: str
    engine: str
    builder: str
    extras: tuple[str, ...]

    params: dict[str, Any]
    """Configurable parameter name -> default. Also the allow-list for kwargs."""

    handoff_points: tuple[str, ...]
    """Suggested start/end/handoff elements, in lattice order.

    A discovery aid, **not** a restriction: any element name in the underlying
    lattice may be used. Screens are enumerated exhaustively, so a screen-shaped
    name absent from this tuple is a typo and is rejected; anything else passes
    through to the engine.

    Positions refer to the **entrance** face of the element. Bmad's
    ``-slice_lattice`` begins at an element's entrance and cannot begin at a
    midpoint, and IMPACT's ``impact.ele[name]["s"]`` is also the entrance, so the
    entrance is the only reference plane both engines express identically.
    """

    start_param: str | None = None
    """Builder kwarg controlling the start element, or None if not configurable."""

    end_param: str | None = None
    """Builder kwarg controlling the end element, or None if not configurable."""

    default_start: str | None = None
    default_end: str | None = None

    shared_params: frozenset[str] = frozenset()
    """Params that must hold the same value in every stage of a chain.

    The beam flows through the stages, so a particle count differing between them
    is physically meaningless. These are broadcast to every stage that declares
    them, and the per-stage ``"<model>.<param>"`` form is rejected for them --
    letting the values diverge would break the invariant, not configure anything.
    """

    @property
    def configurable_extent(self) -> bool:
        return self.start_param is not None or self.end_param is not None


_ALL_CU_HXR_SCREENS = (
    "YAG02",
    "YAG03",
    "OTRH1",
    "OTRH2",
    "OTR1",
    "OTR2",
    "OTR3",
    "OTR4",
    "OTR11",
    "OTR12",
    "OTR21",
    "OTRDMP",
)


MODELS: dict[str, ModelEntry] = {
    "impact_cu_inj": ModelEntry(
        name="impact_cu_inj",
        description="IMPACT-T LCLS injector, cathode -> YAG03",
        facility="lcls",
        engine="impact",
        builder="virtual_accelerator.models.cu_hxr:get_cu_inj_impact_model",
        extras=("impact",),
        params={"n_particles": 100, "end_element": "YAG03"},
        # YAG01 and OTR3 exist in the deck but their lines are commented out;
        # OTR4 is past stop_1 at z=16.5.
        handoff_points=("YAG02", "YAG03"),
        end_param="end_element",
        default_end="YAG03",
        shared_params=frozenset({"n_particles"}),
    ),
    "bmad_cu_hxr": ModelEntry(
        name="bmad_cu_hxr",
        description="Bmad CU-HXR linac, injector handoff -> END",
        facility="lcls",
        engine="bmad",
        builder="virtual_accelerator.models.cu_hxr:get_cu_hxr_bmad_model",
        extras=("bmad",),
        params={
            "start_element": "OTR2",
            "end_element": "END",
            "track_beam": False,
            "custom_beam_path": None,
        },
        # Starts wherever the upstream injector hands off: YAG03 from
        # impact_cu_inj, OTR2 from surrogate_cu_inj.
        handoff_points=("CATHODE", *_ALL_CU_HXR_SCREENS, "END"),
        start_param="start_element",
        end_param="end_element",
        default_start="OTR2",
        default_end="END",
    ),
    "surrogate_cu_inj": ModelEntry(
        name="surrogate_cu_inj",
        description="NN LCLS injector surrogate, cathode -> OTR2",
        facility="lcls",
        engine="surrogate",
        builder=(
            "virtual_accelerator.models.cu_hxr:get_cu_hxr_injector_surrogate_model"
        ),
        extras=("surrogate",),
        params={"n_particles": 1000},
        handoff_points=("OTR2",),
        default_end="OTR2",
        shared_params=frozenset({"n_particles"}),
    ),
    "cheetah_cu_hxr": ModelEntry(
        name="cheetah_cu_hxr",
        description="Cheetah nc_hxr, cathode -> END",
        facility="lcls",
        engine="cheetah",
        builder="virtual_accelerator.models.cu_hxr:get_cu_hxr_cheetah_model",
        extras=("cheetah",),
        params={"n_particles": 1000},
        handoff_points=(),
        shared_params=frozenset({"n_particles"}),
    ),
}
