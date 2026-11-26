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
import collimator_prep  # noqa: E402
from make_run_list import read_runs, run_name  # noqa: E402
from siwecal_common.compact_geometry import ecal_turn_deg, lab_x  # noqa: E402


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


@pytest.mark.parametrize("angle", [30, -5, 7.5])
def test_turn_is_read_from_the_geometry(geo, angle):
    """job3_digitize.py (hit frame) and make_run_sim_dag.py (gun) take the turn from the compact of the run, also from the
    one derived with the far collimator."""
    base = angle_geometry.write("c", angle, geo=str(geo))
    assert ecal_turn_deg(base, geo=str(geo)) == angle
    assert ecal_turn_deg(str(geo / base)) == angle
    assert ecal_turn_deg("SND_compact_beamline.xml", geo=str(geo)) == 0
    rel = collimator.write_compact(base, "generated/c/RUN.xml", -47.0, 47.0, None, ay=22.9, geo=str(geo))
    assert ecal_turn_deg(rel, geo=str(geo)) == angle
    rel = collimator.write_open(base, "generated/c/RUN2.xml", str(geo))
    assert ecal_turn_deg(rel, geo=str(geo)) == angle


def test_only_turns_about_y(geo):
    base = angle_geometry.write("c", 10, geo=str(geo))
    det = geo / "generated" / "c" / "SiPadDetector_beamline_roty10.xml"
    det.write_text(det.read_text().replace('<rotation x="0"', '<rotation x="5*deg"'))
    with pytest.raises(ValueError):
        ecal_turn_deg(base, geo=str(geo))


def test_lab_x_of_a_turned_ecal():
    """Lab x of the beam from the ECAL-frame barycentre and its depth: what a straight line at lab x gives back."""
    import math
    depths = [-107.95 + 15 * i for i in range(15)]
    t = math.radians(30)
    for x_lab, layer in ((0.0, 5.0), (12.0, 2.5), (-20.0, 9.0)):
        z = -107.95 + 15 * layer
        x_ecal = (x_lab - math.sin(t) * z) / math.cos(t)    # the line x_lab, seen from the turned box
        assert abs(lab_x(x_ecal, layer, 30.0, depths) - x_lab) < 1e-9
    assert lab_x(33.0, 5.0, 0.0, depths) == 33.0


def test_collimator_centre_in_the_lab():
    """The jaws are in the lab: at the data spot, or, with a turned ECAL, at the free-line gun; x widths cos(turn) shorter."""
    data, gun = {"x": -20.0, "y": 5.0}, {"x": -12.0, "y": 4.0}
    assert collimator_prep.lab_spot({"data": data}, gun) == (-20.0, 5.0, 1.0)
    x, y, c = collimator_prep.lab_spot({"data": data, "turn_deg": 60.0}, gun)
    assert (x, y) == (-12.0, 5.0) and abs(c - 0.5) < 1e-12


def test_runs_angle_list():
    runs = read_runs(os.path.join(CAMPAIGN, "runs_angle.txt"))
    angles = {}
    for line in open(os.path.join(CAMPAIGN, "runs_angle.txt")):
        f = line.split("#")[0].split()
        if f:
            angles[f[0]] = int(f[5])
    assert len(runs) == 24 and sorted(set(angles.values())) == [5, 10, 30, 45]
    data = yaml.safe_load(open(os.path.join(ROOT, "data_conversion", "jobs", "angular_scan", "runs.yml")))
    scan = {run_name("e" + str(r)) for r in data["runs"]}
    assert {r["run"] for r in runs} <= scan
    positrons = [r for r in runs if r["particle"] == "e-"]
    muons = [r for r in runs if r["particle"] == "mu-"]
    assert len(positrons) == 20 and len(muons) == 4
    for r in positrons:
        assert r["set"] == "th210" and r["label"] == f"A{angles[r['run']]}"
    for a in (5, 10, 30):   # one energy scan per angle
        es = sorted(float(r["E"]) for r in positrons if angles[r["run"]] == a)
        assert {7.5, 10, 20, 34, 52, 74} <= set(es)
    # the 45 deg muons: 150 GeV, the threshold set of their data reconstruction
    th = {run_name("e" + str(n)): f"th{t}" for n, t in data.get("thresholds", {}).items()}
    for r in muons:
        assert (r["label"], float(r["E"]), angles[r["run"]]) == ("M45", 150, 45)
        assert r["set"] == th.get(r["run"], f"th{data['threshold']}")
    assert sorted(r["set"] for r in muons) == ["th210", "th220", "th230", "th230"]
    assert not {r["run"] for r in runs} & {r["run"] for r in read_runs(os.path.join(CAMPAIGN, "runs_v10.txt"))}


def test_runs_muon_list():
    """Normal-incidence muons for tracking: one 150 GeV run per threshold set, the runs of muon_points.txt."""
    runs = read_runs(os.path.join(CAMPAIGN, "runs_muon.txt"))
    assert sorted(r["set"] for r in runs) == ["th210", "th220", "th230"]
    assert all((r["particle"], float(r["E"]), r["label"]) == ("mu-", 150, "M0") for r in runs)
    points = [ln.split() for ln in open(os.path.join(CAMPAIGN, "muon_points.txt")) if ln.strip() and ln[0] != "#"]
    assert {r["run"] for r in runs} == {run_name(p[-1]) for p in points}
    assert not {r["run"] for r in runs} & {r["run"] for r in read_runs(os.path.join(CAMPAIGN, "runs_v10.txt"))}


def test_launcher_seed_offsets_do_not_overlap():
    text = open(os.path.join(CAMPAIGN, "launch_angle_scan.sh")).read()
    assert "--seed-offset $((40000000 + A * 100000))" in text
    offs = [40000000 + a * 100000 for a in (5, 10, 30)]
    # make_run_sim_dag.py: seed = offset + line * 1000 + chunk, at most 8 lines per angle and < 1000 chunks
    spans = [(o, o + 9 * 1000) for o in offs]
    assert all(a[1] < b[0] for a, b in zip(spans, spans[1:])) and offs[0] > 30000000 + 13 * 1000
