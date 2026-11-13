"""The pad maps sit on the pad grid of the DD4hep geometry: regenerating them from the .nominal maps and
simulation/geometry/SND_compact.xml moves no pad (common/mappings/regenerate_pad_maps.py --dry-run)."""
import os
import re
import subprocess
import sys

from conftest import ROOT


def test_pad_maps_match_the_simulated_geometry(k4env):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "common", "mappings", "regenerate_pad_maps.py"), "--dry-run"],
                       env=k4env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    moves = re.findall(r"(\S+\.txt): (\d+) pads, largest move ([\d.]+) mm", r.stdout)
    assert len(moves) == 2, r.stdout
    for name, n, move in moves:
        assert int(n) == 1024 and float(move) == 0.0, (name, n, move)
