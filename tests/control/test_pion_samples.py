"""Pion samples (docs/sim/pion_samples.md): the data runs to reproduce and the E2 background points."""
import importlib.util
import os
import re
import subprocess

from conftest import ROOT

CAMPAIGN = os.path.join(ROOT, "simulation", "campaign")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(CAMPAIGN, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_runs_pion():
    runs = _load("make_run_list").read_runs(os.path.join(CAMPAIGN, "runs_pion.txt"))
    assert [(r["run"][-3:], float(r["E"])) for r in runs] == [("161", 10), ("162", 10), ("164", 20), ("165", 30)]
    assert all((r["set"], r["particle"]) == ("th210", "pi+") for r in runs)


def test_pion_points():
    read = _load("make_sim_dag").read_points
    points = read(os.path.join(CAMPAIGN, "pion_points.txt"))
    ref = {p["name"]: p for p in read(os.path.join(CAMPAIGN, "bkg_points.txt"))}["th230_E2_pi_e5-100"]
    assert [p["E"] for p in points] == ["10", "20", "30", "40", "50"]
    for p in points:
        assert p["name"] == f"th230_E2_pi_e{p['E']}" and p["particle"] == "pi+"
        assert all(p[k] == ref[k] for k in ("set", "label", "x", "y", "sx", "sy"))


def test_electron_points():
    points = _load("make_sim_dag").read_points(os.path.join(CAMPAIGN, "electron_points_E2.txt"))
    assert [p["E"] for p in points] == ["52", "74", "99"]
    assert all((p["set"], p["label"], p["particle"]) == ("th230", "E2", "e-") for p in points)


def _launch(tmp_path, *args):
    return subprocess.run(["bash", os.path.join(CAMPAIGN, "launch_pions.sh"), *args], capture_output=True, text=True,
                          env=dict(os.environ, DATA_RECO=str(tmp_path)), timeout=300)


def test_launcher_refusals(tmp_path):
    assert _launch(tmp_path).returncode == 1 and _launch(tmp_path, "all").returncode == 1
    for mode, text in (("valtree", "not reconstructed"), ("runs", "no data valtree")):
        r = _launch(tmp_path, mode)
        assert r.returncode == 1 and text in r.stderr and "000165" in r.stderr
    run = "TB2026CERN_eudaq_run_000165"
    (tmp_path / run).mkdir()
    (tmp_path / run / f"ecal_{run}.root").write_text("x")
    r = _launch(tmp_path, "reco")
    assert r.returncode == 1 and "exists, not redone" in r.stderr


def test_launcher_e2(tmp_path):
    r = _launch(tmp_path, "e2", "--out", str(tmp_path / "out"), "--dag-dir", str(tmp_path / "dag"), "--nevents", "20",
                "--chunk-events", "10")
    assert r.returncode == 0, r.stderr
    dag = (tmp_path / "dag" / "pion_E2_v1.dag").read_text()
    assert dag.count("JOB c_") == 10 and dag.count("JOB g_") == 5 and dag.count('PARTICLE="pi+"') == 10
    assert len(set(re.findall(r'SEED="(\d+)"', dag))) == 10
