import os
from virtual_accelerator.models.cu_hxr import get_cu_hxr_bmad_model
import matplotlib.pyplot as plt

class TestCUHXR:
    def test_cu_hxr(self):
        model = get_cu_hxr_bmad_model()

        # set tracking
        model.set({"track_type": 1})

        # get initial OTR4 image
        image = model.get(["OTRS:IN20:711:Image:ArrayData"])["OTRS:IN20:711:Image:ArrayData"]
        assert image.shape == (1024, 1024)

        # set some control variables
        model.set({"QUAD:IN20:631:BDES": 0.0})

        # get updated OTR4 image
        updated_image = model.get(["OTRS:IN20:711:Image:ArrayData"])["OTRS:IN20:711:Image:ArrayData"]
        assert updated_image.shape == (1024, 1024)

        # make sure it changed
        assert not (image == updated_image).all()
