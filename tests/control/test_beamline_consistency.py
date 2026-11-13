"""The beam origin and the upstream line belong together.

The default compact (SND_compact_beamline.xml) carries the H2-like line from -61.5 m on; a beam started downstream of
it skips that material silently (generic_condor_beam_chunk.sh did that until the monorepo: -2650 mm with the H2
compact). Every launcher default (COMPACT_FILE + BEAM_Z_MM, make_sim_dag.py --compact/--beam-z) must start the beam
upstream of the first non-vacuum element of its compact. And the digitiser has to shift its time windows by the
extra flight path (RealDigitizer.TimeOffsetNs, set in simulation/jobs/job3_digitize.py from the beam origin)."""
import math
import os
import re
import xml.etree.ElementTree as ET

import pytest

from conftest import ROOT

GEO = os.path.join(ROOT, "simulation", "geometry")
UNITS = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "um": 1e-3}


def _eval(expr, consts):
    e = expr
    for name in sorted(consts, key=len, reverse=True):
        e = re.sub(rf"\b{re.escape(name)}\b", f"({consts[name]})", e)
    e = re.sub(r"\*\s*(mm|cm|um|m)\b", lambda m: f"*{UNITS[m.group(1)]}", e)
    if re.search(r"[A-Za-z_]", e.replace("e-", "").replace("e+", "")):
        raise ValueError(expr)
    return float(eval(e, {"__builtins__": {}}, {}))  # noqa: S307 -- arithmetic on literals only


def first_material_z(compact):
    """z [mm] of the upstream face of the most upstream non-vacuum, non-air element of a compact file."""
    root = ET.parse(os.path.join(GEO, compact)).getroot()
    consts = {}
    for c in root.iter("constant"):
        try:
            consts[c.get("name")] = _eval(c.get("value"), consts)
        except (ValueError, SyntaxError, ZeroDivisionError):
            pass
    zmin = math.inf
    for det in root.iter("detector"):
        mat, box, pos = det.find("material"), det.find("box"), det.find("position")
        if mat is None or box is None or pos is None or mat.get("name", "").lower() in ("vacuum", "air"):
            continue
        z, half = _eval(pos.get("z", "0"), consts), _eval(box.get("z", "0"), consts)
        zmin = min(zmin, z - half)
    return zmin


def launcher_defaults():
    """(file, compact, beam z) of every launcher that sets both defaults."""
    out = []
    for d in (os.path.join(ROOT, "simulation"), os.path.join(ROOT, "analysis")):
        for dp, dn, fn in os.walk(d):
            for n in fn:
                if not n.endswith((".sh", ".py")):
                    continue
                p = os.path.join(dp, n)
                t = open(p, errors="replace").read()
                c = re.search(r"COMPACT_FILE=\$\{COMPACT_FILE:-([\w.]+)\}", t) or \
                    re.search(r'add_argument\("--compact", default="([\w.]+)"', t)
                z = re.search(r"BEAM_Z_MM=\$\{BEAM_Z_MM:-(-?[\d.]+)\}", t) or \
                    re.search(r'add_argument\("--beam-z", type=float, default=(-?[\d.]+)', t)
                if c and z:
                    out.append((os.path.relpath(p, ROOT), c.group(1), float(z.group(1))))
    return out


def test_h2_line_starts_at_61_5_m():
    assert first_material_z("SND_compact_beamline.xml") == pytest.approx(-61501.0, abs=1.0)


@pytest.mark.parametrize("rel,compact,beam_z", launcher_defaults())
def test_launcher_beam_starts_upstream_of_its_line(rel, compact, beam_z):
    assert beam_z < first_material_z(compact), (
        f"{rel}: beam born at {beam_z} mm but {compact} has material from {first_material_z(compact):.0f} mm")


def test_every_launcher_was_checked():
    files = {r for r, _, _ in launcher_defaults()}
    for must in ("simulation/campaign/make_sim_dag.py", "simulation/run/launch_beam_final.sh",
                 "simulation/run/generic_condor_beam.sh", "simulation/run/generic_condor_beam_chunk.sh"):
        assert must in files, must


def test_time_offset_follows_the_beam_origin():
    src = open(os.path.join(ROOT, "simulation", "jobs", "job3_digitize.py")).read()
    assert re.search(r"real\.TimeOffsetNs\s*=\s*max\(0\.0,\s*-BEAM_Z_MM\s*-\s*2650\.0\)\s*/\s*299\.792458", src)
