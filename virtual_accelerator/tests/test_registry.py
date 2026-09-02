"""Registry tests that need no engine dependencies or lattice checkouts."""

import pytest

from lume.actions import WritableActionMixin

from virtual_accelerator.registry import (
    _normalize,
    _resolve_handoffs,
    _route_kwargs,
    _strip_overlapping_variables,
    get_model,
    list_handoff_points,
    list_models,
    models_available,
)
from virtual_accelerator.registry.models import MODELS


class TestDiscovery:
    def test_all_entries_listed(self):
        assert set(models_available) == set(MODELS)

    def test_repr_is_aligned_table(self):
        text = repr(models_available)
        assert "impact_cu_inj" in text
        assert len(text.splitlines()) == len(MODELS)

    def test_filter_by_engine_and_facility(self):
        assert list_models(engine="bmad") == ["bmad_cu_hxr"]
        assert set(list_models(facility="lcls")) == set(MODELS)
        assert list_models(facility="facet2") == []

    def test_handoff_points_are_lattice_ordered(self):
        diags = list_handoff_points("bmad_cu_hxr")
        assert diags.index("YAG02") < diags.index("YAG03") < diags.index("OTR2")

    def test_impact_omits_unavailable_screens(self):
        # YAG01/OTR3 are commented out in the deck; OTR4 is past stop_1.
        diags = list_handoff_points("impact_cu_inj")
        assert "OTR2" in diags
        for absent in ("YAG01", "OTR3", "OTR4"):
            assert absent not in diags


class TestEntryIntegrity:
    @pytest.mark.parametrize("name", sorted(MODELS))
    def test_builder_is_importable_path(self, name):
        module_path, sep, func = MODELS[name].builder.partition(":")
        assert sep and module_path.startswith("virtual_accelerator.") and func

    @pytest.mark.parametrize("name", sorted(MODELS))
    def test_extent_params_are_declared(self, name):
        entry = MODELS[name]
        for param in (entry.start_param, entry.end_param):
            if param is not None:
                assert param in entry.params

    @pytest.mark.parametrize("name", sorted(MODELS))
    def test_broadcast_params_are_declared(self, name):
        entry = MODELS[name]
        assert entry.broadcast_params <= set(entry.params)

    @pytest.mark.parametrize("name", sorted(MODELS))
    def test_element_alias_keys_are_handoff_points(self, name):
        entry = MODELS[name]
        assert set(entry.element_aliases) <= set(entry.handoff_points)

    @pytest.mark.parametrize("name", sorted(MODELS))
    def test_defaults_are_consistent(self, name):
        entry = MODELS[name]
        if entry.default_start and entry.start_param:
            assert entry.params[entry.start_param] == entry.default_start
        if entry.default_end and entry.end_param:
            assert entry.params[entry.end_param] == entry.default_end


class TestValidation:
    def test_unknown_model(self):
        with pytest.raises(KeyError, match="Unknown model"):
            get_model("bmad_does_not_exist")

    def test_rejects_unavailable_screen(self):
        with pytest.raises(ValueError, match="not an available end screen"):
            get_model("impact_cu_inj", end_ele="OTR4")

    def test_rejects_impact_as_downstream_stage(self):
        with pytest.raises(ValueError, match="only start at the cathode"):
            get_model(["bmad_cu_hxr", "impact_cu_inj"], handoff_loc="OTR2")

    def test_rejects_start_ele_on_fixed_extent_model(self):
        with pytest.raises(ValueError, match="fixed start"):
            get_model("surrogate_cu_inj", start_ele="OTR2")

    def test_rejects_single_model_list(self):
        with pytest.raises(ValueError, match="at least two models"):
            get_model(["bmad_cu_hxr"])

    def test_rejects_wrong_handoff_count(self):
        with pytest.raises(ValueError, match="handoff location"):
            get_model(["surrogate_cu_inj", "bmad_cu_hxr"], handoff_loc=["OTR2", "OTR3"])


class TestKwargRouting:
    def test_unknown_kwarg_rejected(self):
        with pytest.raises(ValueError, match="not a parameter of any stage"):
            _route_kwargs([MODELS["bmad_cu_hxr"]], {"n_particle": 5})

    def test_broadcast_reaches_every_declaring_stage(self):
        entries = [MODELS["surrogate_cu_inj"], MODELS["cheetah_cu_hxr"]]
        routed = _route_kwargs(entries, {"n_particles": 42})
        assert routed == [{"n_particles": 42}, {"n_particles": 42}]

    def test_routes_to_single_declaring_stage(self):
        entries = [MODELS["surrogate_cu_inj"], MODELS["bmad_cu_hxr"]]
        routed = _route_kwargs(entries, {"track_beam": True})
        assert routed == [{}, {"track_beam": True}]

    def test_dotted_form_targets_one_stage(self):
        entries = [MODELS["surrogate_cu_inj"], MODELS["cheetah_cu_hxr"]]
        routed = _route_kwargs(entries, {"cheetah_cu_hxr.n_particles": 7})
        assert routed == [{}, {"n_particles": 7}]

    def test_dotted_form_rejects_unknown_stage(self):
        with pytest.raises(ValueError, match="not in this model"):
            _route_kwargs([MODELS["bmad_cu_hxr"]], {"nope.track_beam": True})

    def test_dotted_form_rejects_unknown_param(self):
        with pytest.raises(ValueError, match="not a parameter of"):
            _route_kwargs([MODELS["bmad_cu_hxr"]], {"bmad_cu_hxr.bogus": 1})


