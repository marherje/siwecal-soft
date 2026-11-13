"""The run list of the run-by-run simulation (simulation/campaign/runs_v10.txt): every run of beam_points.txt once, with
the set / label / energy of its point, named like its data folder in Reconstruction/."""
import importlib.util
import os

from conftest import ROOT

CAMPAIGN = os.path.join(ROOT, "simulation", "campaign")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(CAMPAIGN, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_run_name():
    m = _load("make_run_list")
    assert m.run_name("e291") == "TB2026CERN_eudaq_run_000291"
    assert m.run_name("22") == "TB2026CERN_run_000022"


def test_runs_v10_covers_beam_points():
    m = _load("make_run_list")
    points = _load("make_sim_dag").read_points(os.path.join(CAMPAIGN, "beam_points.txt"))
    runs = m.read_runs(os.path.join(CAMPAIGN, "runs_v10.txt"))
    assert len(runs) == len({r["run"] for r in runs}) == 103
    by_run = {r["run"]: r for r in runs}
    for p in points:
        for token in p["runs"].split(","):
            r = by_run[m.run_name(token)]
            assert (r["set"], r["label"], r["E"]) == (p["set"], p["label"], p["E"]), (p, r)
            assert r["particle"] == (p["particle"] or "e-")


def test_runs_exist_in_reconstruction(eos):
    m = _load("make_run_list")
    missing = [r["run"] for r in m.read_runs(os.path.join(CAMPAIGN, "runs_v10.txt"))
               if not os.path.isdir(os.path.join(eos, "Reconstruction", r["run"]))]
    assert not missing, missing


def test_no_angle_scan_runs():
    """The campaign simulates normal incidence only: no run of the angular scan (data_conversion/jobs/angular_scan)."""
    import yaml
    m = _load("make_run_list")
    angle = {m.run_name(str(r)) for r in yaml.safe_load(open(os.path.join(
        ROOT, "data_conversion", "jobs", "angular_scan", "runs.yml")))["runs"]}
    assert not angle & {r["run"] for r in m.read_runs(os.path.join(CAMPAIGN, "runs_v10.txt"))}
