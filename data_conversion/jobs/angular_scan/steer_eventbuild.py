#
# Gaudi/k4FWCore steering of the angular scan, event-building stage, for the run in ANGSCAN_RUN:
# siwecaldecoded chunks -> event-built `ecal` tree, with the FULL calibration of the run's threshold (runs.yml:
# `threshold`, th210, or the run's entry in `thresholds`: the 45 deg muon runs at th220/th230) from the official
# tables (calib_dir()/MuonCalib on EOS): pedestals/th<N>/, mips/th<N>/ and the LG->HG anchor anchor/th<N>/.
#
# Every table is the threshold's own (per-threshold calibration; nothing is borrowed from another threshold). The
# anchor line (k, c) and the pedestal-subtracted switch are read from anchor/th<N>/gain_anchor_th<N>.txt.
#
# One steering for every run of runs.yml (the 55 per-run copies of siwecal-tb2026 differed only in the run number);
# from already-converted chunks (no CONVERT step -- see data_conversion/jobs/condor/generate_convert_eudaq_dag.py).
#
#   source init_siwecalsoft.sh
#   ANGSCAN_RUN=179 k4run data_conversion/jobs/angular_scan/steer_eventbuild.py
#
import glob
import os

from Gaudi.Configuration import INFO
from Configurables import EventDataSvc
from Configurables import EcalEventBuilder
from k4FWCore import ApplicationMgr

import yaml
from siwecal_common import paths

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCAN = yaml.safe_load(open(os.path.join(_HERE, "runs.yml")))
if not os.environ.get("ANGSCAN_RUN"):
    raise SystemExit("Set ANGSCAN_RUN to a run of runs.yml (number or TB2026CERN_eudaq_run_000NNN)")
_NUM = int(os.environ["ANGSCAN_RUN"].rsplit("_", 1)[-1])
if _NUM not in _SCAN["runs"]:
    raise SystemExit(f"run {_NUM} is not in the angular scan (runs.yml)")
_RUN = f"TB2026CERN_eudaq_run_{_NUM:06d}"
_TH = str(_SCAN.get("thresholds", {}).get(_NUM, _SCAN["threshold"]))
_CALIB = paths.muon_calib_dir()
_MAPPINGS = paths.mappings_dir()

_CONVERTED = paths.converted_dir()
_INPUT_GLOB = os.path.join(_CONVERTED, _RUN, "chunks", "chunk_*.root")
# Event-builder output goes to <run>/events/, alongside the run's <run>/chunks/,
# NOT to the shared Reconstruction/ area. Override with EVBLD_OUTPUT.
_EVENTS_DIR = os.path.join(_CONVERTED, _RUN, "events")
_OUTPUT = os.environ.get("EVBLD_OUTPUT", os.path.join(_EVENTS_DIR, f"ecal_{_RUN}.root"))
os.makedirs(os.path.dirname(_OUTPUT), exist_ok=True)


def _latest(pattern):
    hits = sorted(glob.glob(pattern))
    if not hits:
        raise SystemExit(f"calibration file not found: {pattern}")
    return hits[-1]


def _anchor(path):
    """Read k, c, switch from an anchor/thN/gain_anchor_thN.txt file."""
    k, c, switch = 0.0962, 1.45, 1500
    for line in open(path):
        if line.startswith("#") or not line.strip():
            continue
        tok = line.split()
        if tok[0] == "k":
            k = float(tok[1])
        elif tok[0] == "c":
            c = float(tok[1])
        elif tok[0] == "switch":
            switch = int(float(tok[1]))
    return k, c, switch


ped_hg = _latest(os.path.join(_CALIB, "pedestals", f"th{_TH}", "Pedestal_*_highgain.txt"))
mip_hg = _latest(os.path.join(_CALIB, "mips", f"th{_TH}", "MIP_pedestalsubmode1_*_highgain.txt"))
ped_lg = _latest(os.path.join(_CALIB, "pedestals", f"th{_TH}", "Pedestal_*_lowgain.txt"))
mip_lg = _latest(os.path.join(_CALIB, "mips", f"th{_TH}", "MIP_pedestalsubmode1_*_lowgain.txt"))
k, c, switch = _anchor(os.path.join(_CALIB, "anchor", f"th{_TH}", f"gain_anchor_th{_TH}.txt"))

builder = EcalEventBuilder(
    "EcalEventBuilder",
    InputFiles=sorted(glob.glob(_INPUT_GLOB)),
    TreeName="siwecaldecoded",
    OutputFile=_OUTPUT,
    PedestalFile=ped_hg,
    MipFile=mip_hg,
    PedestalFileLowGain=ped_lg,
    MipFileLowGain=mip_lg,
    AdcSaturationThreshold=switch,   # on (adc_high - ped_hg)
    GainRatio=k,
    GainIntercept=c,
    # Geometry: pad (x,y) mapping + per-slab z. Without these the hits have no
    # position and the event display comes up empty. Slab 12 is the COB and uses
    # its own pad map (fev11), every other slab the default fev10.
    PadMapDefaultFile=os.path.join(_MAPPINGS, "fev10_rotate_chip_channel_x_y_mapping.txt"),
    PadMapSlabOverrides=[f"12:{os.path.join(_MAPPINGS, 'fev11_cob_good_rotate_chip_channel_x_y_mapping.txt')}"],
    SlabZFile=os.path.join(_MAPPINGS, "slab_z_positions.yml"),
)

ApplicationMgr(TopAlg=[builder],
               EvtSel="NONE",
               EvtMax=1,
               ExtSvc=[EventDataSvc("EventDataSvc")],
               OutputLevel=INFO)
