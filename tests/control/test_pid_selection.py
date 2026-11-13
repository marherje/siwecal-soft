"""The PID stage's event selection (EcalEventSelection + EcalValTreeWriter, driven by run_pid_batch.py) on the first
1500 events of a small official run:
  * with cuts, the EDM4hep and the valtree hold the same events, and every one passes the cuts;
  * they are exactly the events of the uncut job that CutSet.mask (the Python definition) accepts;
  * --keep-empty keeps every input event, row-aligned with the ecal tree.
Opt-in (runs k4run three times, ~1-2 min):  SIWECAL_SLOW_TESTS=1 pytest tests/control/test_pid_selection.py"""
import os
import subprocess

import numpy as np
import pytest

from conftest import ROOT, TB

RUN = "TB2026CERN_eudaq_run_000293"   # th210, 7.5 GeV electrons
N = 1500
CUT_ARGS = ["--moliere-min", "30", "--weighte-max", "4000", "--is-shower"]
pytestmark = pytest.mark.skipif(os.environ.get("SIWECAL_SLOW_TESTS") != "1", reason="set SIWECAL_SLOW_TESTS=1")


def _pid(env, ecal, outdir, *extra):
    cmd = ["python3", os.path.join(ROOT, "reconstruction/jobs/run_pid_batch.py"), "--file", ecal, "--outdir", outdir,
           "--format", "both", *extra]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=1800)
    log = r.stdout + r.stderr
    open(os.path.join(outdir + ".log"), "w").write(log)
    assert r.returncode == 0, log[-3000:]
    return log


@pytest.fixture(scope="module")
def jobs(tmp_path_factory, k4env, eos):
    w = tmp_path_factory.mktemp("pidsel")
    ecal = str(w / "ecal_small.root")
    src = os.path.join(TB, "Reconstruction", RUN, f"ecal_{RUN}.root")
    # first N entries of the official ecal tree (ROOT copy keeps every branch and type)
    code = ("import ROOT,sys; f=ROOT.TFile.Open(sys.argv[1]); t=f.Get('ecal'); o=ROOT.TFile(sys.argv[2],'RECREATE'); "
            "c=t.CopyTree('','',int(sys.argv[3])); n=c.GetEntries(); c.Write(); o.Close(); f.Close(); print(n)")
    r = subprocess.run(["python3", "-c", code, src, ecal, str(N)], env=k4env, capture_output=True, text=True)
    assert r.returncode == 0 and int(r.stdout.split()[-1]) == N, r.stdout + r.stderr
    out = {"ecal": ecal}
    for tag, extra in (("cut", CUT_ARGS), ("nocut", []), ("keep", ["--keep-empty"])):
        d = str(w / tag)
        out[tag] = (d, _pid(k4env, ecal, d, *extra))
    return out


def _trees(d):
    import uproot
    return (uproot.open(os.path.join(d, "ecal_small.valtree.root"))["ecal"],
            uproot.open(os.path.join(d, "ecal_small.edm4hep.root"))["events"])


def test_edm4hep_and_valtree_hold_the_same_events(jobs):
    for tag in ("cut", "nocut", "keep"):
        v, e = _trees(jobs[tag][0])
        assert v.num_entries == e.num_entries > 0, tag
        ev_v = v["event"].array(library="np")
        ev_e = np.array([x[0] for x in e["EventHeader/EventHeader.eventNumber"].array(library="np")])
        np.testing.assert_array_equal(ev_v, ev_e, err_msg=tag)


def test_every_selected_event_passes_the_cuts(jobs):
    v, _ = _trees(jobs["cut"][0])
    a = v.arrays(["nhit_chan", "energy", "moliere", "weighte", "is_shower"], library="np")
    assert (a["nhit_chan"] > 0).all() and (a["energy"] > 0).all()
    assert (a["moliere"] >= 30).all() and (a["weighte"] <= 4000).all() and a["is_shower"].all()
    assert "EcalEventSelection" in jobs["cut"][1] and "events selected" in jobs["cut"][1]


def test_selection_matches_the_python_cutset(jobs):
    from siwecal_validation.selection import CutSet
    v_all, _ = _trees(jobs["nocut"][0])
    v_cut, _ = _trees(jobs["cut"][0])

    class _Data:   # CutSet.mask reads attributes of an EventData; the valtree has them under the same names
        def __init__(self, arrays):
            self.__dict__.update(arrays)
            self._n = len(arrays["event"])

        def __len__(self):
            return self._n

    from siwecal_validation.selection import _CUT_SPEC
    names = sorted({attr for *_, attr in _CUT_SPEC} | {"event", "is_shower"})
    data = _Data(v_all.arrays(names, library="np"))
    keep = CutSet(moliere_min=30, weighte_max=4000, is_shower=True).mask(data)
    assert 0 < keep.sum() < len(data)
    np.testing.assert_array_equal(data.event[keep], v_cut["event"].array(library="np"))


def test_keep_empty_keeps_every_input_event(jobs):
    import uproot
    v, _ = _trees(jobs["keep"][0])
    ecal = uproot.open(jobs["ecal"])["ecal"]
    assert v.num_entries == ecal.num_entries == N
    np.testing.assert_array_equal(v["event"].array(library="np"), ecal["event"].array(library="np"))
