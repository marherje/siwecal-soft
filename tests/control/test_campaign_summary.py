"""Summary of a run-by-run simulation campaign (simulation/campaign/campaign_summary.py): closure.tsv with one row per
run (runs without a closure marked missing) and beam_points_v10.txt with the tuned gun, readable by make_sim_dag."""
import importlib.util
import json
import os
import subprocess

from conftest import ROOT

CAMPAIGN = os.path.join(ROOT, "simulation", "campaign")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(CAMPAIGN, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _campaign(tmp_path):
    runs = tmp_path / "runs.txt"
    runs.write_text("# test\nTB2026CERN_run_000022 th230 E1 7.5 e-\nTB2026CERN_eudaq_run_000291 th210 - 20 e-\n")
    (tmp_path / "c" / "params").mkdir(parents=True)
    (tmp_path / "c" / "closure").mkdir()
    spot = {"x": -47.0, "y": 48.0, "wx": 20.0, "wy": 19.0, "n": 4100}
    for run in ("TB2026CERN_run_000022", "TB2026CERN_eudaq_run_000291"):
        p = {"run": run, "data": spot, "gun0": {"x": -47, "y": 48, "sx": 20, "sy": 19},
             "dummy": dict(spot, wx=24.0), "gun": {"x": -46.94, "y": 48.0, "sx": 14.83, "sy": 19.0},
             "n_events": 6000, "n_chunks": 3}
        (tmp_path / "c" / "params" / f"{run}.json").write_text(json.dumps(p))
    c = {"data": spot, "sim": dict(spot, x=-46.5), "dx": 0.5, "dy": 0.0, "rwx": 0.0, "rwy": 0.0, "flag": False}
    (tmp_path / "c" / "closure" / "TB2026CERN_run_000022.json").write_text(json.dumps(c))
    return tmp_path / "c", runs


def test_summary_writes_tables(tmp_path):
    camp, runs = _campaign(tmp_path)
    r = subprocess.run(["python3", os.path.join(CAMPAIGN, "campaign_summary.py"), str(camp), str(runs)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    rows = [line.split("\t") for line in (camp / "closure.tsv").read_text().splitlines() if not line.startswith("#")]
    assert len(rows) == 2
    assert rows[0][0] == "TB2026CERN_run_000022" and rows[0][-1] == "ok"
    assert rows[1][0] == "TB2026CERN_eudaq_run_000291" and rows[1][-1] == "missing"
    points = _load("make_sim_dag").read_points(str(camp / "beam_points_v10.txt"))
    assert [p["name"] for p in points] == ["TB2026CERN_run_000022", "TB2026CERN_eudaq_run_000291"]
    assert (points[0]["set"], points[0]["label"], points[0]["E"]) == ("th230", "E1", "7.5")
    assert (points[0]["x"], points[0]["sx"], points[0]["runs"]) == ("-46.9", "14.8", "TB2026CERN_run_000022")
