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

Rectangular aperture per run and per axis (--rect-collimator 7.5,10; collimator tests 2026-11-16): a fixed square
hole leaves the spot too wide in y and too narrow in x, as in H2 the horizontal and vertical collimators are set
independently. For the runs of those energies, after a free-line dummy each axis gets jaws only where the free line
cannot reproduce the data (decide), a dummy with those jaws follows, and the apertures are corrected on its widths
(correct). Nodes: collimator_prep.py.
"""
import math
import os
import re
import xml.etree.ElementTree as ET

GEO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "geometry")
UNITS = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "um": 1e-3}
JAW_W = 100.0            # jaw thickness across the beam [mm]
IDS = (190, 191, 192, 193)   # detector ids of the jaws L, R, T, B (the line uses 100-157)
OPEN_SPAN = 300.0        # half-span across the beam of a jaw pair whose other axis is open [mm]
SQUARE = object()        # write_compact default: same aperture on both axes


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


def jaws(cx, cy, z, ax, ay, length):
    """Iron jaws around a rectangular hole of half-sides ax, ay centred on (cx, cy), from z - length/2 to
    z + length/2: left/right jaws if ax, top/bottom jaws if ay (None: that axis is open). With both, the left/right
    jaws close the corners; with one pair only, it spans OPEN_SPAN across the beam."""
    hl, w = length / 2, JAW_W
    out = ""
    if ax:
        out += (_box("H2_FarCollL", IDS[0], w / 2, (ay or OPEN_SPAN) + w, hl, cx - ax - w / 2, cy, z)
                + _box("H2_FarCollR", IDS[1], w / 2, (ay or OPEN_SPAN) + w, hl, cx + ax + w / 2, cy, z))
    if ay:
        out += (_box("H2_FarCollT", IDS[2], ax or OPEN_SPAN, w / 2, hl, cx, cy + ay + w / 2, z)
                + _box("H2_FarCollB", IDS[3], ax or OPEN_SPAN, w / 2, hl, cx, cy - ay - w / 2, z))
    return out


def write_compact(base, out_rel, cx, cy, a, z=-26000.0, length=1000.0, geo=GEO, ay=SQUARE):
    """Derive <geo>/<out_rel> from <geo>/<base> with the far collimator; returns out_rel (the COMPACT_FILE of the run).
    a is the half-aperture in x, and in y too unless ay is given (rectangular hole; None = that axis open).

    Raises ValueError if the jaws overlap an element of the line or the box, or if both axes are open."""
    ax, ay = a, (a if ay is SQUARE else ay)
    if not ax and not ay:
        raise ValueError("far collimator: both axes open, use the base compact")
    text = open(os.path.join(geo, base)).read()
    lo, hi = z - length / 2, z + length / 2
    hit = [n for n, a_lo, a_hi in line_extents(text) if a_lo < hi and lo < a_hi]
    if hit or hi >= 0:
        raise ValueError(f"far collimator {lo:g} .. {hi:g} mm overlaps {', '.join(hit) or 'the box'}")
    depth = out_rel.count("/")   # the derived file sits deeper: its includes point back to the geometry folder
    text = re.sub(r'ref="([^"/]+\.xml)"', lambda m: f'ref="{"../" * depth}{m.group(1)}"', text)
    fmt = lambda v: f"{v:.2f} mm" if v else "open"   # noqa: E731
    ap = f"{ax:g} mm" if ax == ay else f"x {fmt(ax)}, y {fmt(ay)}"
    note = (f"  <!-- far collimator (make_run_sim_dag.py, option far-collimator): iron, half-aperture {ap}, "
            f"z {lo:g} .. {hi:g} mm, centred on ({cx:.2f}, {cy:.2f}) mm -->\n")
    if "  </detectors>" not in text:
        raise ValueError(f"{base}: no </detectors>")
    text = text.replace("  </detectors>", note + jaws(cx, cy, z, ax, ay, length) + "  </detectors>", 1)
    path = os.path.join(geo, out_rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(text)
    return out_rel


# ---- per-run rectangular aperture (make_run_sim_dag.py --rect-collimator; node script collimator_prep.py) ----
# Two knobs per axis: the gun sigma (core width) and the jaws (truncated tails, or a width the free line alone already
# exceeds). Values from the collimator tests (2026-11-16, work/beam_collimator/make_rect.py).
FLOOR_FRAC = 0.35   # free-line tune below FLOOR_FRAC x data width: the line alone is (nearly) too wide -> jaws
DTAIL = 0.10        # free-line tails wider than the data's by more than this -> jaws
R0 = 0.88           # first aperture a = w_data / R0 (w_sim / a ~ 0.88 at a = 25 mm, 7.5-10 GeV)
SLOPE = 0.45        # d(width)/d(aperture) of a collimated axis
STEP_MAX = 6.0      # largest aperture correction [mm]


def tails(nhit, v):
    """(p95 - p5) / IQR of v over the shower-like events (nhit > 0.5 x p90 of nhit): 2.44 for a gaussian."""
    import numpy as np
    nhit, v = np.asarray(nhit), np.asarray(v)
    m = (nhit > 0.5 * np.percentile(nhit, 90)) & np.isfinite(v)
    q = np.percentile(v[m], [5, 25, 75, 95])
    return float((q[3] - q[0]) / (q[2] - q[1]))


def decide(w_data, s_free, t_free, t_data):
    """One axis after the free-line dummy: (half-aperture or None, gun sigma, reason).

    w_data: data width; s_free: gun sigma tuned on the free line; t_free, t_data: tails of the free-line dummy and of
    the data. Jaws if the tune hits the floor (s_free < FLOOR_FRAC w_data) or the free line has wider tails; then
    a = w_data / R0 and the gun keeps the data width (the aperture sets the spot), else no jaws and the tuned gun."""
    floor, wide = s_free < FLOOR_FRAC * w_data, t_free - t_data > DTAIL
    if not (floor or wide):
        return None, s_free, "open"
    return w_data / R0, w_data, " ".join(s for s, c in (("gun floor", floor), ("tails", wide)) if c)


def correct(a, w_data, w_dummy):
    """Half-aperture after the dummy with the jaws: move the width by SLOPE per mm (step clamped to STEP_MAX, the
    aperture to at least half the data width); None stays None."""
    if not a:
        return a
    step = max(-STEP_MAX, min(STEP_MAX, (w_data - w_dummy) / SLOPE))
    return max(0.5 * w_data, a + step)
