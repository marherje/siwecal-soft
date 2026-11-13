#
# Gaudi/k4FWCore steering para TB2026CERN_run_000013 — modo físico.
# Hit MIP cut = 0.5; sin bloques de variantes mip05_/mip1_.
#
# Uso (desde la raíz del repo):
#   source init_siwecalsoft.sh
#   k4run data_conversion/jobs/runs/run000013/steer_run000013.py
#
import ROOT
from Gaudi.Configuration import INFO
from Configurables import EventDataSvc
from Configurables import EcalToEDM4hep, EcalShowerVariables
from k4FWCore import ApplicationMgr, IOSvc

_RUN   = "TB2026CERN_run_000013"
# Event-builder output with real calibration (MuonCalib_it2, th220)
# the input lived in a personal EOS area: give its location explicitly
import os as _os  # noqa: E402
_INPUT = _os.environ.get("RUN13_REALVALUES_INPUT") or SystemExit("set RUN13_REALVALUES_INPUT to ecal_<run>_realvalues.root")
if isinstance(_INPUT, SystemExit):
    raise _INPUT
# EDM4hep output goes to <run>/events/, alongside the run's chunks -- NOT the
# shared Reconstruction/ area. Override with EDM4HEP_OUTPUT.
import os  # noqa: E402
_EVENTS = os.path.join(os.environ.get(
    "EVBLD_CONVERTED_DIR",
    "/eos/experiment/drdcalo/siw-ecal/TB2026-06/Data/rundata_converted_gaudi"), _RUN, "events")
os.makedirs(_EVENTS, exist_ok=True)
_OUT   = os.environ.get("EDM4HEP_OUTPUT", os.path.join(_EVENTS, f"ecal_{_RUN}.edm4hep.root"))

_f = ROOT.TFile.Open(_INPUT)
n_events = int(_f.Get("ecal").GetEntries())
_f.Close()

svc = IOSvc("IOSvc")
svc.Output = _OUT

source = EcalToEDM4hep("EcalToEDM4hep",
                        InputFile=_INPUT,
                        TreeName="ecal",
                        HitMipCut=0.5)      # <0 para deshabilitar el corte de hit

pid = EcalShowerVariables("EcalShowerVariables",
                          InputCaloHits=["ECalHits"],
                          OutputClusters=["ECalPid"],
                          MipThresholds=[])  # [0.5, 1.0] para modo validación (slider)

ApplicationMgr(TopAlg=[source, pid],
               EvtSel="NONE",
               EvtMax=n_events,
               ExtSvc=[EventDataSvc("EventDataSvc")],
               OutputLevel=INFO)
