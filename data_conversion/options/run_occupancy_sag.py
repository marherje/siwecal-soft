#
# Steering of OccupancySagCalibrator: the measured chip baseline-sag map of a threshold set (common/mappings/
# occupancy_sag_<set>.txt, read by AdcDigitizer.OccupancySagTable). Driver: data_conversion/jobs/calibration/
# run_occupancy_sag.py (one Fill per run, then one Table per set).
#
#   SAG_MODE=Fill  SAG_INPUT_FILES=<chunks, comma list or glob>  SAG_OUTPUT=<run>.sagfill.txt  [SAG_MAX_ACQ=N]
#   SAG_MODE=Table SAG_FILL_FILES=<fill files, comma list>       SAG_OUTPUT=occupancy_sag_<set>.txt  SAG_LABEL="..."
#   k4run data_conversion/options/run_occupancy_sag.py
#
# Fill uses the th210 pedestals of the official tables for every set (calib_dir()/MuonCalib/pedestals/th210, as the
# map was measured) and the per-slab pad maps of common/mappings/slab_z_positions.yml; SAG_PEDESTAL_TH overrides.
import glob
import os

from Gaudi.Configuration import INFO
from Configurables import EventDataSvc, OccupancySagCalibrator
from k4FWCore import ApplicationMgr

from siwecal_common import paths
from siwecal_eventbuilder.calib_files import resolve_gaudi_calib_files
from siwecal_eventbuilder.geometry import load_slab_technology

mode = os.environ.get("SAG_MODE", "Fill")
out = os.environ.get("SAG_OUTPUT", "")
if not out:
    raise SystemExit("Set SAG_OUTPUT (Fill: the run's accumulator file; Table: occupancy_sag_<set>.txt)")

cal = OccupancySagCalibrator("OccupancySagCalibrator", Mode=mode, OutputFile=out, OutputLevel=INFO)
if mode == "Fill":
    raw = os.environ.get("SAG_INPUT_FILES", "")
    files = sorted(glob.glob(raw)) if any(ch in raw for ch in "*?[") else [f for f in raw.split(",") if f]
    if not files:
        raise SystemExit("Set SAG_INPUT_FILES to the siwecaldecoded chunks of one run (comma list or glob)")
    ped_hg, _, ped_lg, _ = resolve_gaudi_calib_files(os.environ.get("SAG_PEDESTAL_TH", "210"))
    slabs = load_slab_technology(paths.mapping_file("slab_z_positions.yml"), paths.mappings_dir())
    cal.InputFiles = files
    cal.PedestalFile = ped_hg
    cal.PedestalFileLowGain = ped_lg
    cal.PadMapDefaultFile = slabs.default_pad_map()
    cal.PadMapSlabOverrides = [f"{s}:{p}" for s, p in sorted(slabs.pad_map_overrides().items())]
    cal.MaxAcquisitions = int(os.environ.get("SAG_MAX_ACQ", "0"))
elif mode == "Table":
    fills = [f for f in os.environ.get("SAG_FILL_FILES", "").split(",") if f]
    if not fills:
        raise SystemExit("Set SAG_FILL_FILES to the Fill outputs of the runs of the set (comma list)")
    cal.FillFiles = fills
    cal.Label = os.environ.get("SAG_LABEL", "")
else:
    raise SystemExit(f"SAG_MODE must be Fill or Table, got {mode}")

ApplicationMgr(TopAlg=[cal], EvtSel="NONE", EvtMax=1, ExtSvc=[EventDataSvc("EventDataSvc")], OutputLevel=INFO)
