#
# Gaudi/k4FWCore steering of the angular scan, VALIDATION / EDM4hep stage, for the run in ANGSCAN_RUN: reads the
# event-built `ecal` tree of steer_eventbuild.py and writes the EDM4hep + PID output next to it, in <run>/events/ --
# NOT in the shared Reconstruction/ area.
#
#   source init_siwecalsoft.sh
#   ANGSCAN_RUN=179 k4run data_conversion/jobs/angular_scan/validate.py
#
import os

import ROOT
from Gaudi.Configuration import INFO
from Configurables import EventDataSvc
from Configurables import EcalToEDM4hep, EcalShowerVariables
from k4FWCore import ApplicationMgr, IOSvc

from siwecal_common import paths

if not os.environ.get("ANGSCAN_RUN"):
    raise SystemExit("Set ANGSCAN_RUN to a run of runs.yml (number or TB2026CERN_eudaq_run_000NNN)")
_RUN = f"TB2026CERN_eudaq_run_{int(os.environ['ANGSCAN_RUN'].rsplit('_', 1)[-1]):06d}"
_CONVERTED = paths.converted_dir()
_EVENTS = os.path.join(_CONVERTED, _RUN, "events")
_INPUT = os.environ.get("VALIDATE_INPUT", os.path.join(_EVENTS, f"ecal_{_RUN}.root"))
_OUTPUT = os.environ.get("VALIDATE_OUTPUT", os.path.join(_EVENTS, f"ecal_{_RUN}.edm4hep.root"))
os.makedirs(os.path.dirname(_OUTPUT), exist_ok=True)

_f = ROOT.TFile.Open(_INPUT)
if not _f or _f.IsZombie():
    raise SystemExit(f"input not found (run steer_eventbuild.py for this run first): {_INPUT}")
n_events = int(_f.Get("ecal").GetEntries())
_f.Close()

svc = IOSvc("IOSvc")
svc.Output = _OUTPUT

source = EcalToEDM4hep("EcalToEDM4hep",
                        InputFile=_INPUT,
                        TreeName="ecal",
                        HitMipCut=0.5)            # <0 to disable the per-hit MIP cut

pid = EcalShowerVariables("EcalShowerVariables",
                          InputCaloHits=["ECalHits"],
                          OutputClusters=["ECalPid"],
                          MipThresholds=[0.5, 1.0])  # validation mode: mip05_/mip1_ shape blocks

ApplicationMgr(TopAlg=[source, pid],
               EvtSel="NONE",
               EvtMax=n_events,
               ExtSvc=[EventDataSvc("EventDataSvc")],
               OutputLevel=INFO)
