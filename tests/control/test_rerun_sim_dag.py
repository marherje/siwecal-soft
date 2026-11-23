"""Re-run DAG of a finished run-by-run campaign (simulation/campaign/make_rerun_sim_dag.py) on a fake source campaign:
the source's guns, chunk counts and seeds are kept, only the digitiser environment changes, the collimated runs get
their geometry written again (identical to what collimator.py writes), and inconsistent inputs stop it."""
import json
import os
import re
import shutil
import subprocess

import pytest

from conftest import ROOT

FREE, RECT, OPEN = "TB2026CERN_eudaq_run_000291", "TB2026CERN_run_000022", "TB2026CERN_run_000021"
CAMP = "test_rerun_dag"
GEN = os.path.join(ROOT, "simulation", "geometry", "generated")


def _params(run, E, n_chunks, far=None, compact="SND_compact_beamline.xml"):
    return {"run": run, "E": E, "set": "th230", "label": "E1", "particle": "e-", "chunk_events": 2000,
            "n_chunks": n_chunks, "n_events": n_chunks * 2000, "compact": compact, "far_collimator": far,
            "data": {"x": -47.06, "y": 47.75, "wx": 23.1, "wy": 21.3, "n": 1000, "entries": 1200},
            "gun": {"x": -55.8, "y": 57.4, "sx": 1.0, "sy": 21.3}}


@pytest.fixture
def setup(tmp_path, k4env):
    src = tmp_path / "src"
    (src / "params").mkdir(parents=True)
    far = {"mode": "rect", "z": -26000.0, "length": 1000.0, "transmission": 0.4}
    runs = {FREE: _params(FREE, "20", 3),
            RECT: _params(RECT, "7.5", 2, dict(far, ax=None, ay=22.9), f"generated/src/{RECT}.xml"),
            OPEN: _params(OPEN, "10", 2, dict(far, ax=None, ay=None), f"generated/src/{OPEN}.xml")}
    for run, p in runs.items():
        json.dump(p, open(src / "params" / f"{run}.json", "w"))
        json.dump({"run": run}, open(src / "params" / f"{run}.data.json", "w"))
    (tmp_path / "runs.txt").write_text(f"{RECT} th230 E1 7.5 e-\n{OPEN} th230 E1 10 e-\n{FREE} th210 - 20 e-\n"
                                       "TB2026CERN_run_000067 th230 E1 20 e-\n")   # 67: not in the source
    (tmp_path / "seeds.txt").write_text(f"# RUN seed_chunk0 n_chunks\n{RECT} 30001000 2\n{OPEN} 30002000 2\n"
                                        f"{FREE} 20003000 3\n")
    yield tmp_path, k4env
    shutil.rmtree(os.path.join(GEN, CAMP), ignore_errors=True)


def _write(setup, *extra, ok=True):
    tmp, env = setup
    cmd = ["python3", os.path.join(ROOT, "simulation/campaign/make_rerun_sim_dag.py"), "--source", str(tmp / "src"),
           "--campaign", CAMP, "--runs", str(tmp / "runs.txt"), "--seeds", str(tmp / "seeds.txt"),
           "--out", str(tmp / "out"), "--dag-dir", str(tmp / "dag"), *extra]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert (r.returncode == 0) == ok, r.stdout + r.stderr
    return r.stdout + r.stderr, tmp


def _dag(tmp):
    return (tmp / "dag" / f"{CAMP}.dag").read_text()


def test_graph_seeds_and_no_tuning(setup):
    out, tmp = _write(setup, "--no-occupancy-sag")
    dag = _dag(tmp)
    assert "SKIP TB2026CERN_run_000067: not in the source" in out
    assert not re.search(r"^JOB (d|d1|d2|p2|p3)_", dag, re.M), "the re-run does not tune again"
    assert re.findall(r'^VARS c_\S+ RUN="\S+" K="(\d+)" SEED="(\d+)"', dag, re.M) == [
        ("0", "30001000"), ("1", "30001001"), ("0", "30002000"), ("1", "30002001"),
        ("0", "20003000"), ("1", "20003001"), ("2", "20003002")]
    assert f"PARENT c_{FREE}_000 c_{FREE}_001 c_{FREE}_002 CHILD g_{FREE}" in dag
    assert f"PARENT g_{RECT} g_{OPEN} g_{FREE} CHILD summary" in dag
    assert not (tmp / "out").exists(), "nothing is written to the output area without --submit"


