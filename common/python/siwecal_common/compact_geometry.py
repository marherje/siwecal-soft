"""What a DD4hep compact of simulation/geometry/ says about the ECAL, read from its XML (no DD4hep needed)."""
import os
import re

import numpy as np

from siwecal_common import paths

GEO = os.path.join(paths.REPO_ROOT, "simulation", "geometry")


def layer_depths(compact="SND_compact_beamline.xml", geo=GEO, detector="SiPad"):
    """Depth [mm] of the sensitive slice of each layer in the ECAL frame (from the box centre, along the beam), read with
    DD4hep from the untilted geometry; needs Key4hep. Layer 0 is at -107.95 mm in SND_compact_beamline.xml."""
    import dd4hep
    path = compact if os.path.isabs(compact) else os.path.join(geo, compact)
    desc = dd4hep.Detector.getInstance()
    desc.fromXML("file:" + path)
    centre = desc.constantAsDouble("Ecal_z_position")

    def sensitive(v):
        return dd4hep.Volume(v).isSensitive() or any(sensitive(v.GetNode(i).GetVolume()) for i in range(v.GetNdaughters()))

    depth = {}
    for _, layer in desc.detector(detector).children():
        for _, s in layer.children():
            if sensitive(s.placement().GetVolume()):
                depth[layer.id()] = (s.nominal().worldTransformation().GetTranslation()[2] - centre) / dd4hep.mm
    return [depth[i] for i in sorted(depth)]


def lab_x(x_ecal, layer, turn_deg, depths):
    """Lab x of the beam that reaches x_ecal (ECAL frame) at the depth of layer (a float: the shower barycentre zbary),
    ECAL turned by turn_deg about y around its centre: x_lab = cos(turn) x_ecal + sin(turn) depth."""
    import math
    z = float(np.interp(layer, range(len(depths)), depths))
    t = math.radians(turn_deg)
    return math.cos(t) * x_ecal + math.sin(t) * z


def ecal_turn_deg(compact, geo=GEO):
    """Turn of the ECAL about y [deg] in a compact (path, or relative to simulation/geometry): the envelope rotation of
    the SiPadDetector file it includes (simulation/campaign/angle_geometry.py). 0 for every other geometry."""
    path = compact if os.path.isabs(compact) else os.path.join(geo, compact)
    refs = [r for r in re.findall(r'<include\s+ref="([^"]+)"', re.sub(r"<!--.*?-->", "", open(path).read(), flags=re.S))
            if os.path.basename(r).startswith("SiPadDetector")]
    if not refs:
        return 0.0
    if len(refs) > 1:
        raise ValueError(f"{compact} includes several SiPadDetector files: {refs}")
    det = os.path.normpath(os.path.join(os.path.dirname(path), refs[0]))
    text = re.sub(r"<!--.*?-->", "", open(det).read(), flags=re.S)
    m = re.search(r"<envelope\b.*?<rotation\s+([^>]*)/>.*?</envelope>", text, re.S)
    if not m:
        return 0.0
    rot = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
    val = {}
    for k in "xyz":
        v = rot.get(k, "0").strip()
        a = re.fullmatch(r"([-+0-9.eE]+)\*deg", v)
        val[k] = float(a.group(1)) if a else None if float(v) else 0.0
    if val["x"] != 0 or val["z"] != 0 or val["y"] is None:
        raise ValueError(f"{det}: envelope rotation {rot}, only a turn about y in degrees is supported")
    return val["y"]
