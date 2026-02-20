from typing import Any
from lume_bmad.transformer import BmadTransformer
from pytao import Tao

# from lcls_live.datamaps import get_datamaps


class SLAC2BmadTransformer(BmadTransformer):
    def get_tao_property(self, tao: Tao, control_name: str):
        """
        Get a property of an element from Bmad via Tao and
        return its value in control system (EPICS) units.

        # TODO: implment other variable types as needed,
        # utilize future datamaps functionality from lcls-live or database

        Parameters
        ----------
        tao: Tao
            Instance of the Tao class.
        control_name: str
            Name of the control variable to retrieve.

        Returns
        -------
        Any
            Value of the requested property.

        """

        # Map control name to element and attribute
        element, attr = self.control_name_to_bmad[control_name].split(" ")
        ele_attr = tao.ele_gen_attribs(element)
        if attr == "b1_gradient":
            # convert from Bmad units to EPICS units
            return ele_attr["B1_GRADIENT"] * ele_attr["L"] * 10
        else:
            return ele_attr[attr]

    def get_tao_commands(
        self, tao: Tao, pvdata: dict[str, Any], beam_path: str
    ) -> list[str]:
        """
        Get Tao commands to set a property of an element in Bmad via Tao. Handle
        mapping control names to element attributes and any necessary unit conversions as needed.

        Parameters
        ----------
        tao: Tao
            Instance of the Tao class.
        pvdata: dict[str, Any]
            Dictionary of control variable names and values to set
        beam_path: str
            Beam path in the Bmad lattice (e.g. "cu_hxr")

        Returns
        -------
        list[str]
            List of Tao commands to execute

        """
        tao_cmds = []
        for name, value in pvdata.items():
            element, attr = self.control_name_to_bmad[name].split(" ")
            if attr == "b1_gradient":
                # convert from EPICS units to Bmad units
                ele_attr = tao.ele_gen_attribs(element)
                bmad_value = value / (ele_attr["L"] * 10)
            else:
                bmad_value = value
            tao_cmd = f"set ele {element} {attr} = {bmad_value}"
            tao_cmds.append(tao_cmd)

        return tao_cmds
