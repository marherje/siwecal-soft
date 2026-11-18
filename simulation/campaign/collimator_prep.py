#!/usr/bin/env python3
"""Aperture nodes of a run with the rectangular far collimator (make_run_sim_dag.py --rect-collimator; logic in
collimator.py). Run on HTCondor through run_collimator_prep.sh (Key4hep environment, for uproot).

Per run, under the campaign folder <out>:
  d1  free-line dummy      collimator/pass1/params/<RUN>.data.json -> collimator/pass1/params/<RUN>.json
  p2  collimator_prep.py step2: per axis jaws or not (collimator.decide), first apertures
        -> collimator/pass2/params/<RUN>.data.json, collimator/<RUN>.step2.json, geometry generated/<c>/<RUN>_pass2.xml
  d2  dummy with the jaws  collimator/pass2/params/<RUN>.data.json -> collimator/pass2/params/<RUN>.json
  p3  collimator_prep.py step3: apertures corrected on the d2 widths (collimator.correct)
        -> params/<RUN>.json (production gun, read by the chunks and the closure), collimator/<RUN>.json,
           geometry generated/<c>/<RUN>.xml (the chunks' COMPACT_FILE)
A run whose two axes stay open gets a geometry identical to the base compact (no jaws), written to the same name.

    collimator_prep.py step2 <out> <RUN> <data_valtree> <base_compact> <compact_rel>
    collimator_prep.py step3 <out> <RUN> <base_compact> <compact_rel>
"""
import json
import os
import sys

import uproot

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collimator  # noqa: E402


def spot_tails(valtree):
    a = uproot.open(valtree)["ecal"].arrays(["nhit_chan", "bar_x", "bar_y"], library="np")
    return {k: collimator.tails(a["nhit_chan"], a[f"bar_{k}"]) for k in ("x", "y")}


def write_geometry(base, rel, cx, cy, ax, ay, far, geo):
    if ax or ay:
        return collimator.write_compact(base, rel, cx, cy, ax, far["z"], far["length"], geo=geo, ay=ay)
    return collimator.write_open(base, rel, geo)   # both axes open: the base line, under the name the chunks expect


def dump(obj, path):
    tmp = path + ".tmp"
    json.dump(obj, open(tmp, "w"), indent=2)
    os.replace(tmp, path)


def step2(out, run, data_valtree, base, rel, geo=collimator.GEO):
    c = os.path.join(out, "collimator")
    dst = os.path.join(c, "pass2", "params", f"{run}.data.json")
    if os.path.exists(dst):
        print(f"{dst} exists: step2 already done")
        return
    d1 = json.load(open(os.path.join(c, "pass1", "params", f"{run}.json")))
    data, g1, far = d1["data"], d1["gun"], d1["far_collimator"]
    t_data = spot_tails(data_valtree)
    t_free = spot_tails(os.path.join(c, "pass1", "dummy", run, f"ecal_dummy_{run}.valtree.root"))
    gun0, axes = {"x": g1["x"], "y": g1["y"]}, {}
    for k in ("x", "y"):
        a, s, why = collimator.decide(data[f"w{k}"], g1[f"s{k}"], t_free[k], t_data[k])
        axes[k] = {"a_pass2": a, "why": why, "tails_data": t_data[k], "tails_free": t_free[k]}
        gun0[f"s{k}"] = s
    write_geometry(base, rel, data["x"], data["y"], axes["x"]["a_pass2"], axes["y"]["a_pass2"], far, geo)
    dump({"run": run, "axes": axes, "compact_pass2": rel, "free_gun": g1}, os.path.join(c, f"{run}.step2.json"))
    p = {k: v for k, v in d1.items() if k not in ("dummy", "gun")}
    p.update(gun0=gun0, far_collimator=far)
    dump(p, dst)
    print(json.dumps(axes, indent=1), gun0)


def step3(out, run, base, rel, geo=collimator.GEO):
    c = os.path.join(out, "collimator")
    dst = os.path.join(out, "params", f"{run}.json")
    if os.path.exists(dst):
        print(f"{dst} exists: step3 already done")
        return
    d2 = json.load(open(os.path.join(c, "pass2", "params", f"{run}.json")))
    s2 = json.load(open(os.path.join(c, f"{run}.step2.json")))
    data, dum, far = d2["data"], d2["dummy"], d2["far_collimator"]   # the tune keeps the keys it does not use
    t2 = spot_tails(os.path.join(c, "pass2", "dummy", run, f"ecal_dummy_{run}.valtree.root"))
    gun, axes = dict(d2["gun"]), s2["axes"]
    for k in ("x", "y"):
        ax = axes[k]
        ax.update(w_data=data[f"w{k}"], w_pass2=dum[f"w{k}"], tails_pass2=t2[k])
        ax["a"] = collimator.correct(ax["a_pass2"], data[f"w{k}"], dum[f"w{k}"])
        if ax["a"]:   # collimated axis: the aperture sets the width, the gun keeps the pass-2 sigma
            gun[f"s{k}"] = d2["gun0"][f"s{k}"]
    write_geometry(base, rel, data["x"], data["y"], axes["x"]["a"], axes["y"]["a"], far, geo)
    dump({"run": run, "axes": axes, "compact": rel, "gun": gun}, os.path.join(c, f"{run}.json"))
    d2.update(gun=gun, compact=rel, far_collimator=dict(far, ax=axes["x"]["a"], ay=axes["y"]["a"]))
    dump(d2, dst)
    print(json.dumps(axes, indent=1), gun)


if __name__ == "__main__":
    {"step2": step2, "step3": step3}[sys.argv[1]](*sys.argv[2:])
