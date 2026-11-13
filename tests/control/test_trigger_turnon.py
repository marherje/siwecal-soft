"""TriggerTurnOnCalibrator (the Gaudi producer of the set and slab turn-ons in digi_calibration.yml) reproduces the
Python original it replaced (analysis/trigger_turnon.py + compare_shapers.data_turnon): on the first 40 acquisitions
of eudaq run 253, chunk 0, every histogram bin must be identical and the fitted mu, sigma, plateau equal within 1e-3
(the YAML keeps 0.01 in ADC); tests/control/data/turnon_reference_e253_chunk0_40acq.txt was frozen from the Python."""
import os
import subprocess

from conftest import ROOT, TB

REF = os.path.join(ROOT, "tests", "control", "data", "turnon_reference_e253_chunk0_40acq.txt")
CHUNK = os.path.join(TB, "Data", "rundata_converted_gaudi", "TB2026CERN_eudaq_run_000253", "chunks", "chunk_0000.root")
STEER = os.path.join(ROOT, "data_conversion", "options", "run_trigger_turnon.py")


def _ref():
    h, f = {}, {}
    for line in open(REF):
        t = line.split()
        if not t or t[0].startswith("#"):
            continue
        if t[0] == "h":
            h[(t[1], int(t[2]))] = (float(t[3]), float(t[4]))
        else:
            f[t[1]] = [float(x) for x in t[2:]]
    return h, f


def test_turnon_reproduces_the_python_original(k4env, eos, tmp_path):
    fill, fit = tmp_path / "e253.turnon.txt", tmp_path / "fit.txt"
    for env in ({"TURNON_MODE": "Fill", "TURNON_SET": "th210", "TURNON_INPUT_FILES": CHUNK, "TURNON_OUTPUT": str(fill)},
                {"TURNON_MODE": "Fit", "TURNON_FILL_FILES": str(fill), "TURNON_OUTPUT": str(fit)}):
        r = subprocess.run(["k4run", STEER], env=dict(k4env, **env), cwd=tmp_path, capture_output=True, text=True,
                           timeout=600)
        assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    href, fref = _ref()
    got = {}
    for line in open(fill):
        t = line.split()
        if t and not t[0].startswith("#"):
            got[(t[0], int(t[1]))] = (float(t[2]), float(t[3]))
    assert got == href
    fits = {l.split()[0]: [float(x) for x in l.split()[1:]] for l in open(fit) if not l.startswith("#")}
    assert set(fits) == set(fref)
    for name, par in fref.items():
        assert all(abs(a - b) < 1e-3 for a, b in zip(fits[name], par)), (name, fits[name], par)
