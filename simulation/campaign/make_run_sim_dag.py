#!/usr/bin/env python3
"""Write (and with --submit, submit) the HTCondor DAG of a run-by-run simulation campaign: one simulated sample per
data run of the run list, with the beam and the statistics of that run.

Per run (design: docs/superpowers/specs/2026-11-13-run-by-run-simulation-design.md):
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

Runs shorter than --min-events (default 5000 events in the data valtree) are skipped. Without --submit nothing
is written on EOS: the data parameters go to <dag-dir>/params/ and are copied to
<out>/params/ at submission. Finished nodes are written as DONE, so re-running after a failure resubmits only what is
missing. Geometry/physics/digitiser as make_sim_dag.py.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

from siwecal_common import paths
from make_run_list import read_runs
from make_sim_dag import eos_mkdir

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SIM = paths.simulation_dir()


def measure(valtree, out_json):
    """siwecal_beamspot measure -> the spot dict (C++: siwecal/BeamSpot.h)."""
    subprocess.run(["siwecal_beamspot", "measure", valtree, out_json], check=True)
    return json.load(open(out_json))


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
    ap.add_argument("--submit", action="store_true")
    args = ap.parse_args()

    out = args.out or os.path.join(SIM, "Processed", args.campaign)
    dag_dir = os.path.abspath(args.dag_dir or os.path.join(REPO, "work", f"condor_{args.campaign}"))
    reco = args.data_reco or paths.reconstruction_dir()
    for d in ("logs", "params"):
        os.makedirs(os.path.join(dag_dir, d), exist_ok=True)
    runs = read_runs(args.runs)
    only = set(args.only.split(",")) if args.only else None

    env = (f"COMPACT_FILE={args.compact} BEAM_Z_MM={args.beam_z:g} PHYSICS_LIST=QGSP_BERT_EMZ RECO_TABLE=th210 "
           f"SIGMA_E={args.sigma_e}")
    sub = {k: os.path.join(dag_dir, f"{k}.sub") for k in ("dummy", "chunk", "group", "summary")}
    write_sub(sub["dummy"], f"{HERE}/run_sim_dummy.sh", f"{REPO} {out} $(RUN) $(SEED) {args.dummy_events}", env,
              dag_dir, "dummy_$(RUN)", "$(FLAVOUR)")
    write_sub(sub["chunk"], f"{HERE}/run_sim_chunk.sh", f"{REPO} {out} $(RUN) $(K) $(SEED) $(CH)", env,
              dag_dir, "$(NAME)", "$(FLAVOUR)")
    write_sub(sub["group"], "/bin/bash", f"{HERE}/run_sim_group.sh {REPO} {out} $(RUN) $(NCH)", None,
              dag_dir, "group_$(RUN)", "workday", transfer=False, disk="$(DISK)M")
    write_sub(sub["summary"], "/usr/bin/python3", f"{HERE}/campaign_summary.py {out} {os.path.abspath(args.runs)}",
              None, dag_dir, "summary", "espresso", transfer=False)

    lines, groups, made = [], [], []
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
        n_events = -(-spot["n"] // ch) * ch
        if args.max_events:
            n_events = min(n_events, args.max_events)
        n_chunks = -(-n_events // ch)
        params = dict(r, data=spot, n_events=n_events, n_chunks=n_chunks, chunk_events=ch,
                      gun0={"x": spot["x"], "y": spot["y"], "sx": max(spot["wx"], 1.0), "sy": max(spot["wy"], 1.0)})
        json.dump(params, open(os.path.join(dag_dir, "params", f"{run}.data.json"), "w"), indent=2)
        made.append(run)

        flavour = "tomorrow" if float(r["E"]) >= 52 else "workday"
        group_done = all(os.path.exists(os.path.join(out, run, f"ecal_sim_{run}{s}.valtree.root")) for s in ("", "_nodigi"))
        dummy_done = group_done or os.path.exists(os.path.join(out, "params", f"{run}.json"))
        lines += [f"JOB d_{run} {sub['dummy']}" + (" DONE" if dummy_done else ""),
                  f'VARS d_{run} RUN="{run}" SEED="{args.seed_offset + i * 1000 + 999}" FLAVOUR="{flavour}"',
                  f"RETRY d_{run} 2"]
        chunks = []
        for k in range(n_chunks):
            node = f"c_{run}_{k:03d}"
            remote = os.path.join(out, "chunks", run, f"ecal_sim_{run}_c{k:03d}")
            done = group_done or (os.path.exists(remote + ".root") and os.path.exists(remote + "_simple.root"))
            lines += [f"JOB {node} {sub['chunk']}" + (" DONE" if done else ""),
                      f'VARS {node} RUN="{run}" K="{k}" SEED="{args.seed_offset + i * 1000 + k}" CH="{ch}" '
                      f'NAME="{node}" FLAVOUR="{flavour}"',
                      f"RETRY {node} 2"]
            chunks.append(node)
        lines += [f"JOB g_{run} {sub['group']}" + (" DONE" if group_done else ""),
                  f'VARS g_{run} RUN="{run}" NCH="{n_chunks}" DISK="{group_disk_mb(n_events)}"', f"RETRY g_{run} 1",
                  f"PARENT d_{run} CHILD {' '.join(chunks)}", f"PARENT {' '.join(chunks)} CHILD g_{run}"]
        groups.append(f"g_{run}")
        print(f"{run:<30} {r['E']:>4} GeV  data ({spot['x']:6.1f},{spot['y']:6.1f}) mm  width {spot['wx']:5.1f} x "
              f"{spot['wy']:5.1f} mm  {spot['n']:>6} showers -> {n_chunks} x {ch}{'  [done]' if group_done else ''}")
    if groups:
        lines += ["JOB summary " + sub["summary"], f"PARENT {' '.join(groups)} CHILD summary"]
    dag = os.path.join(dag_dir, f"{args.campaign}.dag")
    open(dag, "w").write("\n".join(lines) + "\n")
    print(f"--- {len(made)} runs -> {dag}\n--- output: {out}")

    if args.submit:
        for d in (out, *(os.path.join(out, s) for s in ("params", "dummy", "chunks", "closure"))):
            eos_mkdir(d)
        for run in made:   # new files only: an existing data json of this campaign is kept
            dst = os.path.join(out, "params", f"{run}.data.json")
            if not os.path.exists(dst):
                shutil.copy(os.path.join(dag_dir, "params", f"{run}.data.json"), dst)
        sys.exit(subprocess.call(["condor_submit_dag", "-batch-name", args.campaign, os.path.basename(dag)],
                                 cwd=dag_dir))


if __name__ == "__main__":
    main()
