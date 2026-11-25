#!/usr/bin/env python
"""
Per-run comparison of a run-by-run simulation campaign (final_v10 on) with the data: beam spot and shower shapes,
run by run, digitised simulation against the run's data valtree, optionally next to a reference campaign.

    python analysis/run_shapes.py <campaign_dir> [--ref <campaign_dir>] [--runs <runs file>] [--only RUN,...]
        [--out <file.tsv>]

Selection as final_panels.py (shower-like events, nhit_chan > 0.5 x p90 of each sample). Per run and sample:
  spot     width ratio sim / data (IQR / 1.349) and tails (p95 - p5) / IQR of the barycentre, per axis (2.44 gaussian)
  shapes   per variable shift = (mean_sim - mean_data) / std_data and the Kolmogorov-Smirnov distance;
           flagged when |shift| > 0.10 or KS > 0.10
Writes one row per run and sample to --out (default <campaign_dir>/run_shapes.tsv; refuses to overwrite) and prints
the table and, per beam energy, the median |shift| of each variable. Runs without a simulated sample are listed as
missing. Reads every data valtree of the selected runs: for the whole campaign run it on HTCondor or with --only.
"""
import argparse
import os
import sys

import numpy as np
import uproot

from analysis.final_panels import GROUPS_FILE, RECO, load_groups, sim_valtrees, showerlike  # noqa: E402
from siwecal_common import paths  # noqa: E402

VARS = ["nhit_chan", "sum_energy", "e_over_nhit", "moliere", "transverse_rms", "zbary", "shower_start", "shower_max",
        "shower_length", "n_layers_hit", "mip_likeness", "fractal_dimension"]
SHORT = {"nhit_chan": "nhit", "sum_energy": "E_MIP", "e_over_nhit": "E_hit", "moliere": "R90",
         "transverse_rms": "rmsT", "zbary": "zbary", "shower_start": "start", "shower_max": "max",
         "shower_length": "length", "n_layers_hit": "layers", "mip_likeness": "mipL", "fractal_dimension": "fractal"}
FLAG = 0.10


def read_runs(path):
    """RUN set label E particle per line of a run list (simulation/campaign/runs_v10.txt)."""
    out = []
    for line in open(path):
        f = line.split("#")[0].split()
        if len(f) >= 4:
            out.append({"run": f[0], "set": f[1], "label": f[2], "E": f[3]})
    return out


def load(files):
    cols = {b: [] for b in VARS + ["bar_x", "bar_y"]}
    for p in files:
        for a in uproot.iterate(f"{p}:ecal", list(cols), step_size="400 MB", library="np"):
            for b in cols:
                cols[b].append(a[b])
    c = {b: np.concatenate(v).astype(float) for b, v in cols.items()}
    k = showerlike(c["nhit_chan"])
    return {b: v[k] for b, v in c.items()}


def spot(v):
    v = v[np.isfinite(v)]
    q = np.percentile(v, [5, 25, 75, 95])
    return (q[2] - q[1]) / 1.349, (q[3] - q[0]) / (q[2] - q[1])


def ks(a, b):
    a, b = np.sort(a[np.isfinite(a)]), np.sort(b[np.isfinite(b)])
    if not len(a) or not len(b):
        return float("nan")
    x = np.concatenate([a, b])
    return float(np.max(np.abs(np.searchsorted(a, x, "right") / len(a) - np.searchsorted(b, x, "right") / len(b))))


def shift(d, s):
    d, s = d[np.isfinite(d)], s[np.isfinite(s)]
    return float((s.mean() - d.mean()) / d.std()) if len(d) and len(s) and d.std() > 0 else float("nan")