def test_digitiser_environment(setup):
    _, tmp = _write(setup, "--no-occupancy-sag", "--digi-env", "PED_NOISE=0")
    env = re.search(r'^environment\s*=\s*"(.*)"$', (tmp / "dag" / "chunk.sub").read_text(), re.M).group(1)
    assert "OCCUPANCY_SAG_TABLE='' OCCUPANCY_SLOPE='0' PED_NOISE='0'" in env and "PHYSICS_LIST=QGSP_BERT_EMZ" in env
    p = json.load(open(tmp / "dag" / "params" / f"{FREE}.json"))
    assert p["gun"] == {"x": -55.8, "y": 57.4, "sx": 1.0, "sy": 21.3} and p["n_chunks"] == 3
    assert p["rerun"]["digi_env"] == {"OCCUPANCY_SAG_TABLE": "", "OCCUPANCY_SLOPE": "0", "PED_NOISE": "0"}
    assert p["rerun"]["seed_chunk0"] == 20003000 and len(p["rerun"]["commit"]) == 40
    assert (tmp / "dag" / "launched_from.txt").read_text().strip() == p["rerun"]["commit"]


def test_geometries_written_again(setup):
    import collimator
    _, tmp = _write(setup, "--no-occupancy-sag")
    dag = _dag(tmp)
    assert re.search(rf'^VARS c_{FREE}_000 .*COMPACT="SND_compact_beamline.xml"', dag, re.M)
    for run, ay in ((RECT, 22.9), (OPEN, None)):
        rel = f"generated/{CAMP}/{run}.xml"
        assert re.search(rf'^VARS c_{run}_000 .*COMPACT="{rel}"', dag, re.M)
        assert json.load(open(tmp / "dag" / "params" / f"{run}.json"))["compact"] == rel
        new = open(os.path.join(GEN, CAMP, f"{run}.xml")).read()
        ref = f"generated/{CAMP}/ref_{run}.xml"
        if ay:
            collimator.write_compact("SND_compact_beamline.xml", ref, -47.06, 47.75, None, -26000.0, 1000.0, ay=ay)
        else:
            collimator.write_open("SND_compact_beamline.xml", ref)
        assert new == open(os.path.join(GEN, CAMP, f"ref_{run}.xml")).read()
    assert "far collimator" in open(os.path.join(GEN, CAMP, f"{RECT}.xml")).read()
    assert "far collimator" not in open(os.path.join(GEN, CAMP, f"{OPEN}.xml")).read()


def test_max_chunks(setup):
    _, tmp = _write(setup, "--no-occupancy-sag", "--max-chunks", "1")
    assert re.findall(r"^JOB (c_\S+) ", _dag(tmp), re.M) == [f"c_{RECT}_000", f"c_{OPEN}_000", f"c_{FREE}_000"]
    assert json.load(open(tmp / "dag" / "params" / f"{FREE}.json"))["n_events"] == 2000


def test_refuses_inconsistent_inputs(setup):
    tmp, _ = setup
    out, _ = _write(setup, ok=False)
    assert "nothing to change" in out
    (tmp / "seeds.txt").write_text(f"{RECT} 30001000 5\n{OPEN} 30002000 2\n")
    out, _ = _write(setup, "--no-occupancy-sag", ok=False)
    assert f"{RECT}: 5 chunks in the seeds file, 2 in" in out and f"{FREE}: no seed" in out
    assert not (tmp / "dag" / f"{CAMP}.dag").exists()


def test_refuses_the_source_as_output(setup):
    tmp, env = setup
    r = subprocess.run(["python3", os.path.join(ROOT, "simulation/campaign/make_rerun_sim_dag.py"), "--source",
                        str(tmp / "src"), "--campaign", "x", "--out", str(tmp / "src"), "--seeds",
                        str(tmp / "seeds.txt"), "--no-occupancy-sag", "--dag-dir", str(tmp / "dag")],
                       env=env, capture_output=True, text=True)
    assert r.returncode != 0 and "must not write into the source" in r.stderr


def test_final_v11_seeds_file():
    from make_rerun_sim_dag import read_seeds
    seeds = read_seeds(os.path.join(ROOT, "simulation", "campaign", "seeds_final_v11.txt"))
    assert len(seeds) == 99 and sum(n for _, n in seeds.values()) == 5221
    assert seeds["TB2026CERN_run_000022"] == (30003000, 265)
    assert {r for r in ("TB2026CERN_run_000067", "TB2026CERN_run_000070") if r in seeds} == set()
