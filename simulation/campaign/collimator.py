"""Optional far collimator of the run-by-run simulation (make_run_sim_dag.py --far-collimator).

The 7.5 GeV beam spot of the data has truncated tails (p95-p5 over IQR 2.30, a gaussian gives 2.44) that the
free upstream line does not produce; iron jaws ~26 m upstream of the box, after the upstream detectors, reproduce
core and tails (collimator tests, 2026-11-15: half-aperture 22-25 mm). The 20 and 74 GeV spots are not truncated
and the same jaws would cut them, as in the real H2 line, where the collimators were set run by run. So the
aperture is given per beam energy and the runs of any other energy keep the free line:

    --far-collimator 7.5=23            # runs at 7.5 GeV: half-aperture 23 mm; every other energy: no collimator
    --far-collimator 7.5=23,10=30

Per collimated run a compact is derived from the campaign's compact: four iron jaws (square aperture of half-side A,
centred on the run's data spot, 1 m long by default) in the open air at z (default -26 m from the box front), written
to simulation/geometry/generated/<campaign>/ (git-ignored); the jaws may not overlap any element of the line.
"""
import math
import os
import re
import xml.etree.ElementTree as ET

GEO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "geometry")
UNITS = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "um": 1e-3}
JAW_W = 100.0            # jaw thickness across the beam [mm]
IDS = range(190, 194)    # detector ids of the jaws (the line uses 100-157)


def parse_spec(spec):
    """'7.5=23,10=30' -> {7.5: 23.0, 10.0: 30.0} (beam energy GeV -> half-aperture mm); '' or None -> {}."""
    out = {}
    for item in filter(None, (s.strip() for s in (spec or "").split(","))):
        e, sep, a = item.partition("=")
        if not sep:
            raise ValueError(f"far collimator '{item}': expected <energy GeV>=<half-aperture mm>")
        e, a = float(e), float(a)
        if a <= 0:
            raise ValueError(f"far collimator '{item}': the half-aperture must be positive")
        out[e] = a
    return out


def aperture(spec, energy):
    """Half-aperture [mm] for a run of this energy, or None (no collimator)."""
    e = float(energy)
    return next((a for k, a in spec.items() if math.isclose(k, e, abs_tol=1e-6)), None)


def _eval(expr, consts):
    e = expr
    for name in sorted(consts, key=len, reverse=True):
        e = re.sub(rf"\b{re.escape(name)}\b", f"({consts[name]})", e)
    e = re.sub(r"\*\s*(mm|cm|um|m)\b", lambda m: f"*{UNITS[m.group(1)]}", e)
    if re.search(r"[A-Za-z_]", e.replace("e-", "").replace("e+", "")):
        raise ValueError(expr)
    return float(eval(e, {"__builtins__": {}}, {}))  # noqa: S307 -- arithmetic on literals only


def line_extents(text):
    """(name, z_lo, z_hi) [mm] of every box element of a compact text whose position can be evaluated."""
    root = ET.fromstring(text)
    consts = {}
    for c in root.iter("constant"):
        try:
            consts[c.get("name")] = _eval(c.get("value"), consts)
        except (ValueError, SyntaxError, ZeroDivisionError):
            pass
    out = []
    for det in root.iter("detector"):
        box, pos = det.find("box"), det.find("position")
        if box is None or pos is None:
            continue
        try:
            z, half = _eval(pos.get("z", "0"), consts), _eval(box.get("z", "0"), consts)
        except (ValueError, SyntaxError):
            continue
        out.append((det.get("name"), z - half, z + half))
    return out


def _box(name, did, hx, hy, hz, x, y, z):
    return (f'    <detector name="{name}" type="DD4hep_BoxSegment" id="{did}" vis="AlVis">\n'
            f'      <material name="Iron"/>\n'
            f'      <box x="{hx:.4f}*mm" y="{hy:.4f}*mm" z="{hz:.4f}*mm"/>\n'
            f'      <position x="{x:.4f}*mm" y="{y:.4f}*mm" z="Beamline_Front_z+({z:.4f})*mm"/>\n'
            f'      <rotation x="0" y="0" z="0"/>\n    </detector>\n')


def jaws(cx, cy, z, a, length):
    """The four iron jaws: a square hole of half-side a centred on (cx, cy), from z - length/2 to z + length/2."""
    hl, w = length / 2, JAW_W
    i = iter(IDS)
    return (_box("H2_FarCollL", next(i), w / 2, a + w, hl, cx - a - w / 2, cy, z)
            + _box("H2_FarCollR", next(i), w / 2, a + w, hl, cx + a + w / 2, cy, z)
            + _box("H2_FarCollT", next(i), a, w / 2, hl, cx, cy + a + w / 2, z)
            + _box("H2_FarCollB", next(i), a, w / 2, hl, cx, cy - a - w / 2, z))


def write_compact(base, out_rel, cx, cy, a, z=-26000.0, length=1000.0, geo=GEO):
    """Derive <geo>/<out_rel> from <geo>/<base> with the far collimator; returns out_rel (the COMPACT_FILE of the run).

    Raises ValueError if the jaws overlap an element of the line or the box."""
    text = open(os.path.join(geo, base)).read()
    lo, hi = z - length / 2, z + length / 2
    hit = [n for n, a_lo, a_hi in line_extents(text) if a_lo < hi and lo < a_hi]
    if hit or hi >= 0:
        raise ValueError(f"far collimator {lo:g} .. {hi:g} mm overlaps {', '.join(hit) or 'the box'}")
    depth = out_rel.count("/")   # the derived file sits deeper: its includes point back to the geometry folder
    text = re.sub(r'ref="([^"/]+\.xml)"', lambda m: f'ref="{"../" * depth}{m.group(1)}"', text)
    note = (f"  <!-- far collimator (make_run_sim_dag.py, option far-collimator): iron, half-aperture {a:g} mm, "
            f"z {lo:g} .. {hi:g} mm, centred on ({cx:.2f}, {cy:.2f}) mm -->\n")
    if "  </detectors>" not in text:
        raise ValueError(f"{base}: no </detectors>")
    text = text.replace("  </detectors>", note + jaws(cx, cy, z, a, length) + "  </detectors>", 1)
    path = os.path.join(geo, out_rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(text)
    return out_rel
