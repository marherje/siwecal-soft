"""Rectangular far collimator per run and per axis (make_run_sim_dag.py --rect-collimator; collimator.py decide /
correct / tails, collimator_prep.py step2 / step3): the geometry with one axis open, the decision and correction
rules, the node outputs on a fake campaign, and the DAG chain d1 -> p2 -> d2 -> p3 -> chunks."""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from conftest import ROOT

CAMPAIGN = os.path.join(ROOT, "simulation", "campaign")
GEO = os.path.join(ROOT, "simulation", "geometry")
BASE = "SND_compact_beamline.xml"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(CAMPAIGN, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, CAMPAIGN)
    spec.loader.exec_module(mod)
    return mod


collimator = _load("collimator")


@pytest.fixture
def geo(tmp_path):
    shutil.copy(os.path.join(GEO, BASE), tmp_path / BASE)
    return tmp_path


def _jaws(path):
    return {d.get("name"): d for d in ET.parse(path).getroot().iter("detector")
            if d.get("name", "").startswith("H2_FarColl")}


def test_rect_compact_axes(geo):
    both = _jaws(geo / collimator.write_compact(BASE, "g/both.xml", 1.0, 2.0, 25.0, geo=str(geo), ay=20.0))
    assert sorted(both) == ["H2_FarCollB", "H2_FarCollL", "H2_FarCollR", "H2_FarCollT"]
    assert both["H2_FarCollL"].find("position").get("x") == f"{1.0 - 25.0 - collimator.JAW_W / 2:.4f}*mm"
    assert both["H2_FarCollT"].find("position").get("y") == f"{2.0 + 20.0 + collimator.JAW_W / 2:.4f}*mm"
    assert both["H2_FarCollT"].find("box").get("x") == "25.0000*mm"          # top/bottom span the x hole
    only_y = _jaws(geo / collimator.write_compact(BASE, "g/y.xml", 1.0, 2.0, None, geo=str(geo), ay=20.0))
    assert sorted(only_y) == ["H2_FarCollB", "H2_FarCollT"]
    assert only_y["H2_FarCollT"].find("box").get("x") == f"{collimator.OPEN_SPAN:.4f}*mm"
    only_x = _jaws(geo / collimator.write_compact(BASE, "g/x.xml", 1.0, 2.0, 25.0, geo=str(geo), ay=None))
    assert sorted(only_x) == ["H2_FarCollL", "H2_FarCollR"]
    text = (geo / "g/x.xml").read_text()
    assert "half-aperture x 25.00 mm, y open" in text and all(
        "--" not in c for c in re.findall(r"<!--(.*?)-->", text, re.S))
    with pytest.raises(ValueError, match="both axes open"):
        collimator.write_compact(BASE, "g/none.xml", 1.0, 2.0, None, geo=str(geo), ay=None)


def test_tails_gaussian():
    r = np.random.default_rng(1)
    assert collimator.tails(np.full(200000, 100), r.normal(0, 20, 200000)) == pytest.approx(2.44, abs=0.03)
    # shower-like cut: the low-nhit half is ignored
    nhit = np.r_[np.full(1000, 100), np.full(1000, 1)]
    v = np.r_[r.normal(0, 1, 1000), np.full(1000, 1e6)]
    assert collimator.tails(nhit, v) < 3


def test_decide_and_correct():
    a, s, why = collimator.decide(20.0, 1.0, 2.40, 2.38)               # tune at the floor
    assert why == "gun floor" and a == pytest.approx(20.0 / collimator.R0) and s == 20.0
    assert collimator.decide(20.0, 12.0, 2.45, 2.30)[2] == "tails"     # free line tails too wide
    assert collimator.decide(20.0, 1.0, 2.45, 2.30)[2] == "gun floor tails"
    assert collimator.decide(20.0, 12.0, 2.35, 2.30) == (None, 12.0, "open")
    assert collimator.correct(None, 20.0, 15.0) is None
    assert collimator.correct(25.0, 20.0, 19.1) == pytest.approx(25.0 + 0.9 / collimator.SLOPE)
    assert collimator.correct(25.0, 20.0, 10.0) == 25.0 + collimator.STEP_MAX          # clamped step
    assert collimator.correct(12.0, 20.0, 30.0) == 10.0                                # at least w_data / 2


RUN = "TB2026CERN_run_000056"


def _valtree(path, sx, sy, n=4000, seed=0):
    import uproot
    r = np.random.default_rng(seed)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with uproot.recreate(path) as f:
        f["ecal"] = {"nhit_chan": np.full(n, 100, np.int32), "bar_x": r.normal(0, sx, n), "bar_y": r.normal(0, sy, n)}