def compare(d, s):
    """Row of one simulated sample against its data: spot (width ratios, tails) and per variable shift and KS."""
    dx, dy, sx, sy = spot(d["bar_x"]), spot(d["bar_y"]), spot(s["bar_x"]), spot(s["bar_y"])
    row = {"n": len(s["nhit_chan"]), "rwx": sx[0] / dx[0], "rwy": sy[0] / dy[0], "tx": sx[1], "ty": sy[1]}
    for v in VARS:
        row[f"{v}_shift"], row[f"{v}_ks"] = shift(d[v], s[v]), ks(d[v], s[v])
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("campaign")
    ap.add_argument("--ref", default=None, help="reference campaign shown next to it (e.g. the previous one); a group "
                    "campaign (final_v5-v9) contributes the sample of the run's group of --ref-groups")
    ap.add_argument("--ref-groups", default=GROUPS_FILE)
    ap.add_argument("--runs", default=paths.repo_path("simulation", "campaign", "runs_v10.txt"))
    ap.add_argument("--only", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = a.out or os.path.join(a.campaign, "run_shapes.tsv")
    if os.path.exists(out):
        sys.exit(f"{out} exists: choose another --out")
    only = set(a.only.split(",")) if a.only else None
    samples = [("sim", a.campaign)] + ([("ref", a.ref)] if a.ref else [])
    group_of = {r: g for g in load_groups(a.ref_groups) for r in g["runs"]} if a.ref else {}
    head = ["run", "E", "sample", "n", "rwx", "rwy", "tx", "ty"] + [f"{v}_{m}" for v in VARS for m in ("shift", "ks")]
    rows, per_e = [], {}
    print(f"shift = (mean_sim - mean_data)/std_data, ks = KS distance; * = |shift| > {FLAG} or ks > {FLAG}")
    for r in read_runs(a.runs):
        run = r["run"]
        if only and run not in only:
            continue
        sims = {k: sim_valtrees({"name": run, "runs": [run]}, "digi", sim=c) for k, c in samples}
        if a.ref and not sims["ref"] and run in group_of:   # group campaign: the sample of the run's group
            sims["ref"] = sim_valtrees(group_of[run], "digi", sim=a.ref)[:1]
        dpath = f"{RECO}/{run}/ecal_{run}.valtree.root"
        if not sims["sim"] or not os.path.exists(dpath):
            print(f"{run}: missing ({'no simulation' if not sims['sim'] else 'no data'})")
            continue
        d = load([dpath])
        dx, dy = spot(d["bar_x"]), spot(d["bar_y"])
        print(f"\n{run}  {r['E']} GeV  data n {len(d['nhit_chan'])}  tails {dx[1]:.2f}/{dy[1]:.2f}")
        rows.append([run, r["E"], "data", str(len(d["nhit_chan"])), "1", "1", f"{dx[1]:.3f}", f"{dy[1]:.3f}"]
                    + ["0", "0"] * len(VARS))
        for k, files in sims.items():
            if not files:
                continue
            row = compare(d, load(files))
            cells = "".join(f" {SHORT[v]} {row[f'{v}_shift']:+.2f}/{row[f'{v}_ks']:.2f}"
                            + ("*" if abs(row[f"{v}_shift"]) > FLAG or row[f"{v}_ks"] > FLAG else "") for v in VARS)
            print(f"  {k:4s} n {row['n']:6d}  width {row['rwx']:.2f}/{row['rwy']:.2f}  tails {row['tx']:.2f}/"
                  f"{row['ty']:.2f} |{cells}")
            rows.append([run, r["E"], k] + [f"{row[h]:.4g}" if h != "n" else str(row[h]) for h in head[3:]])
            per_e.setdefault((r["E"], k), []).append(row)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    open(out, "w").write("\t".join(head) + "\n" + "\n".join("\t".join(x) for x in rows) + "\n")
    print(f"\nmedian |shift| per energy ({out})")
    print(f"{'E':>5} {'sample':6} {'runs':>4}  {'width x/y':>11} " + " ".join(f"{SHORT[v]:>7}" for v in VARS))
    for (e, k), rs in sorted(per_e.items(), key=lambda t: (float(t[0][0]), t[0][1])):
        med = lambda key: float(np.median([x[key] for x in rs]))   # noqa: E731
        print(f"{e:>5} {k:6} {len(rs):4d}  {med('rwx'):5.2f}/{med('rwy'):4.2f} "
              + " ".join(f"{float(np.median([abs(x[f'{v}_shift']) for x in rs])):7.2f}" for v in VARS))


if __name__ == "__main__":
    main()
