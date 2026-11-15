"""Optional far collimator of the run-by-run simulation (simulation/campaign/collimator.py, make_run_sim_dag.py
--far-collimator): energy -> aperture spec, the derived compact (jaws, includes, overlap guard) and the DAG wiring
(only the runs of a listed energy get the collimated compact)."""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from conftest import ROOT

_spec = importlib.util.spec_from_file_location("collimator", os.path.join(ROOT, "simulation", "campaign",
                                                                          "collimator.py"))
collimator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(collimator)

GEO = os.path.join(ROOT, "simulation", "geometry")
BASE = "SND_compact_beamline.xml"


def test_parse_spec_and_aperture():
    spec = collimator.parse_spec("7.5=23, 10=30")
    assert spec == {7.5: 23.0, 10.0: 30.0}
    assert collimator.aperture(spec, "7.5") == 23.0 and collimator.aperture(spec, 10) == 30.0
    assert collimator.aperture(spec, "20") is None and collimator.aperture({}, "7.5") is None
    assert collimator.parse_spec("") == {} and collimator.parse_spec(None) == {}
    for bad in ("7.5", "7.5=0", "7.5=-3", "x=3"):
        with pytest.raises(ValueError):
            collimator.parse_spec(bad)


@pytest.fixture
def geo(tmp_path):
    shutil.copy(os.path.join(GEO, BASE), tmp_path / BASE)
    return tmp_path


def test_derived_compact(geo):
    rel = collimator.write_compact(BASE, "generated/c/RUN.xml", -8.0, 6.5, 23.0, geo=str(geo))
    text = (geo / rel).read_text()
    root = ET.fromstring(text)   # well-formed (Xerces in DD4hep is stricter still: no "--" inside comments)
    assert all("--" not in c for c in re.findall(r"<!--(.*?)-->", text, re.S))
    jaws = [d for d in root.iter("detector") if d.get("name", "").startswith("H2_FarColl")]
    assert len(jaws) == 4 and all(d.find("material").get("name") == "Iron" for d in jaws)
    ids = [d.get("id") for d in root.iter("detector")]
    assert len(ids) == len(set(ids)), "detector ids must stay unique"
    # every include of the base file now points back to the geometry folder, and exists there
    base_refs = re.findall(r'ref="([^"]+\.xml)"', (geo / BASE).read_text())
    refs = re.findall(r'ref="([^"]+\.xml)"', text)
    assert refs == [f"../../{r}" for r in base_refs]
    assert all(os.path.exists(os.path.join(GEO, r)) for r in base_refs)
    # the hole: left/right jaws at +-(a + w/2) around the centre, 1 m long at -26 m
    left = next(d for d in jaws if d.get("name") == "H2_FarCollL")
    assert left.find("position").get("x") == f"{-8.0 - 23.0 - collimator.JAW_W / 2:.4f}*mm"
    assert left.find("position").get("z") == "Beamline_Front_z+(-26000.0000)*mm"
    assert left.find("box").get("z") == "500.0000*mm"
    # the rest of the line is untouched
    def dump(d):
        d.tail = None
        return ET.tostring(d)
    rest = [dump(d) for d in root.iter("detector") if not d.get("name", "").startswith("H2_FarColl")]
    assert rest == [dump(d) for d in ET.fromstring((geo / BASE).read_text()).iter("detector")]


@pytest.mark.parametrize("z", [-27000.0, -45000.0, -2500.0, -100.0, 200.0])
def test_overlap_guard(geo, z):
    """DWC2 (-27 m), the vacuum exit window (-45 m), the near line (-2.5 m) and the box: refused."""
    with pytest.raises(ValueError, match="overlaps"):
        collimator.write_compact(BASE, "generated/c/RUN.xml", 0.0, 0.0, 23.0, z=z, geo=str(geo))
    assert not (geo / "generated" / "c" / "RUN.xml").exists()


def test_free_slots_of_the_far_line(geo):
    for z in (-26000.0, -33500.0, -42500.0):   # the air gaps between the upstream detectors (collimator tests)
        collimator.write_compact(BASE, f"generated/c/z{-z:g}.xml", 0.0, 0.0, 23.0, z=z, geo=str(geo))


