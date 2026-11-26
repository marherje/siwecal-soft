#!/usr/bin/env python3
"""Write (and with --submit, submit) the HTCondor DAG of a run-by-run simulation campaign: one simulated sample per
data run of the run list, with the beam and the statistics of that run.

Per run (design: docs/sim/run_by_run_simulation.md):
  here   siwecal_beamspot measure on the data valtree (Reconstruction/<RUN>/ecal_<RUN>.valtree.root): shower-like
         centre, width and count -> params/<RUN>.data.json with the initial gun and the number of chunks
  d_RUN  run_sim_dummy.sh: short simulation with the initial gun, measured and tuned -> params/<RUN>.json
  c_RUN  run_sim_chunk.sh x n_chunks: production with the tuned gun (n_events = data shower-like events rounded up
         to whole chunks)
  g_RUN  run_sim_group.sh: hadd, PID + valtree (digi and nodigi) -> <RUN>/ecal_sim_<RUN>{,_nodigi}.*, closure
  summary (after every run) campaign_summary.py -> closure.tsv, beam_points_v10.txt

    python3 simulation/campaign/make_run_sim_dag.py --campaign final_v10             # writes work/condor_final_v10/
    python3 simulation/campaign/make_run_sim_dag.py --campaign final_v10 --submit    # ... and condor_submit_dag
    python3 simulation/campaign/make_run_sim_dag.py --campaign test_v10 --out <dir> --only <RUN> \\
        --dummy-events 500 --max-events 1000 --chunk-events 500                      # small test
    python3 simulation/campaign/make_run_sim_dag.py --campaign final_v11 --far-collimator 7.5=23
        # iron collimator 26 m upstream, half-aperture 23 mm, only in the 7.5 GeV runs (see collimator.py);
        # those runs simulate n_data / --far-collimator-transmission events and a larger dummy
    python3 simulation/campaign/make_run_sim_dag.py --campaign final_v11 --rect-collimator 7.5,10
        # the 7.5 and 10 GeV runs: rectangular aperture per run and per axis, decided at run time
        # (d1 free-line dummy -> p2 -> d2 dummy with jaws -> p3 -> chunks; collimator.py, collimator_prep.py)

Runs shorter than --min-events (default 5000 events in the data valtree) are skipped. Without --submit nothing
is written on EOS: the data parameters go to <dag-dir>/params/ and are copied to
<out>/params/ at submission. Finished nodes are written as DONE, so re-running after a failure resubmits only what is
missing. Geometry/physics/digitiser as make_sim_dag.py.
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys

from siwecal_common import paths
from siwecal_common.compact_geometry import ecal_turn_deg, lab_x, layer_depths
from make_run_list import read_runs
from make_sim_dag import eos_mkdir
import collimator

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SIM = paths.simulation_dir()


def measure(valtree, out_json):
    """siwecal_beamspot measure -> the spot dict (C++: siwecal/BeamSpot.h)."""
    subprocess.run(["siwecal_beamspot", "measure", valtree, out_json], check=True)
    return json.load(open(out_json))


def shower_zbary(valtree):
    """Median zbary (layer units) of the shower-like events (nhit > 0.5 p90, as siwecal_beamspot measure)."""
    import numpy as np
    import uproot
    a = uproot.open(valtree)["ecal"].arrays(["nhit_chan", "zbary"], library="np")
    k = (a["nhit_chan"] > 0.5 * np.percentile(a["nhit_chan"], 90)) & np.isfinite(a["zbary"])
    return float(np.median(a["zbary"][k]))


def group_disk_mb(n_events):
    """Local disk of the group node [MB]: the hadd'ed trees and PID outputs of both samples (final_v9: ~88 kB per
    simulated event for all of them), with margin; at least 20 GB."""
    return max(20000, -(-n_events * 15 // 100))


def write_sub(path, executable, arguments, env, dag_dir, log, flavour, transfer=True, disk="20 GB"):
    lines = [f"universe                = vanilla",
             f"executable              = {executable}",
             f"arguments               = {arguments}",
             f'environment             = "{env}"' if env else None,
             f"log                     = {dag_dir}/logs/dag.log",
             f"output                  = {dag_dir}/logs/{log}.out",
             f"error                   = {dag_dir}/logs/{log}.err",
             "request_cpus            = 1",
             "request_memory          = 4 GB",
             f"request_disk            = {disk}",
             f"should_transfer_files   = {'YES' if transfer else 'NO'}",
             "when_to_transfer_output = ON_EXIT" if transfer else None,
             'transfer_output_files   = ""' if transfer else None,
             f'+JobFlavour             = "{flavour}"',
             "queue"]
    open(path, "w").write("\n".join(line for line in lines if line) + "\n")


RECT_DIRS = ("collimator", "collimator/pass1", "collimator/pass1/params", "collimator/pass1/dummy",
             "collimator/pass2", "collimator/pass2/params", "collimator/pass2/dummy")


def rect_nodes(run, out, sub, seed, flavour, n_dummy, valtree, base, campaign, all_done):
    """d1 (free-line dummy) -> p2 (jaws per axis) -> d2 (dummy with jaws) -> p3 (apertures corrected, production
    params and geometry) for a run with the rectangular collimator (collimator_prep.py). DONE from their outputs."""
    c = os.path.join(out, "collimator")
    gen = f"generated/{campaign}/{run}"
    exists = lambda *p: all_done or os.path.exists(os.path.join(*p))   # noqa: E731
    nodes = [
        ("d1", sub["dummy"], exists(c, "pass1", "params", f"{run}.json"),
         f'SEED="{seed + 997}" CAMP="{c}/pass1" COMPACT="{base}" NDUMMY="{n_dummy}" FLAVOUR="{flavour}"'),
        ("p2", sub["prep"], exists(c, "pass2", "params", f"{run}.data.json"),
         f'ARGS="step2 {out} {run} {valtree} {base} {gen}_pass2.xml"'),
        ("d2", sub["dummy"], exists(c, "pass2", "params", f"{run}.json"),
         f'SEED="{seed + 998}" CAMP="{c}/pass2" COMPACT="{gen}_pass2.xml" NDUMMY="{n_dummy}" FLAVOUR="{flavour}"'),
        ("p3", sub["prep"], exists(out, "params", f"{run}.json"), f'ARGS="step3 {out} {run} {base} {gen}.xml"')]
    lines = []
    for n, s, done, var in nodes:
        lines += [f"JOB {n}_{run} {s}" + (" DONE" if done else ""), f'VARS {n}_{run} RUN="{run}" NAME="{n}_{run}" {var}',
                  f"RETRY {n}_{run} 2"]
    lines += [f"PARENT {a}_{run} CHILD {b}_{run}" for a, b in (("d1", "p2"), ("p2", "d2"), ("d2", "p3"))]
    return lines


def prepare_output(out, dag_dir, made, rect_runs):
    """Campaign folders on EOS and the data parameters of each run (new files only: existing ones are kept); a run
    with the rectangular collimator also gets them as the input of its free-line dummy (collimator/pass1)."""
    dirs = ["", "params", "dummy", "chunks", "closure"] + (list(RECT_DIRS) if rect_runs else [])
    for d in dirs:
        eos_mkdir(os.path.join(out, d) if d else out)
    for run in made:
        src = os.path.join(dag_dir, "params", f"{run}.data.json")
        for dst in [os.path.join(out, "params", f"{run}.data.json")] + (
                [os.path.join(out, "collimator", "pass1", "params", f"{run}.data.json")] if run in rect_runs else []):
            if not os.path.exists(dst):
                shutil.copy(src, dst)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--campaign", required=True, help="output Processed/<campaign> (never an existing campaign)")
    ap.add_argument("--runs", default=os.path.join(HERE, "runs_v10.txt"))
    ap.add_argument("--only", default=None, help="comma-separated RUN names")
    ap.add_argument("--out", default=None, help="EOS output base (default Simulation/Processed/<campaign>)")
    ap.add_argument("--dag-dir", default=None, help="DAG, submit files, logs (default work/condor_<campaign>)")
    ap.add_argument("--data-reco", default=None, help="data area with <RUN>/ecal_<RUN>.valtree.root "
                                                      "(default: Reconstruction)")
    ap.add_argument("--dummy-events", type=int, default=3000)
    ap.add_argument("--chunk-events", type=int, default=2000)
    ap.add_argument("--max-events", type=int, default=None, help="cap the production per run (tests)")
    ap.add_argument("--min-events", type=int, default=5000,
                    help="skip runs whose data valtree has fewer events (extremely short runs)")
    ap.add_argument("--seed-offset", type=int, default=20000000)
    ap.add_argument("--sigma-e", default="0.02")
    ap.add_argument("--compact", default="SND_compact_beamline.xml")
    ap.add_argument("--beam-z", type=float, default=-65500.0)
    ap.add_argument("--far-collimator", default="",
                    help="half-aperture [mm] per beam energy of an iron collimator in the far line, e.g. 7.5=23 "
                         "(runs of any other energy: none); default: no collimator")
    ap.add_argument("--far-collimator-z", type=float, default=-26000.0, help="its centre [mm from the box front]")
    ap.add_argument("--far-collimator-length", type=float, default=1000.0, help="its length along the beam [mm]")
    ap.add_argument("--far-collimator-transmission", type=float, default=0.4,
                    help="fraction of the simulated events left shower-like behind the jaws: a collimated run "
                         "simulates n_data / transmission events (collimator tests: 0.40-0.44 at 7.5 GeV, a = 25 mm)")
    ap.add_argument("--far-collimator-dummy-events", type=int, default=6000,
                    help="dummy events of a collimated run (the jaws stop most of them)")
    ap.add_argument("--rect-collimator", default="",
                    help="beam energies [GeV] whose runs get the far collimator with a rectangular aperture tuned per "
                         "run and per axis (free-line dummy, jaws where needed, dummy with jaws, aperture "
                         "correction; collimator.py), e.g. 7.5,10")
    ap.add_argument("--no-summary", action="store_true",
                    help="no summary node (a second DAG writing into a campaign whose first DAG makes the summary)")
    ap.add_argument("--submit", action="store_true")
    args = ap.parse_args()
    try:
        coll = collimator.parse_spec(args.far_collimator)
        rect = [float(e) for e in args.rect_collimator.split(",") if e.strip()]
    except ValueError as e:
        ap.error(str(e))
    if not 0 < args.far_collimator_transmission <= 1:
        ap.error("--far-collimator-transmission must be in (0, 1]")
    if any(collimator.aperture(coll, e) is not None for e in rect):
        ap.error("an energy is in both --far-collimator and --rect-collimator")

    out = args.out or os.path.join(SIM, "Processed", args.campaign)
    dag_dir = os.path.abspath(args.dag_dir or os.path.join(REPO, "work", f"condor_{args.campaign}"))
    reco = args.data_reco or paths.reconstruction_dir()
    for d in ("logs", "params"):
        os.makedirs(os.path.join(dag_dir, d), exist_ok=True)
    runs = read_runs(args.runs)
    only = set(args.only.split(",")) if args.only else None

    env = (f"COMPACT_FILE=$(COMPACT) BEAM_Z_MM={args.beam_z:g} PHYSICS_LIST=QGSP_BERT_EMZ RECO_TABLE=th210 "
           f"SIGMA_E={args.sigma_e}")
    sub = {k: os.path.join(dag_dir, f"{k}.sub") for k in ("dummy", "chunk", "group", "summary", "prep")}
    write_sub(sub["dummy"], f"{HERE}/run_sim_dummy.sh", f"{REPO} $(CAMP) $(RUN) $(SEED) $(NDUMMY)", env,
              dag_dir, "$(NAME)", "$(FLAVOUR)")
    write_sub(sub["prep"], f"{HERE}/run_collimator_prep.sh", f"{REPO} $(ARGS)", None, dag_dir, "$(NAME)",
              "microcentury", transfer=False)
    write_sub(sub["chunk"], f"{HERE}/run_sim_chunk.sh", f"{REPO} {out} $(RUN) $(K) $(SEED) $(CH)", env,
              dag_dir, "$(NAME)", "$(FLAVOUR)")
    write_sub(sub["group"], "/bin/bash", f"{HERE}/run_sim_group.sh {REPO} {out} $(RUN) $(NCH)", None,
              dag_dir, "group_$(RUN)", "workday", transfer=False, disk="$(DISK)M")
    write_sub(sub["summary"], "/usr/bin/python3", f"{HERE}/campaign_summary.py {out} {os.path.abspath(args.runs)}",
              None, dag_dir, "summary", "espresso", transfer=False)

    # ECAL turned about y (angle scan): the data spot is in the ECAL frame, the gun in the lab (x is cos(turn) shorter)
    turn = ecal_turn_deg(args.compact)
    cx = math.cos(math.radians(turn))
    depths = layer_depths() if turn else None
    if turn and coll:
        ap.error("--far-collimator is not for a turned ECAL (its jaws sit at the ECAL-frame spot); use --rect-collimator")
    lines, groups, made, rect_runs = [], [], [], []
    for i, r in enumerate(runs, 1):
        run = r["run"]
        if only and run not in only:
            continue
        valtree = os.path.join(reco, run, f"ecal_{run}.valtree.root")
        if not os.path.exists(valtree):
            print(f"SKIP {run}: no valtree ({valtree})")
            continue
        spot = measure(valtree, os.path.join(dag_dir, "params", f"{run}.spot.json"))
        if spot["entries"] < args.min_events:
            print(f"SKIP {run}: {spot['entries']} events < --min-events {args.min_events}")
            continue
        if not spot["n"]:
            print(f"SKIP {run}: no shower-like events")
            continue
        ch = args.chunk_events
        compact, a, far = args.compact, collimator.aperture(coll, r["E"]), None
        is_rect = any(math.isclose(e, float(r["E"]), abs_tol=1e-6) for e in rect)
        n_sim, n_dummy = spot["n"], args.dummy_events
        if a is not None:   # the jaws are centred on the data spot of the run
            compact = collimator.write_compact(args.compact, f"generated/{args.campaign}/{run}.xml", spot["x"],
                                               spot["y"], a, args.far_collimator_z, args.far_collimator_length)
            far = {"a": a, "z": args.far_collimator_z, "length": args.far_collimator_length,
                   "transmission": args.far_collimator_transmission}
        elif is_rect:       # apertures decided at run time by the p2/p3 nodes; the chunks read this geometry
            compact = f"generated/{args.campaign}/{run}.xml"
            far = {"mode": "rect", "z": args.far_collimator_z, "length": args.far_collimator_length,
                   "transmission": args.far_collimator_transmission}
        if far:
            # the jaws stop part of the beam: simulate more so the shower-like statistics match the data
            n_sim = math.ceil(spot["n"] / args.far_collimator_transmission)
            n_dummy = max(args.dummy_events, args.far_collimator_dummy_events)
        n_events = -(-n_sim // ch) * ch
        if args.max_events:
            n_events = min(n_events, args.max_events)
        n_chunks = -(-n_events // ch)
        params = dict(r, data=spot, n_events=n_events, n_chunks=n_chunks, chunk_events=ch, dummy_events=n_dummy,
                      gun0={"x": spot["x"], "y": spot["y"], "sx": max(cx * spot["wx"], 1.0), "sy": max(spot["wy"], 1.0)},
                      compact=compact, far_collimator=far)
        if turn:
            # the barycentre is at the depth of the shower: the lab x of the beam is not cos(turn) x alone. Missing the
            # depth puts the gun where the beam enters through the side of the box (late showers, narrow spot).
            zbary = shower_zbary(valtree)
            params["turn_deg"], params["data_zbary"] = turn, zbary
            params["gun0"]["x"] = lab_x(spot["x"], zbary, turn, depths)
        json.dump(params, open(os.path.join(dag_dir, "params", f"{run}.data.json"), "w"), indent=2)
        made.append(run)
        if is_rect:
            rect_runs.append(run)

        flavour = "tomorrow" if float(r["E"]) >= 52 else "workday"
        group_done = all(os.path.exists(os.path.join(out, run, f"ecal_sim_{run}{s}.valtree.root")) for s in ("", "_nodigi"))
        dummy_done = group_done or os.path.exists(os.path.join(out, "params", f"{run}.json"))
        seed = args.seed_offset + i * 1000
        if is_rect:
            lines += rect_nodes(run, out, sub, seed, flavour, n_dummy, valtree, args.compact, args.campaign, dummy_done)
            last = f"p3_{run}"
        else:
            lines += [f"JOB d_{run} {sub['dummy']}" + (" DONE" if dummy_done else ""),
                      f'VARS d_{run} RUN="{run}" SEED="{seed + 999}" FLAVOUR="{flavour}" COMPACT="{compact}" '
                      f'NDUMMY="{n_dummy}" CAMP="{out}" NAME="dummy_{run}"',
                      f"RETRY d_{run} 2"]
            last = f"d_{run}"
        chunks = []
        for k in range(n_chunks):
            node = f"c_{run}_{k:03d}"
            remote = os.path.join(out, "chunks", run, f"ecal_sim_{run}_c{k:03d}")
            done = group_done or (os.path.exists(remote + ".root") and os.path.exists(remote + "_simple.root"))
            lines += [f"JOB {node} {sub['chunk']}" + (" DONE" if done else ""),
                      f'VARS {node} RUN="{run}" K="{k}" SEED="{args.seed_offset + i * 1000 + k}" CH="{ch}" '
                      f'NAME="{node}" FLAVOUR="{flavour}" COMPACT="{compact}"',
                      f"RETRY {node} 2"]
            chunks.append(node)
        lines += [f"JOB g_{run} {sub['group']}" + (" DONE" if group_done else ""),
                  f'VARS g_{run} RUN="{run}" NCH="{n_chunks}" DISK="{group_disk_mb(n_events)}"', f"RETRY g_{run} 1",
                  f"PARENT {last} CHILD {' '.join(chunks)}", f"PARENT {' '.join(chunks)} CHILD g_{run}"]
        groups.append(f"g_{run}")
        tag = f"  far collimator a {a:g} mm" if a is not None else "  rect collimator" if is_rect else ""
        print(f"{run:<30} {r['E']:>4} GeV  data ({spot['x']:6.1f},{spot['y']:6.1f}) mm  width {spot['wx']:5.1f} x "
              f"{spot['wy']:5.1f} mm  {spot['n']:>6} showers -> {n_chunks} x {ch}{tag}{'  [done]' if group_done else ''}")
    if groups and not args.no_summary:
        lines += ["JOB summary " + sub["summary"], f"PARENT {' '.join(groups)} CHILD summary"]
    dag = os.path.join(dag_dir, f"{args.campaign}.dag")
    open(dag, "w").write("\n".join(lines) + "\n")
    print(f"--- {len(made)} runs -> {dag}\n--- output: {out}")

    if args.submit:
        prepare_output(out, dag_dir, made, rect_runs)
        sys.exit(subprocess.call(["condor_submit_dag", "-batch-name", args.campaign, os.path.basename(dag)],
                                 cwd=dag_dir))


if __name__ == "__main__":
    main()