def test_prep_steps(tmp_path, geo, k4env):
    """step2: x open (tune fine, same tails), y collimated (tune at the floor); step3 corrects y on the pass-2 width."""
    prep = _load("collimator_prep")
    out, c = tmp_path / "camp", tmp_path / "camp" / "collimator"
    for d in ("pass1/params", "pass2/params", "params"):
        (c / d if d != "params" else out / d).mkdir(parents=True, exist_ok=True)
    far = {"mode": "rect", "z": -26000.0, "length": 1000.0, "transmission": 0.4}
    data = {"x": -3.0, "y": -1.0, "wx": 23.0, "wy": 20.0, "n": 100000}
    d1 = {"run": RUN, "E": "10", "data": data, "gun0": {"x": -3.0, "y": -1.0, "sx": 23.0, "sy": 20.0},
          "gun": {"x": -2.5, "y": -0.5, "sx": 12.0, "sy": 1.0}, "dummy": {"wx": 26.0, "wy": 29.0},
          "n_events": 10000, "far_collimator": far}
    json.dump(d1, open(c / "pass1" / "params" / f"{RUN}.json", "w"))
    _valtree(str(tmp_path / "data.root"), 23.0, 20.0, seed=1)
    _valtree(str(c / "pass1" / "dummy" / RUN / f"ecal_dummy_{RUN}.valtree.root"), 26.0, 29.0, seed=2)

    prep.step2(str(out), RUN, str(tmp_path / "data.root"), BASE, "gen/RUN_pass2.xml", geo=str(geo))
    s2 = json.load(open(c / f"{RUN}.step2.json"))
    assert s2["axes"]["x"]["why"] == "open" and s2["axes"]["x"]["a_pass2"] is None
    assert s2["axes"]["y"]["why"].startswith("gun floor")
    p2 = json.load(open(c / "pass2" / "params" / f"{RUN}.data.json"))
    assert p2["gun0"] == {"x": -2.5, "y": -0.5, "sx": 12.0, "sy": 20.0} and "gun" not in p2 and "dummy" not in p2
    assert p2["far_collimator"] == far and p2["n_events"] == 10000
    assert sorted(_jaws(geo / "gen/RUN_pass2.xml")) == ["H2_FarCollB", "H2_FarCollT"]

    d2 = dict(p2, gun={"x": -2.0, "y": -0.2, "sx": 11.0, "sy": 18.0}, dummy={"wx": 22.5, "wy": 18.2})
    json.dump(d2, open(c / "pass2" / "params" / f"{RUN}.json", "w"))
    _valtree(str(c / "pass2" / "dummy" / RUN / f"ecal_dummy_{RUN}.valtree.root"), 22.5, 18.2, seed=3)
    prep.step3(str(out), RUN, BASE, "gen/RUN.xml", geo=str(geo))
    p = json.load(open(out / "params" / f"{RUN}.json"))
    ay = 20.0 / collimator.R0 + (20.0 - 18.2) / collimator.SLOPE
    assert p["far_collimator"]["ax"] is None and p["far_collimator"]["ay"] == pytest.approx(ay)
    assert p["gun"] == {"x": -2.0, "y": -0.2, "sx": 11.0, "sy": 20.0}   # open x: d2 tune; collimated y: pass-2 sigma
    assert p["compact"] == "gen/RUN.xml" and p["n_events"] == 10000
    top = _jaws(geo / "gen/RUN.xml")["H2_FarCollT"]
    assert top.find("position").get("y") == f"{-1.0 + ay + collimator.JAW_W / 2:.4f}*mm"
    # a node rerun after success does nothing
    mtime = os.path.getmtime(out / "params" / f"{RUN}.json")
    prep.step3(str(out), RUN, BASE, "gen/RUN.xml", geo=str(geo))
    assert os.path.getmtime(out / "params" / f"{RUN}.json") == mtime


def test_prep_both_axes_open_keeps_the_line(tmp_path, geo, k4env):
    prep = _load("collimator_prep")
    path = prep.write_geometry(BASE, "gen/open.xml", 0.0, 0.0, None, None, {"z": -26000.0, "length": 1000.0},
                               str(geo))
    assert (geo / path).read_text() == (geo / BASE).read_text()


A, B = "TB2026CERN_run_000022", "TB2026CERN_run_000023"


@pytest.fixture
def runs(tmp_path, k4env):
    import uproot
    r = np.random.default_rng(5)
    for run in (A, B):
        (tmp_path / "reco" / run).mkdir(parents=True)
        with uproot.recreate(str(tmp_path / "reco" / run / f"ecal_{run}.valtree.root")) as f:
            f["ecal"] = {"nhit_chan": np.full(3000, 100, np.int32), "bar_x": r.normal(-8, 24, 3000),
                         "bar_y": r.normal(6, 23, 3000)}
    (tmp_path / "runs.txt").write_text(f"{A} th230 E5 7.5 e-\n{B} th230 E5 20 e-\n")
    yield tmp_path, f"pytest_{os.getpid()}", k4env


