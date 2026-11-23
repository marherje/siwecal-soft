#!/usr/bin/env python3
"""The H2-like line with the ECAL turned about the vertical axis (y), for the angular-scan simulation
(launch_angle_scan.sh). Writes, under simulation/geometry/generated/<campaign>/ (git-ignored):

  SiPadDetector_beamline_roty<A>.xml  SiPadDetector_beamline.xml with the envelope rotation y = <A>*deg
                                      (xml::createPlacedEnvelope: the box turns about its own centre, z = Ecal_z_position)
  SND_compact_beamline_roty<A>.xml    SND_compact_beamline.xml including it, its other includes pointing back up

and prints the compact's path relative to simulation/geometry (the COMPACT_FILE / --compact of make_run_sim_dag.py).
The turned detector is included as "./<file>" so that collimator.write_compact, which relocates bare names, keeps it
when it derives the far-collimator compact of a run in the same folder.

    python3 simulation/campaign/angle_geometry.py <campaign> <angle_deg>
"""
import os
import re
import sys

import collimator

BASE, DET = "SND_compact_beamline.xml", "SiPadDetector_beamline.xml"


def tag(angle):
    return "roty" + f"{angle:g}".replace("-", "m").replace(".", "p")


def write(campaign, angle, base=BASE, det=DET, geo=collimator.GEO):
    """Writes the two files; returns the compact's path relative to geo."""
    folder = os.path.join("generated", campaign)
    det_rel = os.path.join(folder, f"{os.path.splitext(det)[0]}_{tag(angle)}.xml")
    compact_rel = os.path.join(folder, f"{os.path.splitext(base)[0]}_{tag(angle)}.xml")
    text, n = re.subn(r'(<envelope\b.*?<rotation\s+x="0"\s+)y="0"', rf'\1y="{angle:g}*deg"',
                      open(os.path.join(geo, det)).read(), count=1, flags=re.S)
    if n != 1:
        raise ValueError(f"no envelope rotation y=\"0\" in {det}")
    if re.search(r'\bref="', text):
        raise ValueError(f"{det} includes other files: they would need relocating")
    text = text.replace("<envelope", f"<!-- angle_geometry.py: ECAL turned by {angle:g} deg about y -->\n  <envelope", 1)
    compact = collimator.relocate(open(os.path.join(geo, base)).read(), compact_rel)
    up = "../" * compact_rel.count("/")
    compact, n = re.subn(rf'ref="{re.escape(up + det)}"', f'ref="./{os.path.basename(det_rel)}"', compact)
    if n != 1:
        raise ValueError(f"{base} does not include {det} exactly once")
    os.makedirs(os.path.join(geo, folder), exist_ok=True)
    for rel, t in ((det_rel, text), (compact_rel, compact)):
        open(os.path.join(geo, rel), "w").write(t)
    return compact_rel


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(write(sys.argv[1], float(sys.argv[2])))
