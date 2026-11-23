"""Angular-scan simulation inputs (simulation/campaign/launch_angle_scan.sh): the turned geometry of angle_geometry.py
(rotation in the ECAL envelope only, includes that resolve, kept by the far-collimator compact) and runs_angle.txt."""
import os
import re
import shutil
import sys

import pytest
import yaml

from conftest import ROOT

CAMPAIGN = os.path.join(ROOT, "simulation", "campaign")
sys.path.insert(0, CAMPAIGN)
import angle_geometry  # noqa: E402
import collimator  # noqa: E402
from make_run_list import read_runs, run_name  # noqa: E402


@pytest.fixture
def geo(tmp_path):
    for f in ("SND_compact_beamline.xml", "SiPadDetector_beamline.xml", "elements.xml", "materials.xml"):
        shutil.copy(os.path.join(collimator.GEO, f), tmp_path / f)
    return tmp_path


def _refs(path):
    """Every include of a file, resolved from its own folder."""
    return [os.path.normpath(os.path.join(os.path.dirname(path), r)) for r in re.findall(r'ref="([^"]+)"', open(path).read())]


@pytest.mark.parametrize("angle,tag", [(30, "roty30"), (-5, "rotym5"), (7.5, "roty7p5")])
def test_turned_geometry(geo, angle, tag):
    rel = angle_geometry.write("c", angle, geo=str(geo))
    assert rel == f"generated/c/SND_compact_beamline_{tag}.xml"
    det = geo / "generated" / "c" / f"SiPadDetector_beamline_{tag}.xml"
    orig = open(geo / "SiPadDetector_beamline.xml").read()
    new = det.read_text()
    assert re.search(rf'<envelope\b.*?<rotation x="0" y="{angle:g}\*deg" z="0"/>', new, re.S)
    assert new.count("<rotation") == orig.count("<rotation") == 1
    note = f"<!-- angle_geometry.py: ECAL turned by {angle:g} deg about y -->\n  "
    assert new.count(note) == 1
    assert new.replace(note, "").replace(f'y="{angle:g}*deg"', 'y="0"') == orig
    compact = geo / rel
    refs = _refs(str(compact))
    assert str(det) in refs and str(geo / "SiPadDetector_beamline.xml") not in refs
    assert all(os.path.exists(r) for r in refs if r.endswith(("elements.xml", "materials.xml")) or "SiPad" in r)
    # the base compact otherwise unchanged
    strip = lambda t: re.sub(r'ref="[^"]*"', "", t)   # noqa: E731
    assert strip(compact.read_text()) == strip(open(geo / "SND_compact_beamline.xml").read())


def test_far_collimator_keeps_the_turned_detector(geo):
    base = angle_geometry.write("c", 10, geo=str(geo))
    rel = collimator.write_compact(base, "generated/c/RUN.xml", -47.0, 47.0, None, ay=22.9, geo=str(geo))
    refs = _refs(str(geo / rel))
    assert str(geo / "generated" / "c" / "SiPadDetector_beamline_roty10.xml") in refs
    assert all(os.path.exists(r) for r in refs if r.endswith(".xml") and ("SiPad" in r or "elements" in r))
    assert "far collimator" in (geo / rel).read_text()


def test_runs_angle_list():
    runs = read_runs(os.path.join(CAMPAIGN, "runs_angle.txt"))
    angles = {}
    for line in open(os.path.join(CAMPAIGN, "runs_angle.txt")):
        f = line.split("#")[0].split()
        if f:
            angles[f[0]] = int(f[5])
    assert len(runs) == 20 and sorted(set(angles.values())) == [5, 10, 30]
    scan = {run_name("e" + str(r)) for r in yaml.safe_load(open(os.path.join(
        ROOT, "data_conversion", "jobs", "angular_scan", "runs.yml")))["runs"]}
    assert {r["run"] for r in runs} <= scan
    for r in runs:
        assert r["set"] == "th210" and r["label"] == f"A{angles[r['run']]}"
    for a in (5, 10, 30):   # one energy scan per angle
        es = sorted(float(r["E"]) for r in runs if angles[r["run"]] == a)
        assert {7.5, 10, 20, 34, 52, 74} <= set(es)
    assert not {r["run"] for r in runs} & {r["run"] for r in read_runs(os.path.join(CAMPAIGN, "runs_v10.txt"))}


def test_launcher_seed_offsets_do_not_overlap():
    text = open(os.path.join(CAMPAIGN, "launch_angle_scan.sh")).read()
    assert "--seed-offset $((40000000 + A * 100000))" in text
    offs = [40000000 + a * 100000 for a in (5, 10, 30)]
    # make_run_sim_dag.py: seed = offset + line * 1000 + chunk, at most 8 lines per angle and < 1000 chunks
    spans = [(o, o + 9 * 1000) for o in offs]
    assert all(a[1] < b[0] for a, b in zip(spans, spans[1:])) and offs[0] > 30000000 + 13 * 1000
