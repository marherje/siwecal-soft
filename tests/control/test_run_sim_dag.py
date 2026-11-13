"""DAG writer of the run-by-run simulation (simulation/campaign/make_run_sim_dag.py) on fake data valtrees: node graph
per run, the data parameters it measures with siwecal_beamspot, skipped runs, DONE detection, --max-events."""
import json
import os
import re
import subprocess

import numpy as np
import pytest

from conftest import ROOT

A, B = "TB2026CERN_run_000022", "TB2026CERN_eudaq_run_000291"


@pytest.fixture
def setup(tmp_path, k4env):
    import uproot
    (tmp_path / "reco" / A).mkdir(parents=True)
    r = np.random.default_rng(3)
    with uproot.recreate(str(tmp_path / "reco" / A / f"ecal_{A}.valtree.root")) as f:   # 4500 shower-like events
        f["ecal"] = {"nhit_chan": np.full(4500, 100, np.int32), "bar_x": r.normal(-47, 20, 4500),
                     "bar_y": r.normal(48, 19, 4500)}
    runs = tmp_path / "runs.txt"
    runs.write_text(f"{A} th230 E1 7.5 e-\n{B} th210 - 74 e-\n")      # B has no valtree
    return tmp_path, runs, k4env


def _write(setup, *extra):
    tmp, runs, env = setup
    cmd = ["python3", os.path.join(ROOT, "simulation/campaign/make_run_sim_dag.py"), "--campaign", "t", "--runs",
           str(runs), "--data-reco", str(tmp / "reco"), "--out", str(tmp / "out"), "--dag-dir", str(tmp / "dag"),
           "--min-events", "0", *extra]   # the fake run is short; tests that need the cut pass their own
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout, (tmp / "dag" / "t.dag").read_text(), tmp


def _nodes(dag, prefix):
    return re.findall(rf"^JOB ({prefix}\S*) ", dag, re.M)


def test_dag_graph(setup):
    out, dag, _ = _write(setup)
    assert f"SKIP {B}: no valtree" in out
    assert _nodes(dag, "d_") == [f"d_{A}"] and _nodes(dag, "g_") == [f"g_{A}"]
    chunks = _nodes(dag, "c_")
    assert chunks == [f"c_{A}_000", f"c_{A}_001", f"c_{A}_002"]
    assert f"PARENT d_{A} CHILD {' '.join(chunks)}" in dag
    assert f"PARENT {' '.join(chunks)} CHILD g_{A}" in dag
    assert f"PARENT g_{A} CHILD summary" in dag
    # the group node holds the run's trees and PID outputs locally: its disk request scales with the run
    assert re.search(rf'^VARS g_{A} .*DISK="20000"', dag, re.M)            # 6000 events: the 20 GB floor
    assert "request_disk            = $(DISK)M" in (setup[0] / "dag" / "group.sub").read_text()
    assert not os.path.exists(setup[0] / "out"), "nothing is written to the output area without --submit"


def test_data_json(setup):
    _, _, tmp = _write(setup)
    p = json.load(open(tmp / "dag" / "params" / f"{A}.data.json"))
    assert p["n_events"] == 6000 and p["n_chunks"] == 3 and p["data"]["n"] == 4500
    assert (p["set"], p["label"], p["E"], p["particle"]) == ("th230", "E1", "7.5", "e-")
    assert p["gun0"]["x"] == p["data"]["x"] and p["gun0"]["sx"] == p["data"]["wx"]
    assert abs(p["data"]["x"] + 47) < 1.5 and abs(p["data"]["wx"] - 20) < 1.5


def test_done_detection(setup):
    tmp = setup[0]
    (tmp / "out" / "params").mkdir(parents=True)
    (tmp / "out" / "params" / f"{A}.json").write_text("{}")
    _, dag, _ = _write(setup)
    assert re.search(rf"^JOB d_{A} \S+ DONE$", dag, re.M)
    assert not re.search(rf"^JOB c_{A}_000 \S+ DONE$", dag, re.M)


def test_short_runs_are_skipped(setup):
    out, dag, _ = _write(setup, "--min-events", "5000")      # run A has 4500 events
    assert f"SKIP {A}: 4500 events < --min-events 5000" in out
    assert not _nodes(dag, "d_")


def test_max_events(setup):
    _, dag, _ = _write(setup, "--max-events", "1000", "--chunk-events", "500")
    assert _nodes(dag, "c_") == [f"c_{A}_000", f"c_{A}_001"]
    assert 'CH="500"' in dag
