"""
siwecal_eventbuilder: the Python side of the Gaudi event builder (EcalEventBuilder, data_conversion/src).

The event building itself is Gaudi's only (data_conversion/options/run_event_builder.py); the pure-Python event
builder of siwecal-tb2026 duplicated it and is retired. What stays is what the drivers need to configure it:

* :mod:`.calib_files`   -- the MuonCalib tables, the LG->HG anchor and the pad maps of a run.
* :mod:`.geometry`      -- the slab description (thin view of siwecal_common.slab_description) and slab z / W.
* :mod:`.run_settings`  -- the threshold DAC of a run from its Run_Settings.txt.
"""
from .geometry import DetectorGeometry, W_X0_MM, load_slab_technology, load_slab_w_thickness_mm
from .run_settings import read_threshold_dac, run_settings_path

__all__ = ["DetectorGeometry", "W_X0_MM", "load_slab_technology", "load_slab_w_thickness_mm",
           "read_threshold_dac", "run_settings_path"]
