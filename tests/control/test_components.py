"""One definition per Gaudi component, and every component loadable from the installed Configurables."""
import glob
import os
import re
import subprocess
import sys

from conftest import ROOT

DECL = re.compile(r'^\s*DECLARE_COMPONENT_WITH_ID\([^,]+,\s*"([^"]+)"\)|^\s*DECLARE_COMPONENT\(\s*([\w:]+)\s*\)', re.M)


def declared():
    out = {}
    for f in glob.glob(os.path.join(ROOT, "**", "src", "*.cpp"), recursive=True):
        if "/build/" in f or "/install/" in f:
            continue
        for m in DECL.finditer(open(f).read()):
            out.setdefault(m.group(1) or m.group(2), []).append(os.path.relpath(f, ROOT))
    return out


def test_component_names_unique():
    d = declared()
    dup = {k: v for k, v in d.items() if len(v) > 1}
    assert not dup, dup
    # the shared tracking front-end: one source, a data and a simulation instantiation
    assert d["ShowerTagger"] == d["SimShowerTagger"] == ["reconstruction/tracking/src/ShowerTagger.cpp"]
    assert d["SiPadMeasConverter"] == d["SimSiPadMeasConverter"] == ["reconstruction/tracking/src/SiPadMeasConverter.cpp"]
    assert d["ACTSGeoSvc"] == ["reconstruction/tracking/src/ACTSGeoSvc.cpp"]


def test_configurables_import(k4env):
    names = sorted(declared())
    code = "import Configurables as C\n" + "".join(f"getattr(C, {n!r})\n" for n in names)
    r = subprocess.run([sys.executable, "-c", code], env=k4env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
