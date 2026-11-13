"""Every Gaudi steering file of the repo configures (k4run --dry-run) from a foreign working directory, with only
the inputs a driver would pass: imports, Configurables, siwecal_common.paths and the data files they resolve.
Without inputs each one stops with its own explicit message (never a traceback)."""
import glob
import os
import subprocess

import pytest

from conftest import ROOT, TB

RUN = "TB2026CERN_eudaq_run_000293"   # th210, 7.5 GeV electrons: a small official run


def _dry(path, env, cwd):
    r = subprocess.run(["k4run", "--dry-run", path], env=env, cwd=cwd, capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr


def _cases(tmp):
    mc = os.path.join(TB, "Calib", "MuonCalib")
    chunk = os.path.join(TB, "Data", "rundata_converted_gaudi", RUN, "chunks", "chunk_0000.root")
    ecal = os.path.join(TB, "Reconstruction", RUN, f"ecal_{RUN}.root")
    pid = os.path.join(TB, "Reconstruction", RUN, f"ecal_{RUN}.edm4hep.root")
    ped = os.path.join(mc, "pedestals", "th210", "Pedestal_TB2026CERN_run_000th210_highgain.txt")
    mip = sorted(glob.glob(os.path.join(mc, "mips", "th210", "*highgain*.txt")))[0]
    o = str(tmp)
    return {
        "data_conversion/options/run_raw2root.py": dict(RAW_FILES=chunk, RAW2ROOT_OUT=f"{o}/r.root"),
        "data_conversion/options/run_lcio_decode.py": dict(LCIO_IN=f"{o}/x.slcio", LCIO_OUT=f"{o}/l.root"),
        "data_conversion/options/run_event_builder.py": dict(EVBLD_INPUT=chunk, EVBLD_PEDESTAL_FILE=ped,
                                                             EVBLD_MIP_FILE=mip, EVBLD_OUTPUT=f"{o}/e.root"),
        "data_conversion/options/run_pedestal_mip.py": dict(CALIB_INPUT_FILES=chunk),
        "data_conversion/options/run_gain_anchor.py": dict(ANCHOR_INPUT_FILES=chunk, ANCHOR_PEDESTAL_FILE=ped,
                                                           ANCHOR_PEDESTAL_FILE_LOWGAIN=ped.replace("highgain", "lowgain"),
                                                           ANCHOR_OUTPUT_FILE=f"{o}/a.txt"),
        "reconstruction/pid/options/run_pid.py": dict(ECAL_FILE=ecal, ECAL_PID_OUT=f"{o}/p.edm4hep.root"),
        "reconstruction/pid/options/edm4hep_to_valtree.py": dict(PID_FILE=pid, ECAL_VALTREE_OUT=f"{o}/v.root"),
        "reconstruction/tracking/options/run_tracking.py": dict(TRACKING_INPUT_FILE=pid,
                                                                TRACKING_OUTPUT_FILE=f"{o}/t.root"),
        "simulation/jobs/job3_digitize.py": dict(CALIB_THRESHOLD="th210", DIGI_MODE="real", INPUT_FILE=pid,
                                                 BEAM_Z_MM="-65500"),
        "simulation/jobs/job4_tracking.py": dict(),
        "data_conversion/options/run_occupancy_sag.py": dict(SAG_MODE="Fill", SAG_INPUT_FILES=chunk,
                                                             SAG_OUTPUT=f"{o}/s.txt"),
        "data_conversion/options/run_trigger_turnon.py": dict(TURNON_MODE="Fill", TURNON_SET="th210",
                                                              TURNON_INPUT_FILES=chunk, TURNON_OUTPUT=f"{o}/t.txt"),
        # outputs always redirected to tmp: the defaults write next to the converted chunks on EOS
        "data_conversion/jobs/angular_scan/steer_eventbuild.py": dict(ANGSCAN_RUN="179", EVBLD_OUTPUT=f"{o}/as.root"),
    }


def test_every_steering_file_is_covered():
    found = {os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "*", "options", "*.py")) +
             glob.glob(os.path.join(ROOT, "*", "*", "options", "*.py")) +
             glob.glob(os.path.join(ROOT, "simulation", "jobs", "job*.py")) +
             glob.glob(os.path.join(ROOT, "data_conversion", "jobs", "angular_scan", "steer_*.py"))}
    assert found == set(_cases("/x").keys()) if os.path.isdir(TB) else True, found ^ set(_cases("/x").keys())