def test_dd4hep_builds_the_derived_compact(k4env):
    """The derived file loads in DD4hep from its real place in the geometry folder (includes resolved)."""
    rel = f"generated/pytest_{os.getpid()}/RUN.xml"
    try:
        collimator.write_compact(BASE, rel, -8.0, 6.5, 23.0)
        code = ("import dd4hep, sys; d = dd4hep.Detector.getInstance(); d.fromXML(sys.argv[1]); "
                "print(sorted(n for n in d.detectors() if str(n).startswith('H2_FarColl')))")
        r = subprocess.run(["python3", "-c", code, os.path.join(GEO, rel)], env=k4env, capture_output=True, text=True,
                           timeout=300)
        assert r.returncode == 0, r.stderr[-2000:]
        assert "H2_FarCollB" in r.stdout and "H2_FarCollT" in r.stdout
    finally:
        shutil.rmtree(os.path.join(GEO, os.path.dirname(rel)), ignore_errors=True)


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
    camp = f"pytest_{os.getpid()}"
    yield tmp_path, camp, k4env
    shutil.rmtree(os.path.join(GEO, "generated", camp), ignore_errors=True)


def _dag(runs, *extra):
    tmp, camp, env = runs
    cmd = ["python3", os.path.join(ROOT, "simulation/campaign/make_run_sim_dag.py"), "--campaign", camp, "--runs",
           str(tmp / "runs.txt"), "--data-reco", str(tmp / "reco"), "--out", str(tmp / "out"), "--dag-dir",
           str(tmp / "dag"), "--min-events", "0", *extra]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout, (tmp / "dag" / f"{camp}.dag").read_text()


def _compact(dag, node):
    return re.search(rf'^VARS {node} .*COMPACT="([^"]+)"', dag, re.M).group(1)


def test_dag_collimates_only_the_listed_energy(runs):
    tmp, camp, _ = runs
    out, dag = _dag(runs, "--far-collimator", "7.5=23")
    gen = f"generated/{camp}/{A}.xml"
    assert _compact(dag, f"d_{A}") == gen and _compact(dag, f"c_{A}_000") == gen
    assert _compact(dag, f"d_{B}") == BASE and _compact(dag, f"c_{B}_000") == BASE
    assert os.path.exists(os.path.join(GEO, gen)) and not os.path.exists(os.path.join(GEO, f"generated/{camp}/{B}.xml"))
    assert "far collimator a 23 mm" in out
    pa = json.load(open(tmp / "dag" / "params" / f"{A}.data.json"))
    pb = json.load(open(tmp / "dag" / "params" / f"{B}.data.json"))
    assert pa["far_collimator"] == {"a": 23.0, "z": -26000.0, "length": 1000.0} and pa["compact"] == gen
    assert pb["far_collimator"] is None and pb["compact"] == BASE
    # centred on the run's data spot
    left = next(d for d in ET.parse(os.path.join(GEO, gen)).getroot().iter("detector")
                if d.get("name") == "H2_FarCollL")
    assert left.find("position").get("x") == f"{pa['data']['x'] - 23.0 - collimator.JAW_W / 2:.4f}*mm"
    for sub in ("dummy", "chunk"):
        assert "COMPACT_FILE=$(COMPACT)" in (tmp / "dag" / f"{sub}.sub").read_text()


def test_dag_without_collimator_is_unchanged(runs):
    _, camp, _ = runs
    _, dag = _dag(runs)
    assert {_compact(dag, n) for n in (f"d_{A}", f"c_{A}_000", f"d_{B}", f"c_{B}_000")} == {BASE}
    assert not os.path.exists(os.path.join(GEO, "generated", camp))


def test_bad_spec_is_refused(runs):
    tmp, camp, env = runs
    r = subprocess.run(["python3", os.path.join(ROOT, "simulation/campaign/make_run_sim_dag.py"), "--campaign", camp,
                        "--runs", str(tmp / "runs.txt"), "--dag-dir", str(tmp / "dag"), "--far-collimator", "7.5"],
                       env=env, capture_output=True, text=True)
    assert r.returncode != 0 and "expected <energy GeV>=<half-aperture mm>" in r.stderr
