#
# Steering of TriggerTurnOnCalibrator: the trigger turn-on of a threshold set and of each of its slabs, the values
# the digitiser takes from common/mappings/digi_calibration.yml. Driver: data_conversion/jobs/calibration/
# run_trigger_turnon.py.
#
#   TURNON_MODE=Fill TURNON_SET=th210 TURNON_INPUT_FILES=<chunks, comma list or glob> TURNON_OUTPUT=<run>.turnon.txt
#        [TURNON_PER_CHUNK=40]   (pedestal and MIP tables: calib_dir()/MuonCalib/{pedestals,mips}/<set>/*highgain*)
#   TURNON_MODE=Fit  TURNON_FILL_FILES=<fill files, comma list> TURNON_OUTPUT=turnon_<set>.txt TURNON_LABEL="..."
#   k4run data_conversion/options/run_trigger_turnon.py
import glob
import os

from Gaudi.Configuration import INFO
from Configurables import EventDataSvc, TriggerTurnOnCalibrator
from k4FWCore import ApplicationMgr

from siwecal_common import paths

mode = os.environ.get("TURNON_MODE", "Fill")
out = os.environ.get("TURNON_OUTPUT", "")
if not out:
    raise SystemExit("Set TURNON_OUTPUT (Fill: the run's histogram file; Fit: the parameter file)")

cal = TriggerTurnOnCalibrator("TriggerTurnOnCalibrator", Mode=mode, OutputFile=out, OutputLevel=INFO)
if mode == "Fill":
    raw = os.environ.get("TURNON_INPUT_FILES", "")
    files = sorted(glob.glob(raw)) if any(ch in raw for ch in "*?[") else [f for f in raw.split(",") if f]
    th = os.environ.get("TURNON_SET", "")
    if not files or not th:
        raise SystemExit("Set TURNON_INPUT_FILES (decoded chunks of one run) and TURNON_SET (th210|th220|th230)")

    def table(kind):
        hits = sorted(glob.glob(os.path.join(paths.muon_calib_dir(), kind, th, "*highgain*")))
        if not hits:
            raise SystemExit(f"no high-gain {kind} table for {th} under {paths.muon_calib_dir()}")
        return hits[0]
    cal.InputFiles = files
    cal.PedestalFile = table("pedestals")
    cal.MipFile = table("mips")
    cal.AcquisitionsPerChunk = int(os.environ.get("TURNON_PER_CHUNK", "40"))
elif mode == "Fit":
    fills = [f for f in os.environ.get("TURNON_FILL_FILES", "").split(",") if f]
    if not fills:
        raise SystemExit("Set TURNON_FILL_FILES to the Fill outputs (comma list)")
    cal.FillFiles = fills
    cal.Label = os.environ.get("TURNON_LABEL", "")
else:
    raise SystemExit(f"TURNON_MODE must be Fill or Fit, got {mode}")

ApplicationMgr(TopAlg=[cal], EvtSel="NONE", EvtMax=1, ExtSvc=[EventDataSvc("EventDataSvc")], OutputLevel=INFO)