@pytest.mark.parametrize("rel", sorted(_cases("/x").keys()) if os.path.isdir(TB) else [])
def test_steering_configures(rel, k4env, eos, tmp_path):
    env = dict(k4env, **_cases(tmp_path)[rel])
    rc, out = _dry(os.path.join(ROOT, rel), env, tmp_path)
    assert rc == 0, out[-3000:]
    assert "Traceback" not in out, out[-3000:]
    if rel == "simulation/jobs/job3_digitize.py":
        # the H2-like line: beam born at -65.5 m, windows shifted by the extra 62.85 m of flight
        assert "RealDigitizer.TimeOffsetNs = 209.65 ns" in out, out[-2000:]
        assert "occupancy baseline sag: measured map" in out and "occupancy_sag_th210.txt" in out


def _pid_variants(tmp):
    """run_pid.py with each optional block the drivers switch on (run_pid_batch.py, run_pid_sim.sh)."""
    ecal = os.path.join(TB, "Reconstruction", RUN, f"ecal_{RUN}.root")
    pid = os.path.join(TB, "Reconstruction", RUN, f"ecal_{RUN}.edm4hep.root")
    o = str(tmp)
    base = dict(ECAL_FILE=ecal, ECAL_PID_OUT=f"{o}/p.edm4hep.root", ECAL_HIT_MIP_CUT="0.5", ECAL_MIP_THRESHOLDS="")
    return {
        "select": (dict(base, PID_SELECT="1", PID_CUTS="moliere:30:,weighte::4000", PID_IS_SHOWER="1"),
                   ["EcalEventSelection"], ["EcalValTreeWriter"]),
        "select_keep_empty": (dict(base, PID_SELECT="1", PID_REQUIRE_HITS="0"), ["EcalEventSelection"], []),
        "valtree": (dict(base, PID_SELECT="1", ECAL_VALTREE_OUT=f"{o}/p.valtree.root"),
                    ["EcalEventSelection", "EcalValTreeWriter"], []),
        "valtree_only": (dict(base, ECAL_PID_OUT="", ECAL_VALTREE_OUT=f"{o}/p.valtree.root"),
                         ["EcalValTreeWriter"], ["EcalEventSelection"]),
        "merge": (dict(base, PID_MERGE_FILE=pid), ["ACTSTracks"], ["EcalEventSelection"]),
    }


@pytest.mark.parametrize("variant", ["select", "select_keep_empty", "valtree", "valtree_only", "merge"])
def test_run_pid_variants_configure(variant, k4env, eos, tmp_path):
    env, present, absent = _pid_variants(tmp_path)[variant]
    rc, out = _dry(os.path.join(ROOT, "reconstruction/pid/options/run_pid.py"), dict(k4env, **env), tmp_path)
    assert rc == 0 and "Traceback" not in out, out[-3000:]
    for word in present:
        assert word in out, (word, out[-3000:])
    for word in absent:
        assert word not in out, (word, out[-3000:])


def test_edm4hep_to_valtree_reads_mip_blocks(k4env, eos, tmp_path):
    """Reconstruction PID files are validation mode: their metadata names the mip05_/mip1_ blocks."""
    env = dict(k4env, **_cases(tmp_path)["reconstruction/pid/options/edm4hep_to_valtree.py"])
    rc, out = _dry(os.path.join(ROOT, "reconstruction/pid/options/edm4hep_to_valtree.py"), env, tmp_path)
    assert rc == 0 and "MipThresholds [0.5, 1.0]" in out, out[-3000:]


@pytest.mark.parametrize("rel", ["reconstruction/pid/options/run_pid.py", "data_conversion/options/run_event_builder.py",
                                 "simulation/jobs/job3_digitize.py",
                                 "reconstruction/pid/options/edm4hep_to_valtree.py"])
def test_steering_without_inputs_says_why(rel, k4env, tmp_path):
    env = {k: v for k, v in k4env.items() if not k.startswith(("ECAL_", "EVBLD_", "INPUT_FILE", "CALIB_", "DIGI_", "PID_"))}
    rc, out = _dry(os.path.join(ROOT, rel), env, tmp_path)
    assert rc != 0 and "Traceback" not in out, out[-2000:]
