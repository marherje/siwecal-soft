"""The results scripts read both simulation layouts: group campaigns (final_v5-v9, pid/<group>_<kind>/ and
trees/) and run-by-run campaigns (final_v10 on, <RUN>/ecal_sim_<RUN>{,_nodigi}.*), pooling the runs of a group; the
points file of a run-by-run campaign (campaign_summary.py) is a valid groups file; run_shapes.py on fake samples.
The analysis modules are imported in a subprocess from the repo root (no sys.path changes in tests)."""
import json
import os
import subprocess

import numpy as np
import pytest

from conftest import ROOT

R1, R2, R3 = "TB2026CERN_run_000056", "TB2026CERN_run_000057", "TB2026CERN_eudaq_run_000291"


def _py(code, env, **extra):
    e = dict(env, MPLCONFIGDIR=extra.pop("mpl"), **extra)
    r = subprocess.run(["python3", "-c", code], cwd=ROOT, env=e, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _valtree(path, n=3000, seed=0, shift=0.0):
    import uproot
    r = np.random.default_rng(seed)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cols = {v: r.normal(10 + shift, 2, n) for v in ("sum_energy", "e_over_nhit", "moliere", "transverse_rms", "zbary",
                                                    "shower_start", "shower_max", "shower_length", "n_layers_hit",
                                                    "mip_likeness", "fractal_dimension")}
    cols.update(nhit_chan=np.full(n, 100, np.int32), bar_x=r.normal(0, 20, n), bar_y=r.normal(0, 15, n))
    with uproot.recreate(path) as f:
        f["ecal"] = cols


@pytest.fixture
def camps(tmp_path, k4env):
    run_by_run = tmp_path / "final_vX"
    for run in (R1, R3):
        for suf in ("", "_nodigi"):
            _valtree(str(run_by_run / run / f"ecal_sim_{run}{suf}.valtree.root"))
            (run_by_run / run / f"ecal_sim_{run}{suf}.root").write_text("")
    group = tmp_path / "final_vG"
    _valtree(str(group / "pid" / "grp_digi" / "x.valtree.root"))
    (group / "trees").mkdir()
    (group / "trees" / "ecal_grp.root").write_text("")
    return tmp_path, run_by_run, group, k4env


def test_sim_lookup_both_layouts(camps):
    tmp, rbr, grp, env = camps
    code = ("import json; from analysis import final_panels as fp, final_profiles as pr; "
            f"g = {{'name': 'grp', 'runs': ['{R1}', '{R2}', '{R3}']}}; "
            "print(json.dumps({'rbr': fp.sim_valtrees(g, 'digi', sim=SIM1), 'rbr_nd': fp.sim_valtrees(g, 'nodigi', "
            "sim=SIM1), 'grp': fp.sim_valtrees(g, 'digi', sim=SIM2), 'files': pr.sim_files(g, 'nodigi')}))")
    code = code.replace("SIM1", repr(str(rbr))).replace("SIM2", repr(str(grp)))
    out = _py(code, env, mpl=str(tmp / "mpl"), FINAL_SIM=str(rbr))
    assert out["rbr"] == [f"{rbr}/{R1}/ecal_sim_{R1}.valtree.root", f"{rbr}/{R3}/ecal_sim_{R3}.valtree.root"]
    assert out["rbr_nd"][0].endswith(f"ecal_sim_{R1}_nodigi.valtree.root")
    assert out["grp"] == [f"{grp}/pid/grp_digi/x.valtree.root"]
    trees, vts = out["files"]   # final_profiles, FINAL_SIM = run-by-run: tree and valtree paired per run
    assert trees == [f"{rbr}/{r}/ecal_sim_{r}_nodigi.root" for r in (R1, R3)]
    assert vts == [f"{rbr}/{r}/ecal_sim_{r}_nodigi.valtree.root" for r in (R1, R3)]


def test_points_file_of_a_campaign_is_a_groups_file(camps):
    tmp, _, _, env = camps
    pts = tmp / "beam_points_v10.txt"
    pts.write_text("# header\n"   # campaign_summary.py format: name set label E x y sx sy runs particle
                   f"{R1:<32} th230  E5     10      -2.5   -0.5   11.0   20.0  {R1} e-\n"
                   f"{R3:<32} th210  -      20      26.0  -52.0   12.0    7.0  {R3} e-\n")
    code = f"import json; from analysis import final_panels as fp; print(json.dumps(fp.load_groups({str(pts)!r})))"
    g = _py(code, env, mpl=str(tmp / "mpl"))
    assert [x["name"] for x in g] == [R1, R3] and [x["runs"] for x in g] == [[R1], [R3]]
    assert g[1]["label"] is None and g[0]["E"] == "10"
    code = ("import json; from analysis.final_panels import _run; "
            "print(json.dumps([_run('22'), _run('e291'), _run('TB2026CERN_run_000022')]))")
    assert _py(code, env, mpl=str(tmp / "mpl")) == ["TB2026CERN_run_000022", "TB2026CERN_eudaq_run_000291",
                                                    "TB2026CERN_run_000022"]


def test_run_shapes_on_fake_samples(camps, tmp_path):
    tmp, rbr, _, env = camps
    reco = tmp / "reco"
    _valtree(str(reco / R1 / f"ecal_{R1}.valtree.root"), n=20000, seed=7)
    (tmp / "runs.txt").write_text(f"{R1} th230 E5 10 e-\n{R2} th230 E5 7.5 e-\n")
    out = tmp / "rs.tsv"
    cmd = ["python3", "analysis/run_shapes.py", str(rbr), "--runs", str(tmp / "runs.txt"), "--out", str(out)]
    e = dict(env, MPLCONFIGDIR=str(tmp / "mpl"), FINAL_RECO=str(reco))
    r = subprocess.run(cmd, cwd=ROOT, env=e, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"{R2}: missing (no simulation)" in r.stdout
    rows = [line.split("\t") for line in out.read_text().splitlines()]
    head, sim = rows[0], next(x for x in rows if x[2] == "sim")
    col = dict(zip(head, sim))
    assert abs(float(col["rwx"]) - 1) < 0.05 and abs(float(col["moliere_shift"])) < 0.05
    assert float(col["moliere_ks"]) < 0.05
    # never overwrites
    r = subprocess.run(cmd, cwd=ROOT, env=e, capture_output=True, text=True, timeout=300)
    assert r.returncode != 0 and "exists" in r.stderr
