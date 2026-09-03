"""Single entry point for building virtual-accelerator models by name.

from virtual_accelerator.registry import get_model, models_available

print(models_available)
model = get_model("bmad_cu_hxr", end_ele="OTR4", track_beam=True)
model = get_model(["impact_cu_inj", "bmad_cu_hxr"], handoff_loc="YAG03")
"""

import importlib
import logging
from typing import Any

from virtual_accelerator.registry.models import MODELS, ModelEntry

logger = logging.getLogger(__name__)

__all__ = ["get_model", "models_available", "list_models", "list_handoff_points"]


class _ModelCatalog(dict):
    """Mapping of model name -> description that prints as an aligned table."""

    def __repr__(self) -> str:
        if not self:
            return "(no models registered)"
        width = max(len(name) for name in self)
        return "\n".join(f"{name:<{width}}  {desc}" for name, desc in self.items())


models_available = _ModelCatalog(
    (name, entry.description) for name, entry in MODELS.items()
)


def list_models(facility: str | None = None, engine: str | None = None) -> list[str]:
    """Names of registered models, optionally filtered by facility or engine."""
    return [
        name
        for name, entry in MODELS.items()
        if (facility is None or entry.facility == facility)
        and (engine is None or entry.engine == engine)
    ]


def list_handoff_points(model_name: str) -> tuple[str, ...]:
    """Suggested start/end/handoff elements, in lattice order.

    A discovery aid, not an exhaustive list -- any lattice element may be used.
    """
    return _entry(model_name).handoff_points


def _entry(name: str) -> ModelEntry:
    try:
        return MODELS[name]
    except KeyError:
        raise KeyError(
            f"Unknown model {name!r}. Available: {', '.join(sorted(MODELS))}"
        ) from None


def _load_builder(entry: ModelEntry):
    module_path, _, func_name = entry.builder.partition(":")
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        extras = ", ".join(entry.extras) or "none"
        raise ImportError(
            f"Cannot import builder for {entry.name!r} ({entry.builder}). "
            f"Required extras: {extras}. Install with "
            f'`pip install "virtual-accelerator[{",".join(entry.extras)}]"`.'
        ) from exc
    return getattr(module, func_name)


def _normalize(name: str | None) -> str | None:
    """Canonicalise a user-supplied element name to upper case.

    Lattice element names are upper case everywhere. Tao is case-insensitive so a
    lower-case name would appear to work, but IMPACT's ``impact.ele[...]`` is a
    plain dict lookup, and the registry's own ``handoff_points`` and
    ``element_aliases`` lookups would silently miss.
    """
    return name if name is None else name.upper()


def _resolve_element(entry: ModelEntry, name: str) -> str:
    """Translate a standard element name into this model's engine-local name."""
    return entry.element_aliases.get(name, name)


def _check_element(entry: ModelEntry, name: str, role: str) -> None:
    """Validate a start/end/handoff element.

    Any element in the underlying lattice is allowed, so this cannot be an
    exhaustive check -- quads, markers and drifts are all legitimate and there are
    thousands of them. Screens *are* enumerated exhaustively though, so a
    screen-shaped name missing from ``handoff_points`` is a typo worth catching
    early rather than letting it fail deep inside Tao.
    """
    if name in entry.handoff_points:
        return
    if name.startswith(("OTR", "YAG", "PR")):
        raise ValueError(
            f"{name!r} is not an available {role} screen for {entry.name!r}. "
            f"Suggested points: {', '.join(entry.handoff_points)}"
        )


