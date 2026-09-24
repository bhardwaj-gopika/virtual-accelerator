import pytest

from virtual_accelerator.bmad.factory import _wrap_bmad_set_with_rollback


class _FakeVariable:
    def __init__(self, value):
        self.value = value
        self.read_only = False

    def _get(self, _simulator):
        return self.value

    def _set(self, _simulator, value):
        self.value = value


class _FakeSimulator:
    def __init__(self):
        self.commands = []

    def cmd(self, command):
        self.commands.append(command)


class _FakeModel:
    def __init__(self):
        self.simulator = _FakeSimulator()
        self.supported_variables = {"bend": _FakeVariable(1.0)}
        self.refresh_calls = 0
        self.update_calls = 0

    def _set(self, values):
        self.supported_variables["bend"]._set(self.simulator, values["bend"])
        raise RuntimeError("bad lattice setting")

    def _refresh_dynamic_action_variables(self):
        self.refresh_calls += 1

    def update_state(self):
        self.update_calls += 1


def test_wrap_bmad_set_with_rollback_restores_previous_value():
    model = _wrap_bmad_set_with_rollback(_FakeModel())

    with pytest.raises(RuntimeError, match="bad lattice setting"):
        model._set({"bend": 0.98})

    assert model.supported_variables["bend"].value == 1.0
    assert model.refresh_calls == 1
    assert model.update_calls == 1
    assert model.simulator.commands == [
        "set global lattice_calc_on = F",
        "set global lattice_calc_on = T",
    ]
