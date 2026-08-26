from virtual_accelerator.models.cu_hxr import get_cu_inj_impact_model

def test_cu_inj_impact_model():
    model = get_cu_inj_impact_model()
    assert model is not None