def _route_kwargs(
    entries: list[ModelEntry], kwargs: dict[str, Any]
) -> list[dict[str, Any]]:
    """Distribute flat kwargs across stages using the registry's declared params.

    Routing is a table lookup, not signature introspection, so the error
    messages can name the candidate stages.
    """
    routed: list[dict[str, Any]] = [{} for _ in entries]
    by_name = {entry.name: i for i, entry in enumerate(entries)}

    for key, value in kwargs.items():
        stage_name, sep, param = key.partition(".")
        if sep:
            if stage_name not in by_name:
                raise ValueError(
                    f"{key!r} targets stage {stage_name!r}, which is not in this model. "
                    f"Stages: {', '.join(by_name)}"
                )
            index = by_name[stage_name]
            if param not in entries[index].params:
                raise ValueError(
                    f"{param!r} is not a parameter of {stage_name!r}. "
                    f"Accepted: {', '.join(sorted(entries[index].params))}"
                )
            routed[index][param] = value
            continue

        accepting = [i for i, entry in enumerate(entries) if key in entry.params]
        if not accepting:
            known = sorted({p for entry in entries for p in entry.params})
            raise ValueError(
                f"{key!r} is not a parameter of any stage. Accepted: {', '.join(known)}"
            )

        broadcast = any(key in entries[i].broadcast_params for i in accepting)
        if len(accepting) > 1 and not broadcast:
            names = ", ".join(entries[i].name for i in accepting)
            raise ValueError(
                f"{key!r} is ambiguous across stages ({names}). "
                f'Qualify it, e.g. "{entries[accepting[0]].name}.{key}=...".'
            )
        for i in accepting:
            routed[i][key] = value

    return routed


def _build(
    entry: ModelEntry,
    call_kwargs: dict[str, Any],
    start_ele: str | None,
    end_ele: str | None,
) -> Any:
    kwargs = dict(call_kwargs)

    if start_ele is not None:
        if entry.start_param is None:
            raise ValueError(
                f"{entry.name!r} has a fixed start and does not accept start_ele."
            )
        _check_element(entry, start_ele, "start")
        kwargs[entry.start_param] = _resolve_element(entry, start_ele)

    if end_ele is not None:
        if entry.end_param is None:
            raise ValueError(
                f"{entry.name!r} has a fixed end and does not accept end_ele."
            )
        _check_element(entry, end_ele, "end")
        kwargs[entry.end_param] = _resolve_element(entry, end_ele)

    return _load_builder(entry)(**kwargs)


def _resolve_handoffs(
    entries: list[ModelEntry], handoff_loc: str | list[str] | None
) -> list[str]:
    """Determine the handoff element between each consecutive pair of stages."""
    n_handoffs = len(entries) - 1

    if handoff_loc is None:
        handoffs = []
        for upstream in entries[:-1]:
            if upstream.default_end is None:
                raise ValueError(
                    f"handoff_loc is required: {upstream.name!r} has no default end "
                    "to infer it from."
                )
            handoffs.append(upstream.default_end)
        return handoffs

    handoffs = [handoff_loc] if isinstance(handoff_loc, str) else list(handoff_loc)
    if len(handoffs) != n_handoffs:
        raise ValueError(
            f"{len(entries)} stages need {n_handoffs} handoff location(s), "
            f"got {len(handoffs)}."
        )
    return handoffs


def _validate_pair(upstream: ModelEntry, downstream: ModelEntry, handoff: str) -> None:
    if upstream.facility != downstream.facility:
        raise ValueError(
            f"Cannot stage {upstream.name!r} ({upstream.facility}) onto "
            f"{downstream.name!r} ({downstream.facility}): different facilities."
        )

    if downstream.start_param is None:
        reason = (
            "IMPACT models can only start at the cathode"
            if downstream.engine == "impact"
            else f"{downstream.name!r} has a fixed start"
        )
        raise ValueError(f"{downstream.name!r} cannot be a downstream stage: {reason}.")

    _check_element(upstream, handoff, "end")
    _check_element(downstream, handoff, "start")

    # Each linac model is registered for one standard handoff plane, so a mismatch
    # means the wrong pair was chosen -- silently re-slicing would leave a gap.
    if downstream.default_start is not None and handoff != downstream.default_start:
        alternatives = [
            name
            for name, entry in MODELS.items()
            if entry.facility == downstream.facility
            and entry.engine == downstream.engine
            and entry.default_start == handoff
        ]
        hint = f" Use {alternatives[0]!r} instead." if alternatives else ""
        raise ValueError(
            f"{upstream.name!r} hands off at {handoff!r} but {downstream.name!r} "
            f"starts at {downstream.default_start!r}.{hint}"
        )


