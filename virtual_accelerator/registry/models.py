"""Registry of available virtual-accelerator models.

Currently LCLS only; FACET-II entries are not registered yet.
"""

from dataclasses import dataclass, field
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

    diagnostics: tuple[str, ...]
    """Standard-named diagnostics usable as handoff points, in lattice order."""

    start_param: str | None = None
    """Builder kwarg controlling the start element, or None if not configurable."""

    end_param: str | None = None
    """Builder kwarg controlling the end element, or None if not configurable."""

    default_start: str | None = None
    default_end: str | None = None

    broadcast_params: frozenset[str] = frozenset()
    """Params safe to send to every stage of a staged model, e.g. n_particles."""

    images_diagnostics: bool = True
    """Whether this model publishes full screen-image PVs for its diagnostics.

    Two stages that both image the handoff diagnostic would publish the same PVs
    and be rejected by StagedModel, so the downstream stage has to start just
    past it. Surrogates publish only scalars (XRMS/YRMS) and so never collide.
    """

    element_after: dict[str, str] = field(default_factory=dict)
    """Diagnostic -> the element immediately downstream of it.

    Only needed for entries that can be a downstream stage, and only for
    diagnostics used as handoff points. Bmad's ``s`` is the exit face, so
    slicing from ``DL02A2`` begins at exactly YAG03's position while excluding
    the screen itself.
    """

    element_aliases: dict[str, str] = field(default_factory=dict)
    """Standard name -> this engine's local name.

    Empty for every current entry: diagnostic names already agree between Bmad
    and IMPACT in both facilities. Kept as the place a future rename would go.
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
        description="IMPACT-T LCLS injector, cathode -> OTR2",
        facility="lcls",
        engine="impact",
        builder="virtual_accelerator.models.cu_hxr:get_cu_inj_impact_model",
        extras=("impact",),
        params={"n_particles": 100, "end_element": "OTR2"},
        # YAG01 and OTR3 exist in the deck but their lines are commented out;
        # OTR4 is past stop_1 at z=16.5.
        diagnostics=("YAG02", "YAG03", "OTR1", "OTR2"),
        end_param="end_element",
        default_end="OTR2",
        broadcast_params=frozenset({"n_particles"}),
    ),
    "bmad_cu_hxr": ModelEntry(
        name="bmad_cu_hxr",
        description="Bmad CU-HXR, gun -> undulator/dump",
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
        diagnostics=_ALL_CU_HXR_SCREENS,
        start_param="start_element",
        end_param="end_element",
        default_start="OTR2",
        default_end="END",
        # Verified against the lattice: each value's entrance face sits exactly at
        # the screen's s. OTR11/OTR21 are omitted because both are followed by an
        # element named DDG4, which is ambiguous and so unusable as a slice start.
        element_after={
            "YAG02": "DL01G",
            "YAG03": "DL02A2",
            "OTRH1": "DH03A",
            "OTRH2": "DH02B",
            "OTR1": "DE05C",
            "OTR2": "DE06D",
            "OTR3": "DE07",
            "OTR4": "DB00B",
        },
    ),
    "surrogate_cu_inj": ModelEntry(
        name="surrogate_cu_inj",
        description="NN LCLS injector surrogate, fixed cathode -> OTR2",
        facility="lcls",
        engine="surrogate",
        builder=(
            "virtual_accelerator.models.cu_hxr:get_cu_hxr_injector_surrogate_model"
        ),
        extras=("surrogate",),
        params={"n_particles": 1000},
        diagnostics=("OTR2",),
        default_end="OTR2",
        broadcast_params=frozenset({"n_particles"}),
        images_diagnostics=False,
    ),
    "cheetah_cu_hxr": ModelEntry(
        name="cheetah_cu_hxr",
        description="Cheetah nc_hxr",
        facility="lcls",
        engine="cheetah",
        builder="virtual_accelerator.models.cu_hxr:get_cu_hxr_cheetah_model",
        extras=("cheetah",),
        params={"n_particles": 1000},
        diagnostics=(),
        broadcast_params=frozenset({"n_particles"}),
    ),
}
