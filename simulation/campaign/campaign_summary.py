#!/usr/bin/env python3
"""Summary of a run-by-run simulation campaign (last node of make_run_sim_dag.py). Bookkeeping only: every number
comes from the JSON files siwecal_beamspot wrote.

    python3 simulation/campaign/campaign_summary.py <campaign_dir> <runs_file>

  <campaign_dir>/closure.tsv          one row per run of <runs_file>: data spot, tuned gun, simulated spot, closure;
                                      last column ok / FLAG (|shift| > 1 mm or |width| off by > 5 %) / missing
  <campaign_dir>/beam_points_v10.txt  the tuned guns in the beam_points.txt format (one point per run), so the
                                      analysis reads the campaign with FINAL_GROUPS=<this file>
"""
import json
import os
import sys

from make_run_list import read_runs


def _load(path):
    return json.load(open(path)) if os.path.exists(path) else None


def _f(v, fmt="{:.2f}"):
    return "nan" if v is None else fmt.format(v)


def summary(campaign_dir, runs):
    head = ["RUN", "E", "data_x", "data_y", "data_wx", "data_wy", "data_n", "gun_x", "gun_y", "gun_sx", "gun_sy",
            "sim_x", "sim_y", "sim_wx", "sim_wy", "dx", "dy", "rwx", "rwy", "status"]
    rows, points = ["# " + "\t".join(head)], []
    for r in runs:
        p = _load(os.path.join(campaign_dir, "params", f"{r['run']}.json")) or {}
        c = _load(os.path.join(campaign_dir, "closure", f"{r['run']}.json"))
        d, g, s = p.get("data", {}), p.get("gun", {}), (c or {}).get("sim", {})
        status = "missing" if c is None else ("FLAG" if c["flag"] else "ok")
        row = [r["run"], r["E"]] + [_f(d.get(k)) for k in ("x", "y", "wx", "wy")] + [str(d.get("n", "nan"))]
        row += [_f(g.get(k)) for k in ("x", "y", "sx", "sy")] + [_f(s.get(k)) for k in ("x", "y", "wx", "wy")]
        row += [_f((c or {}).get(k), "{:.3f}") for k in ("dx", "dy", "rwx", "rwy")] + [status]
        rows.append("\t".join(row))
        if g:
            gun = [_f(g[k], "{:.1f}") for k in ("x", "y", "sx", "sy")]
            points.append(f"{r['run']:<32} {r['set']:<6} {r['label']:<6} {r['E']:<5} " + " ".join(f"{v:>6}" for v in gun)
                          + f"  {r['run']} {r['particle']}")
    open(os.path.join(campaign_dir, "closure.tsv"), "w").write("\n".join(rows) + "\n")
    header = ("# Beam points of a run-by-run simulation campaign (one per data run), written by campaign_summary.py:\n"
              "# name set label E x y sx sy runs particle; x y sx sy = tuned gun [mm] (params/<RUN>.json).\n")
    open(os.path.join(campaign_dir, "beam_points_v10.txt"), "w").write(header + "\n".join(points) + "\n")
    flagged = sum(row.endswith("\tFLAG") for row in rows)
    missing = sum(row.endswith("\tmissing") for row in rows)
    print(f"{len(runs)} runs: {flagged} flagged, {missing} missing -> {campaign_dir}/closure.tsv")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    summary(sys.argv[1], read_runs(sys.argv[2]))
