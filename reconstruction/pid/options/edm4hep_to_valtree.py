#
# Gaudi/k4FWCore steering: an existing PID EDM4hep file -> its valtree, every event, nothing recomputed.
#
#   PID_FILE=ecal_<label>.edm4hep.root ECAL_VALTREE_OUT=ecal_<label>.valtree.root \
#       k4run reconstruction/pid/options/edm4hep_to_valtree.py
#
# The same EcalValTreeWriter as run_pid.py (ECAL_VALTREE_OUT there), without selection and without EDM4hep output.
# Driver: reconstruction/jobs/pid_to_valtree.py.
#   VALTREE_MIP_THRESHOLDS   comma list of the file's MIP-variant blocks ("0.5,1.0" for validation-mode files,
#                            "" for physics mode). Unset: read from the file's ECalPid_shapeParameterNames metadata.
#
import os
import re

from Gaudi.Configuration import INFO
from Configurables import EventDataSvc, EcalValTreeWriter
from k4FWCore import ApplicationMgr, IOSvc

pid_file = os.environ.get("PID_FILE", "")
valtree_out = os.environ.get("ECAL_VALTREE_OUT", "")
if not pid_file or not valtree_out:
    raise SystemExit("Set PID_FILE (input ecal_<label>.edm4hep.root) and ECAL_VALTREE_OUT")

SHAPE_PARAM_META = "ECalPid_shapeParameterNames"


def mip_thresholds_from_metadata(path):
    """The MIP thresholds of the mip<t>_* blocks in the file's shapeParameterNames ("mip05" -> 0.5, "mip1" -> 1.0)."""
    import podio.root_io as rio

    for frame in rio.Reader(path).get("metadata"):
        names = [n.decode() if isinstance(n, bytes) else str(n) for n in frame.get_parameter(SHAPE_PARAM_META)]
        thresholds = []
        for n in names:
            m = re.fullmatch(r"mip(\d+)_nhit", n)   # one per block (not mip05_e_over_nhit)
            if m:
                digits = m.group(1)
                thresholds.append(float(digits[0] + "." + digits[1:]) if len(digits) > 1 else float(digits))
        return thresholds
    raise SystemExit(f"{path}: no {SHAPE_PARAM_META} metadata; set VALTREE_MIP_THRESHOLDS")


_raw = os.environ.get("VALTREE_MIP_THRESHOLDS")
mip_thresholds = ([float(t) for t in _raw.split(",") if t.strip()] if _raw is not None
                  else mip_thresholds_from_metadata(pid_file))
print("valtree:", pid_file, "->", valtree_out, "MipThresholds", mip_thresholds)

svc = IOSvc("IOSvc")
svc.Input = pid_file

ApplicationMgr(TopAlg=[EcalValTreeWriter("EcalValTreeWriter", OutputFile=valtree_out, MipThresholds=mip_thresholds)],
               EvtSel="NONE",
               EvtMax=-1,
               ExtSvc=[EventDataSvc("EventDataSvc")],
               OutputLevel=INFO)