class TestHandoffResolution:
    def test_inferred_from_upstream_fixed_end(self):
        entries = [MODELS["surrogate_cu_inj"], MODELS["bmad_cu_hxr"]]
        assert _resolve_handoffs(entries, None) == ["OTR2"]

    def test_explicit_handoff_is_used_verbatim(self):
        entries = [MODELS["impact_cu_inj"], MODELS["bmad_cu_hxr"]]
        assert _resolve_handoffs(entries, "YAG03") == ["YAG03"]


class _FakeStage:
    """Minimal stand-in for a LUMEModel with registerable action variables."""

    def __init__(self, variables):
        self._vars = dict(variables)

    @property
    def supported_variables(self):
        return dict(self._vars)

    def unregister_action_variable(self, name):
        return self._vars.pop(name)


class _ReadOnlyVar:
    pass


class _WritableVar(WritableActionMixin):
    def _get(self, simulator):  # pragma: no cover - never invoked
        raise NotImplementedError

    def _set(self, simulator, value):  # pragma: no cover - never invoked
        raise NotImplementedError


class TestOverlapRemoval:
    """The handoff element belongs to both stages, so both publish its PVs.

    The upstream stage owns them since it tracks the beam to that plane, so they
    are unregistered downstream rather than moving the downstream start element.
    """

    def test_shared_read_only_variables_are_removed_downstream(self):
        up = _FakeStage({"SCREEN:IMAGE": _ReadOnlyVar(), "UP:ONLY": _ReadOnlyVar()})
        down = _FakeStage({"SCREEN:IMAGE": _ReadOnlyVar(), "DOWN:ONLY": _ReadOnlyVar()})
        removed = _strip_overlapping_variables(up, down, "up", "down")
        assert removed == ["SCREEN:IMAGE"]
        assert set(down.supported_variables) == {"DOWN:ONLY"}
        # the upstream stage keeps its copy
        assert "SCREEN:IMAGE" in up.supported_variables

    def test_no_overlap_is_a_no_op(self):
        up = _FakeStage({"UP:ONLY": _ReadOnlyVar()})
        down = _FakeStage({"DOWN:ONLY": _ReadOnlyVar()})
        assert _strip_overlapping_variables(up, down, "up", "down") == []
        assert set(down.supported_variables) == {"DOWN:ONLY"}

    def test_writable_overlap_raises_instead_of_silently_dropping(self):
        # Both stages driving the same magnet means the extents overlap rather
        # than meeting at a plane; dropping it downstream would leave that stage
        # tracking with a stale value.
        up = _FakeStage({"QUAD:BCTRL": _WritableVar()})
        down = _FakeStage({"QUAD:BCTRL": _WritableVar()})
        with pytest.raises(ValueError, match="writable variable"):
            _strip_overlapping_variables(up, down, "up", "down")
        assert "QUAD:BCTRL" in down.supported_variables

    def test_stage_without_unregister_support_raises(self):
        class Fixed:
            supported_variables = {"SHARED": _ReadOnlyVar()}

        up = _FakeStage({"SHARED": _ReadOnlyVar()})
        with pytest.raises(TypeError, match="unregister_action_variable"):
            _strip_overlapping_variables(up, Fixed(), "up", "down")


class TestElementNameCase:
    """Element names are normalised at the API boundary.

    Tao is case-insensitive so lower case would appear to work, but IMPACT's
    impact.ele[...] is a dict lookup and the registry's own handoff_points and
    element_aliases lookups would silently miss.
    """

    @pytest.mark.parametrize("given", ["OTR4", "otr4", "Otr4", "oTr4"])
    def test_normalize_is_idempotent_upper(self, given):
        assert _normalize(given) == "OTR4"

    def test_normalize_passes_none_through(self):
        assert _normalize(None) is None

    def test_lowercase_bad_screen_is_still_rejected(self):
        # Before normalisation this slipped past validation and failed later
        # inside Tao with a far worse message.
        with pytest.raises(ValueError, match="not an available end screen"):
            get_model("impact_cu_inj", end_ele="otr99")

    def test_lowercase_valid_screen_is_accepted(self):
        # Reaches the builder (and fails only because the extra is absent here),
        # proving validation no longer rejects it.
        with pytest.raises((ImportError, ValueError)) as excinfo:
            get_model("impact_cu_inj", end_ele="yag03")
        assert "not an available" not in str(excinfo.value)

    def test_lowercase_handoff_normalises_before_resolution(self):
        entries = [MODELS["impact_cu_inj"], MODELS["bmad_cu_hxr"]]
        handoffs = [_normalize(h) for h in _resolve_handoffs(entries, "yag03")]
        assert handoffs == ["YAG03"]