def _dag(runs, *extra, check=True):
    tmp, camp, env = runs
    cmd = ["python3", os.path.join(CAMPAIGN, "make_run_sim_dag.py"), "--campaign", camp, "--runs",
           str(tmp / "runs.txt"), "--data-reco", str(tmp / "reco"), "--out", str(tmp / "out"), "--dag-dir",
           str(tmp / "dag"), "--min-events", "0", *extra]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if check:
        assert r.returncode == 0, r.stdout + r.stderr
        return r.stdout, (tmp / "dag" / f"{camp}.dag").read_text()
    return r


def _vars(dag, node):
    return dict(re.findall(r'(\w+)="([^"]*)"', re.search(rf"^VARS {node} (.*)$", dag, re.M).group(1)))


def test_dag_rect_chain(runs):
    tmp, camp, _ = runs
    out, dag = _dag(runs, "--rect-collimator", "7.5")
    o = str(tmp / "out")
    assert "rect collimator" in out and not os.path.exists(os.path.join(GEO, "generated", camp))  # written at run time
    for n in ("d1", "p2", "d2", "p3"):
        assert re.search(rf"^JOB {n}_{A} ", dag, re.M)
    assert not re.search(rf"^JOB d_{A} ", dag, re.M) and re.search(rf"^JOB d_{B} ", dag, re.M)
    for a, b in (("d1", "p2"), ("p2", "d2"), ("d2", "p3")):
        assert f"PARENT {a}_{A} CHILD {b}_{A}" in dag
    assert re.search(rf"^PARENT p3_{A} CHILD c_{A}_000", dag, re.M)
    d1, d2 = _vars(dag, f"d1_{A}"), _vars(dag, f"d2_{A}")
    assert d1["CAMP"] == f"{o}/collimator/pass1" and d1["COMPACT"] == BASE and d1["NDUMMY"] == "6000"
    assert d2["CAMP"] == f"{o}/collimator/pass2" and d2["COMPACT"] == f"generated/{camp}/{A}_pass2.xml"
    assert _vars(dag, f"p2_{A}")["ARGS"] == (f"step2 {o} {A} {tmp}/reco/{A}/ecal_{A}.valtree.root {BASE} "
                                            f"generated/{camp}/{A}_pass2.xml")
    assert _vars(dag, f"p3_{A}")["ARGS"] == f"step3 {o} {A} {BASE} generated/{camp}/{A}.xml"
    assert _vars(dag, f"c_{A}_000")["COMPACT"] == f"generated/{camp}/{A}.xml"
    assert _vars(dag, f"d_{B}")["CAMP"] == o and _vars(dag, f"c_{B}_000")["COMPACT"] == BASE
    pa = json.load(open(tmp / "dag" / "params" / f"{A}.data.json"))
    assert pa["far_collimator"]["mode"] == "rect" and (pa["n_events"], pa["dummy_events"]) == (8000, 6000)
    prep_sub = (tmp / "dag" / "prep.sub").read_text()
    assert "run_collimator_prep.sh" in prep_sub and "should_transfer_files   = NO" in prep_sub
    assert "$(CAMP)" in (tmp / "dag" / "dummy.sub").read_text()


def test_prepare_output_copies_the_pass1_input(runs, tmp_path):
    tmp, camp, _ = runs
    _dag(runs, "--rect-collimator", "7.5")
    mk = _load("make_run_sim_dag")
    mk.prepare_output(str(tmp / "out"), str(tmp / "dag"), [A, B], [A])
    assert (tmp / "out" / "collimator" / "pass1" / "params" / f"{A}.data.json").exists()
    assert (tmp / "out" / "collimator" / "pass2" / "dummy").is_dir()
    assert not (tmp / "out" / "collimator" / "pass1" / "params" / f"{B}.data.json").exists()
    assert (tmp / "out" / "params" / f"{B}.data.json").exists()


def test_no_summary(runs):
    assert "JOB summary" in _dag(runs)[1]
    assert "JOB summary" not in _dag(runs, "--no-summary")[1]


def test_rect_and_square_on_one_energy_refused(runs):
    r = _dag(runs, "--rect-collimator", "7.5", "--far-collimator", "7.5=25", check=False)
    assert r.returncode != 0 and "both" in r.stderr


def test_dd4hep_builds_one_axis_compact(k4env):
    """A geometry with only the top/bottom jaws loads in DD4hep from its real place (includes resolved)."""
    rel = f"generated/pytest_rect_{os.getpid()}/RUN.xml"
    try:
        collimator.write_compact(BASE, rel, -8.0, 6.5, None, ay=21.0)
        code = ("import dd4hep, sys; d = dd4hep.Detector.getInstance(); d.fromXML(sys.argv[1]); "
                "print(sorted(str(n.first) for n in d.detectors() if str(n.first).startswith('H2_FarColl')))")
        r = subprocess.run(["python3", "-c", code, os.path.join(GEO, rel)], env=k4env, capture_output=True,
                           text=True, timeout=300)
        assert r.returncode == 0, r.stderr[-2000:]
        assert "['H2_FarCollB', 'H2_FarCollT']" in r.stdout
    finally:
        shutil.rmtree(os.path.join(GEO, os.path.dirname(rel)), ignore_errors=True)
