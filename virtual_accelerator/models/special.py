from virtual_accelerator.models.cu_hxr import get_cu_hxr_bmad_model
from virtual_accelerator.bmad.actions import RMatrixAction


def get_cu_hxr_rmat(start_element, end_element):
    """
    Dedicated model configuration optimized for CU HXR R-matrix calculations
    """
    model = get_cu_hxr_bmad_model(start_element, end_element, track_beam=False)

    # register R-matrix specific action variables
    model.register_action_variable(
        RMatrixAction(
            name=f"rmat:{start_element}_{end_element}",
            start_element=start_element,
            end_element=end_element,
        )
    )

    return model