def _strip_overlapping_variables(upstream, downstream, upstream_name, downstream_name):
    """Remove variables the downstream stage shares with the upstream stage.

    Both stages include the handoff element, so both publish its PVs and
    ``StagedModel`` would reject the pair as duplicates. The upstream stage owns
    them -- it is the stage that actually tracks the beam to that plane -- so they
    are unregistered from the downstream stage.

    A *writable* overlap means something different and worse: both stages would be
    driving the same magnet, and dropping it downstream would silently leave that
    stage tracking with a stale value. That is a slicing error, so it raises.
    """
    from lume.actions import WritableActionMixin

    downstream_vars = downstream.supported_variables
    overlap = sorted(set(upstream.supported_variables) & set(downstream_vars))
    if not overlap:
        return []

    writable = [
        name
        for name in overlap
        if isinstance(downstream_vars[name], WritableActionMixin)
    ]
    if writable:
        raise ValueError(
            f"{upstream_name!r} and {downstream_name!r} both control "
            f"{len(writable)} writable variable(s), so their extents overlap rather "
            f"than meeting at a plane: {', '.join(writable[:5])}"
            f"{' ...' if len(writable) > 5 else ''}. Check the handoff element."
        )

    if not hasattr(downstream, "unregister_action_variable"):
        raise TypeError(
            f"{downstream_name!r} shares {len(overlap)} variable(s) with "
            f"{upstream_name!r} but does not support unregister_action_variable, so "
            "the duplicates cannot be resolved."
        )

    for name in overlap:
        downstream.unregister_action_variable(name)
    logger.debug(
        "Removed %d variable(s) from %s already provided by %s",
        len(overlap),
        downstream_name,
        upstream_name,
    )
    return overlap


def get_model(
    spec: str | list[str],
    *,
    handoff_loc: str | list[str] | None = None,
    start_ele: str | None = None,
    end_ele: str | None = None,
    **kwargs: Any,
):
    """Build a model, or a staged chain of models, by registry name.

    Parameters
    ----------
    spec
        A registry name, or an ordered list of names to stage together.
    handoff_loc
        Element where each consecutive pair hands the beam over. Inferred from
        the upstream stage's fixed end when it has one. A list is required for
        more than two stages.
    start_ele, end_ele
        Overall extent. For a staged model these apply to the first and last
        stage respectively; interior extents come from ``handoff_loc``.
    **kwargs
        Builder parameters. For staged models, qualify an ambiguous parameter as
        ``"<model_name>.<param>"``.
    """
    start_ele, end_ele = _normalize(start_ele), _normalize(end_ele)

    if isinstance(spec, str):
        entry = _entry(spec)
        (routed,) = _route_kwargs([entry], kwargs)
        return _build(entry, routed, start_ele, end_ele)

    names = list(spec)
    if len(names) < 2:
        raise ValueError("Staging requires at least two models.")

    entries = [_entry(name) for name in names]
    handoffs = [_normalize(h) for h in _resolve_handoffs(entries, handoff_loc)]
    routed = _route_kwargs(entries, kwargs)

    for upstream, downstream, handoff in zip(entries, entries[1:], handoffs):
        _validate_pair(upstream, downstream, handoff)

    stages = []
    for i, entry in enumerate(entries):
        stage_start = start_ele if i == 0 else handoffs[i - 1]
        stage_end = end_ele if i == len(entries) - 1 else handoffs[i]

        stage_kwargs = dict(routed[i])
        # Every stage needs tracking on: a non-final stage has to produce
        # final_particles, and a non-first stage has to accept initial_particles
        # (lume_bmad rejects those unless track_type is 'beam').
        if "track_beam" in entry.params:
            stage_kwargs["track_beam"] = True

        stages.append(
            _build(
                entry,
                stage_kwargs,
                stage_start if entry.start_param else None,
                stage_end if entry.end_param else None,
            )
        )

    # Both stages include the handoff element and so publish its PVs. Resolve the
    # duplicates before StagedModel validation, which would otherwise reject them.
    for i in range(1, len(stages)):
        _strip_overlapping_variables(
            stages[i - 1], stages[i], entries[i - 1].name, entries[i].name
        )

    from lume.staged_model import StagedModel

    return StagedModel(stages)
