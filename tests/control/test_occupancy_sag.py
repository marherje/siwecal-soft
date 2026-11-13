"""OccupancySagCalibrator (the Gaudi producer of common/mappings/occupancy_sag_<set>.txt) reproduces the Python
original it replaced (analysis/cm_sag_collect.py + sag_table.py, retired): on the first 40 acquisitions of eudaq run
291, chunk 10, the per-bin record counts must be equal and the sums equal to float precision
(tests/control/data/sag_reference_e291_chunk10_40acq.txt, frozen from the Python code). And the Table step turns
Fill outputs into a map AdcDigitizer reads (format, shape, a sag that deepens with the charge)."""
import os
import subprocess

import pytest

from conftest import ROOT, TB

REF = os.path.join(ROOT, "tests", "control", "data", "sag_reference_e291_chunk10_40acq.txt")
CHUNK = os.path.join(TB, "Data", "rundata_converted_gaudi", "TB2026CERN_eudaq_run_000291", "chunks", "chunk_0010.root")
STEER = os.path.join(ROOT, "data_conversion", "options", "run_occupancy_sag.py")


def _read_fill(path):
    out = {}
    for line in open(path):
        t = line.split()
        if not t or t[0].startswith("#") or t[0].endswith("edges"):
            continue
        out[(int(t[0]), int(t[1]))] = [float(x) for x in t[2:]]
    return out


@pytest.fixture(scope="module")
def fill(tmp_path_factory, k4env, eos):
    w = tmp_path_factory.mktemp("sag")
    env = dict(k4env, SAG_MODE="Fill", SAG_INPUT_FILES=CHUNK, SAG_OUTPUT=str(w / "e291.sagfill.txt"), SAG_MAX_ACQ="40")
    r = subprocess.run(["k4run", STEER], env=env, cwd=w, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    return w


def test_fill_reproduces_the_python_original(fill):
    ref, got = _read_fill(REF), _read_fill(str(fill / "e291.sagfill.txt"))
    assert set(ref) == set(got)
    for k, (n, sb, sqc, sqs) in ref.items():
        g = got[k]
        assert g[0] == n, k
        for a, b in zip((sb, sqc, sqs), g[1:]):
            assert abs(a - b) <= 1e-6 * max(1.0, abs(a)), (k, a, b)


def test_table_is_a_map_the_digitiser_reads(fill, k4env):
    out = fill / "occupancy_sag_check.txt"
    env = dict(k4env, SAG_MODE="Table", SAG_FILL_FILES=str(fill / "e291.sagfill.txt"), SAG_OUTPUT=str(out),
               SAG_LABEL="test")
    r = subprocess.run(["k4run", STEER], env=env, cwd=fill, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    lines = [l.split() for l in open(out) if not l.startswith("#")]
    qc, qs = [float(x) for x in lines[0][1:]], [float(x) for x in lines[1][1:]]
    rows = [[float(x) for x in l] for l in lines[2:]]
    assert lines[0][0] == "qchip" and lines[1][0] == "qslab"
    assert len(rows) == len(qc) and all(len(r) == len(qs) for r in rows)
    assert qc == sorted(qc) and qs == sorted(qs)
    assert rows[-1][-1] < rows[0][0] < 0      # the baseline sags, more under more charge
