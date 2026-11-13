"""End-to-end physics smoke test of the simulation chain as a campaign runs it, on 40 events (a few minutes):
  ddsim through the H2-like line (simulation/run/ddsim_beam_chunk.sh: beam at -65.5 m, 2 % energy spread)
  -> job3_digitize.py, real chain, with and without the measured occupancy sag
  -> the PID stage with its valtree (reconstruction/jobs/run_pid_batch.py --format both; pid_to_valtree.py must
  rewrite the same valtree from the EDM4hep)
Opt-in:  SIWECAL_SLOW_TESTS=1 pytest tests/control/test_physics_smoke.py"""
import os
import subprocess

import pytest

from conftest import ROOT

N = 40
pytestmark = pytest.mark.skipif(os.environ.get("SIWECAL_SLOW_TESTS") != "1", reason="set SIWECAL_SLOW_TESTS=1")


def _run(cmd, env, cwd, what):
    r = subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True, timeout=3600)
    log = r.stdout + r.stderr
    open(os.path.join(cwd, f"{what}.log"), "w").write(log)
    return r.returncode, log


@pytest.fixture(scope="module")
def chain(tmp_path_factory, k4env, eos):
    w = tmp_path_factory.mktemp("smoke")
    env = dict(k4env, COMPACT_FILE="SND_compact_beamline.xml", BEAM_Z_MM="-65500", PHYSICS_LIST="QGSP_BERT_EMZ",
               KEEP_LOCAL="1")
    rc, log = _run(["bash", os.path.join(ROOT, "simulation/run/ddsim_beam_chunk.sh"), ROOT, str(N), "e-", "20",
                    "26", "-52", "17.6", "13.0", "0.02", "4242", "-"], env, w, "ddsim")
    assert os.path.isfile(w / "sim.edm4hep.root"), log[-3000:]
    out = {}
    for tag, sag in (("sag", None), ("nosag", "")):
        d = w / tag
        d.mkdir()
        e = dict(k4env, CALIB_THRESHOLD="th210", DIGI_MODE="real", RECO_TABLE_THRESHOLD="th210",
                 INPUT_FILE=str(w / "sim.edm4hep.root"), ECAL_TREE_OUTPUT="ecal.root", BEAM_Z_MM="-65500")
        if sag is not None:
            e["OCCUPANCY_SAG_TABLE"] = sag
        rc, log = _run(["k4run", os.path.join(ROOT, "simulation/jobs/job3_digitize.py")], e, d, "job3")
        assert os.path.isfile(d / "ecal.root") and f"wrote {N} events" in log, log[-3000:]
        out[tag] = (d, log)
    d = out["sag"][0]
    rc, log = _run(["python3", os.path.join(ROOT, "reconstruction/jobs/run_pid_batch.py"), "--file", str(d / "ecal.root"),
                    "--outdir", str(d / "pid"), "--format", "both", "--hit-mip-cut", "0.5"], k4env, d, "pid")
    assert rc == 0, log[-3000:]
    pid = [f for f in os.listdir(d / "pid") if f.endswith(".edm4hep.root")]
    out["valtree"] = d / "pid" / pid[0].replace(".edm4hep.root", ".valtree.root")
    # the same valtree, written afterwards from the EDM4hep by its own Gaudi job
    rc, log = _run(["python3", os.path.join(ROOT, "reconstruction/jobs/pid_to_valtree.py"), "--outdir", str(d),
                    str(d / "pid" / pid[0])], k4env, d, "valtree")
    assert rc == 0, log[-3000:]
    out["valtree_from_edm4hep"] = d / os.path.basename(out["valtree"])
    out["pid"] = d / "pid" / pid[0]
    return out


def test_valtree_from_edm4hep_matches_the_pid_job(chain):
    import numpy as np
    import uproot
    a = uproot.open(str(chain["valtree"]))["ecal"]
    b = uproot.open(str(chain["valtree_from_edm4hep"]))["ecal"]
    assert a.num_entries == b.num_entries == uproot.open(str(chain["pid"]))["events"].num_entries > 0
    assert set(a.keys()) == set(b.keys())
    for k in a.keys():
        x, y = a[k].array(library="np"), b[k].array(library="np")
        if x.dtype == object:
            x, y = np.concatenate(list(x) or [[]]), np.concatenate(list(y) or [[]])
        np.testing.assert_array_equal(x, y, err_msg=k)


def test_h2_beam_produces_triggered_hits(chain):
    import uproot
    log = chain["sag"][1]
    assert "TimeOffsetNs = 209.65 ns" in log
    t = uproot.open(str(chain["sag"][0] / "ecal.root"))["ecal"]
    nhit = t["nhit_chan"].array(library="np")
    assert t.num_entries == N and (nhit > 50).mean() > 0.9, nhit   # 20 GeV electrons shower in every event


def test_occupancy_sag_changes_the_digitisation(chain):
    import numpy as np
    import uproot
    assert "occupancy baseline sag ON" in chain["sag"][1] and "occupancy baseline sag ON" not in chain["nosag"][1]
    a = uproot.open(str(chain["sag"][0] / "ecal.root"))["ecal"]["sum_hg"].array(library="np")
    b = uproot.open(str(chain["nosag"][0] / "ecal.root"))["ecal"]["sum_hg"].array(library="np")
    assert np.mean(a) < np.mean(b), (np.mean(a), np.mean(b))      # the baseline sags down under load


def test_valtree_has_what_the_final_plots_read(chain):
    import uproot
    need = ["nhit_chan", "sum_hg", "sum_energy", "weighte", "e_over_nhit", "moliere", "transverse_rms", "bar_r",
            "zbary", "shower_start", "shower_max", "shower_length", "n_layers_hit", "mip_likeness",
            "fractal_dimension", "barxy_min_border_distance", "bar_x", "bar_y"]
    keys = set(uproot.open(str(chain["valtree"]))["ecal"].keys())
    assert not set(need) - keys, set(need) - keys


def test_ecal_tree_is_self_consistent(chain):
    """The ecal tree of EcalTreeWriter (job3 ECAL_TREE_OUTPUT; the Python converter it replaced is retired): counters
    and sums agree with the hit arrays, the cell indices are inside the detector."""
    import awkward as ak
    import numpy as np
    import uproot
    t = uproot.open(str(chain["sag"][0] / "ecal.root"))["ecal"]
    a = t.arrays(["nhit_chan", "nhit_slab", "sum_hg", "sum_energy", "hit_slab", "hit_chip", "hit_chan", "hit_hg",
                  "hit_energy"])
    assert np.array_equal(ak.to_numpy(a["nhit_chan"]), ak.to_numpy(ak.num(a["hit_slab"])))
    assert np.allclose(ak.to_numpy(a["sum_hg"]), ak.to_numpy(ak.sum(a["hit_hg"], axis=1)), rtol=1e-5)
    assert np.allclose(ak.to_numpy(a["sum_energy"]), ak.to_numpy(ak.sum(a["hit_energy"], axis=1)), rtol=1e-5)
    nslab = [len(set(x)) for x in ak.to_list(a["hit_slab"])]
    assert list(ak.to_numpy(a["nhit_slab"])) == nslab
    for k, hi in (("hit_slab", 15), ("hit_chip", 16), ("hit_chan", 64)):
        v = ak.to_numpy(ak.flatten(a[k]))
        assert v.min() >= 0 and v.max() < hi, k
