#!/usr/bin/env python3
"""Write (and with --submit, submit) the HTCondor DAG that re-runs a finished run-by-run campaign with another
digitiser setting: same runs, tuned guns, far-collimator geometries, event counts and Geant4 seeds as the source
campaign, so the Geant4 showers are the same events and only the digitisation changes.

Per run (no dummy and no tuning: the source campaign's params/<RUN>.json are reused as they are):
  c_RUN  run_sim_chunk.sh x n_chunks: ddsim + job3_digitize.py with the source's gun and seed of each chunk
  g_RUN  run_sim_group.sh: hadd, PID + valtree (digi and nodigi) -> <RUN>/ecal_sim_<RUN>{,_nodigi}.*, closure
  summary campaign_summary.py -> closure.tsv, beam_points_v10.txt

The geometry of a collimated run is written again from its params/<RUN>.json (far_collimator: z, length, ax, ay,
centred on the data spot) under simulation/geometry/generated/<campaign>/; when the source campaign's own file is in
this checkout it must come out identical. The seeds are not in params/: they come from --seeds (one line per run,
seed of chunk 0 and number of chunks; chunk k uses seed_chunk0 + k), extracted from the source campaign's DAGs.

    # final_v11 without the occupancy sag (the chip baseline shift) in the digitisation
    python3 simulation/campaign/make_rerun_sim_dag.py --source final_v11 --campaign final_v11_nosag --no-occupancy-sag
    python3 simulation/campaign/make_rerun_sim_dag.py --source final_v11 --campaign final_v11_nosag --no-occupancy-sag \\
        --submit
    # any other digitiser switch of job3_digitize.py: --digi-env NAME=VALUE (repeatable)

Without --submit nothing is written on EOS. With it: <out>/params/ (copies of the source's, tagged with the rerun)
and <out>/rerun.json (source, digitiser environment, commit of this checkout). <dag-dir>/launched_from.txt and
uncommitted.diff record the code the jobs read. Finished nodes are written as DONE, so re-running after a failure
resubmits only what is missing. Run it in the Key4hep environment (source init_siwecalsoft.sh).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

from siwecal_common import paths
from make_run_list import read_runs
from make_run_sim_dag import eos_mkdir, group_disk_mb, write_sub
import collimator

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SIM = paths.simulation_dir()
NO_SAG = {"OCCUPANCY_SAG_TABLE": "", "OCCUPANCY_SLOPE": "0"}   # job3_digitize.py: both off = no baseline sag


def read_seeds(path):
    """{RUN: (seed of chunk 0, number of chunks)} from a seeds file (RUN seed_chunk0 n_chunks; # comments)."""
    seeds = {}
    for line in open(path):
        line = line.split("#", 1)[0].split()
        if line:
            seeds[line[0]] = (int(line[1]), int(line[2]))
    return seeds


def parse_env(items):
    env = {}
    for item in items:
        name, sep, value = item.partition("=")
        if not sep or not name.isidentifier():
            raise ValueError(f"--digi-env {item!r}: expected NAME=VALUE")
        if "'" in value or '"' in value:
            raise ValueError(f"--digi-env {item!r}: quotes are not allowed in the value")
        env[name] = value
    return env


def condor_env(env):
    """NAME='value' pairs of the HTCondor environment string (an empty value stays defined and empty)."""
    return " ".join(f"{k}='{v}'" for k, v in env.items())


def geometry(params, campaign, base):
    """COMPACT_FILE of a run: the base line, or its far collimator written again from params under
    generated/<campaign>/<RUN>.xml (as collimator_prep.write_geometry and make_run_sim_dag.py write it)."""
    far, run, data = params.get("far_collimator"), params["run"], params["data"]
    if not far:
        return params["compact"]
    rel = f"generated/{campaign}/{run}.xml"
    if far.get("mode") == "rect":
        ax, ay = far.get("ax"), far.get("ay")
        if ax or ay:
            return collimator.write_compact(base, rel, data["x"], data["y"], ax, far["z"], far["length"], ay=ay)
        return collimator.write_open(base, rel)
    return collimator.write_compact(base, rel, data["x"], data["y"], far["a"], far["z"], far["length"])


def same_geometry(source_rel, new_rel):
    """None if the source campaign's geometry is not in this checkout, else whether the two files are identical."""
    src = os.path.join(collimator.GEO, source_rel)
    if not os.path.exists(src):
        return None
    return open(src).read() == open(os.path.join(collimator.GEO, new_rel)).read()


def provenance(dag_dir):
    """Commit and local changes of the checkout the jobs read -> <dag-dir>/launched_from.txt, uncommitted.diff."""
    git = lambda *a: subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True).stdout   # noqa: E731
    commit = git("rev-parse", "HEAD").strip()
    diff = git("diff", "HEAD")
    open(os.path.join(dag_dir, "launched_from.txt"), "w").write(commit + "\n")
    open(os.path.join(dag_dir, "uncommitted.diff"), "w").write(diff)
    return commit, bool(diff)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="finished campaign to re-run: Processed/<source> (or a path)")
    ap.add_argument("--campaign", required=True, help="output Processed/<campaign> (not the source)")
    ap.add_argument("--seeds", default=None, help="seeds file (default simulation/campaign/seeds_<source>.txt)")
    ap.add_argument("--runs", default=os.path.join(HERE, "runs_v10.txt"),
                    help="run list: order of the DAG and rows of the summary")
    ap.add_argument("--only", default=None, help="comma-separated RUN names")
    ap.add_argument("--out", default=None, help="EOS output base (default Simulation/Processed/<campaign>)")
    ap.add_argument("--dag-dir", default=None, help="DAG, submit files, logs (default work/condor_<campaign>)")
    ap.add_argument("--no-occupancy-sag", action="store_true",
                    help="digitise without the chip baseline sag (OCCUPANCY_SAG_TABLE='' OCCUPANCY_SLOPE=0)")
    ap.add_argument("--digi-env", action="append", default=[], metavar="NAME=VALUE",
                    help="environment of job3_digitize.py in the chunks (repeatable)")
    ap.add_argument("--max-chunks", type=int, default=None, help="only the first chunks of each run (tests)")
    ap.add_argument("--sigma-e", default="0.02", help="as the source campaign (make_run_sim_dag.py default)")
    ap.add_argument("--compact", default="SND_compact_beamline.xml", help="base line, as the source campaign")
    ap.add_argument("--beam-z", type=float, default=-65500.0, help="as the source campaign")
    ap.add_argument("--no-summary", action="store_true")
    ap.add_argument("--submit", action="store_true")
    args = ap.parse_args()
    try:
        digi = dict(NO_SAG if args.no_occupancy_sag else {}, **parse_env(args.digi_env))
    except ValueError as e:
        ap.error(str(e))
    if not digi:
        ap.error("nothing to change: give --no-occupancy-sag or --digi-env")

    src = args.source if os.path.isabs(args.source) else os.path.join(SIM, "Processed", args.source)
    src_name = os.path.basename(src.rstrip("/"))
    out = args.out or os.path.join(SIM, "Processed", args.campaign)
    if args.campaign == src_name or os.path.realpath(out) == os.path.realpath(src):
        ap.error("the re-run must not write into the source campaign")
    seeds_file = args.seeds or os.path.join(HERE, f"seeds_{src_name}.txt")
    if not os.path.exists(seeds_file):
        ap.error(f"no seeds file {seeds_file}")
    seeds = read_seeds(seeds_file)
    dag_dir = os.path.abspath(args.dag_dir or os.path.join(REPO, "work", f"condor_{args.campaign}"))
    for d in ("logs", "params"):
        os.makedirs(os.path.join(dag_dir, d), exist_ok=True)
    runs = read_runs(args.runs)
    only = set(args.only.split(",")) if args.only else None
    commit, dirty = provenance(dag_dir)
    rerun = {"source": src, "seeds": os.path.abspath(seeds_file), "digi_env": digi, "commit": commit,
             "uncommitted_changes": dirty}

    env = (f"COMPACT_FILE=$(COMPACT) BEAM_Z_MM={args.beam_z:g} PHYSICS_LIST=QGSP_BERT_EMZ RECO_TABLE=th210 "
           f"SIGMA_E={args.sigma_e} {condor_env(digi)}")
    sub = {k: os.path.join(dag_dir, f"{k}.sub") for k in ("chunk", "group", "summary")}
    write_sub(sub["chunk"], f"{HERE}/run_sim_chunk.sh", f"{REPO} {out} $(RUN) $(K) $(SEED) $(CH)", env,
              dag_dir, "$(NAME)", "$(FLAVOUR)")
    write_sub(sub["group"], "/bin/bash", f"{HERE}/run_sim_group.sh {REPO} {out} $(RUN) $(NCH)", None,
              dag_dir, "group_$(RUN)", "workday", transfer=False, disk="$(DISK)M")
    write_sub(sub["summary"], "/usr/bin/python3", f"{HERE}/campaign_summary.py {out} {os.path.abspath(args.runs)}",
              None, dag_dir, "summary", "espresso", transfer=False)

    lines, groups, made, bad = [], [], [], []
    for r in runs:
        run = r["run"]
        if only and run not in only:
            continue
        pfile = os.path.join(src, "params", f"{run}.json")
        if not os.path.exists(pfile):
            print(f"SKIP {run}: not in the source campaign ({pfile})")
            continue
        if run not in seeds:
            bad.append(f"{run}: no seed in {seeds_file}")
            continue
        params = json.load(open(pfile))
        seed0, n_chunks = seeds[run]
        if n_chunks != params["n_chunks"]:
            bad.append(f"{run}: {n_chunks} chunks in the seeds file, {params['n_chunks']} in {pfile}")
            continue
        compact = geometry(params, args.campaign, args.compact)
        if compact != params["compact"] and same_geometry(params["compact"], compact) is False:
            bad.append(f"{run}: {compact} differs from the source's {params['compact']}")
            continue
        if args.max_chunks:
            n_chunks = min(n_chunks, args.max_chunks)
            params["n_events"] = min(params["n_events"], n_chunks * params["chunk_events"])
        params.update(compact=compact, n_chunks=n_chunks, rerun=dict(rerun, seed_chunk0=seed0))
        json.dump(params, open(os.path.join(dag_dir, "params", f"{run}.json"), "w"), indent=2)
        shutil.copy(os.path.join(src, "params", f"{run}.data.json"), os.path.join(dag_dir, "params"))
        made.append(run)

        flavour = "tomorrow" if float(r["E"]) >= 52 else "workday"
        group_done = all(os.path.exists(os.path.join(out, run, f"ecal_sim_{run}{s}.valtree.root")) for s in ("", "_nodigi"))
        chunks = []
        for k in range(n_chunks):
            node = f"c_{run}_{k:03d}"
            remote = os.path.join(out, "chunks", run, f"ecal_sim_{run}_c{k:03d}")
            done = group_done or (os.path.exists(remote + ".root") and os.path.exists(remote + "_simple.root"))
            lines += [f"JOB {node} {sub['chunk']}" + (" DONE" if done else ""),
                      f'VARS {node} RUN="{run}" K="{k}" SEED="{seed0 + k}" CH="{params["chunk_events"]}" '
                      f'NAME="{node}" FLAVOUR="{flavour}" COMPACT="{compact}"',
                      f"RETRY {node} 2"]
            chunks.append(node)
        lines += [f"JOB g_{run} {sub['group']}" + (" DONE" if group_done else ""),
                  f'VARS g_{run} RUN="{run}" NCH="{n_chunks}" DISK="{group_disk_mb(params["n_events"])}"',
                  f"RETRY g_{run} 1", f"PARENT {' '.join(chunks)} CHILD g_{run}"]
        groups.append(f"g_{run}")
        print(f"{run:<30} {r['E']:>4} GeV  gun ({params['gun']['x']:6.1f},{params['gun']['y']:6.1f}) mm  "
              f"{n_chunks} x {params['chunk_events']}  seed {seed0}  {compact}{'  [done]' if group_done else ''}")
    if bad:
        sys.exit("ERROR, nothing written:\n  " + "\n  ".join(bad))
    if groups and not args.no_summary:
        lines += ["JOB summary " + sub["summary"], f"PARENT {' '.join(groups)} CHILD summary"]
    dag = os.path.join(dag_dir, f"{args.campaign}.dag")
    open(dag, "w").write("\n".join(lines) + "\n")
    json.dump(rerun, open(os.path.join(dag_dir, "rerun.json"), "w"), indent=2)
    print(f"--- {len(made)} runs -> {dag}\n--- source: {src}\n--- digitiser: {condor_env(digi)}\n--- output: {out}"
          + (f"\n--- WARNING: {REPO} has uncommitted changes (uncommitted.diff)" if dirty else ""))

    if args.submit:
        for d in ("", "params", "chunks", "closure"):
            eos_mkdir(os.path.join(out, d) if d else out)
        for run in made:
            for name in (f"{run}.json", f"{run}.data.json"):
                dst = os.path.join(out, "params", name)
                if not os.path.exists(dst):
                    shutil.copy(os.path.join(dag_dir, "params", name), dst)
        if not os.path.exists(os.path.join(out, "rerun.json")):
            shutil.copy(os.path.join(dag_dir, "rerun.json"), os.path.join(out, "rerun.json"))
        sys.exit(subprocess.call(["condor_submit_dag", "-batch-name", args.campaign, os.path.basename(dag)],
                                 cwd=dag_dir))


if __name__ == "__main__":
    main()
