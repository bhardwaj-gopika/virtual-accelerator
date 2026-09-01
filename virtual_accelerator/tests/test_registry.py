"""Registry tests that need no engine dependencies or lattice checkouts."""

import pytest

from virtual_accelerator.registry import (
    _downstream_start,
    _normalize,
    _resolve_handoffs,
    _route_kwargs,
    get_model,
    list_diagnostics,
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

    def test_diagnostics_are_lattice_ordered(self):
        diags = list_diagnostics("bmad_cu_hxr")
        assert diags.index("YAG02") < diags.index("YAG03") < diags.index("OTR2")

    def test_impact_omits_unavailable_screens(self):
        # YAG01/OTR3 are commented out in the deck; OTR4 is past stop_1.
        diags = list_diagnostics("impact_cu_inj")
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
    def test_element_after_keys_are_diagnostics(self, name):
        entry = MODELS[name]
        assert set(entry.element_after) <= set(entry.diagnostics)

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

    def test_rejects_unavailable_diagnostic(self):
        with pytest.raises(ValueError, match="not an available end diagnostic"):
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

    def test_scalar_upstream_hands_off_at_the_diagnostic(self):
        # The surrogate publishes XRMS/YRMS only, so no PV collision.
        start = _downstream_start(
            MODELS["surrogate_cu_inj"], MODELS["bmad_cu_hxr"], "OTR2"
        )
        assert start == "OTR2"

    @pytest.mark.parametrize(
        ("handoff", "expected"), [("YAG03", "DL02A2"), ("OTR2", "DE06D")]
    )
    def test_imaging_upstream_starts_after_the_diagnostic(self, handoff, expected):
        # Both stages image the screen, so the downstream stage must skip it or
        # StagedModel would reject the pair on duplicate PVs.
        start = _downstream_start(
            MODELS["impact_cu_inj"], MODELS["bmad_cu_hxr"], handoff
        )
        assert start == expected

    def test_unrecorded_handoff_gives_actionable_error(self):
        entry = MODELS["bmad_cu_hxr"]
        stripped = type(entry)(**{**entry.__dict__, "element_after": {}})
        with pytest.raises(ValueError, match="element_after"):
            _downstream_start(MODELS["impact_cu_inj"], stripped, "OTR2")


class TestElementNameCase:
    """Element names are normalised at the API boundary.

    Tao is case-insensitive so lower case would appear to work, but IMPACT's
    impact.ele[...] is a dict lookup and the registry's own diagnostics and
    element_after lookups would silently miss.
    """

    @pytest.mark.parametrize("given", ["OTR4", "otr4", "Otr4", "oTr4"])
    def test_normalize_is_idempotent_upper(self, given):
        assert _normalize(given) == "OTR4"

    def test_normalize_passes_none_through(self):
        assert _normalize(None) is None

    def test_lowercase_bad_diagnostic_is_still_rejected(self):
        # Before normalisation this slipped past validation and failed later
        # inside Tao with a far worse message.
        with pytest.raises(ValueError, match="not an available end diagnostic"):
            get_model("impact_cu_inj", end_ele="otr99")

    def test_lowercase_valid_diagnostic_is_accepted(self):
        # Reaches the builder (and fails only because the extra is absent here),
        # proving validation no longer rejects it.
        with pytest.raises((ImportError, ValueError)) as excinfo:
            get_model("impact_cu_inj", end_ele="yag03")
        assert "not an available" not in str(excinfo.value)

    def test_lowercase_handoff_still_skips_the_screen(self):
        # Mirrors what get_model does: normalise, then resolve the handoff.
        handoff = _normalize("yag03")
        start = _downstream_start(
            MODELS["impact_cu_inj"], MODELS["bmad_cu_hxr"], handoff
        )
        assert start == "DL02A2"
