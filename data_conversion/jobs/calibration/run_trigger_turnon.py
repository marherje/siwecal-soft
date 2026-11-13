#!/usr/bin/env python3
"""The trigger turn-on of a threshold set and of each slab with TriggerTurnOnCalibrator (Fill on the decoded chunks
of a beam run, then Fit), written as the YAML block the digitiser reads -- threshold_mip / sigma_mip / efficiency /
threshold_adc of the set and slab_overrides -- the same keys analysis/trigger_turnon.py --write-config wrote
(retired). Copying it into common/mappings/digi_calibration.yml is a deliberate step of its own.

    python3 data_conversion/jobs/calibration/run_trigger_turnon.py <outdir> --set th210 --run e253 \\
        [--chunks 2] [--per-chunk 40]
"""
import argparse
import glob
import os
import subprocess
import sys

import yaml

from siwecal_common import paths

STEERING = paths.options_file("data_conversion", "run_trigger_turnon.py")


def run_name(r):
    return f"TB2026CERN_eudaq_run_{int(r[1:]):06d}" if r.startswith("e") else f"TB2026CERN_run_{int(r):06d}"


def k4run(env, log):
    with open(log, "w") as fh:
        rc = subprocess.run(["k4run", STEERING], env=dict(os.environ, **env), stdout=fh, stderr=subprocess.STDOUT).returncode
    if rc:
        sys.exit(f"k4run failed (exit {rc}), see {log}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir")
    ap.add_argument("--set", required=True, help="th210 | th220 | th230")
    ap.add_argument("--run", required=True, help="beam run of the set ('e' prefix = eudaq)")
    ap.add_argument("--chunks", type=int, default=2, help="first N chunks of the run")
    ap.add_argument("--per-chunk", type=int, default=40, help="first N acquisitions of each chunk (0 = all)")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    run = run_name(a.run)
    chunks = sorted(glob.glob(os.path.join(paths.converted_dir(), run, "chunks", "chunk_*.root")))[:a.chunks]
    if not chunks:
        sys.exit(f"no decoded chunks for {run}")
    fill = os.path.join(a.outdir, f"{a.run}.turnon.txt")
    fit = os.path.join(a.outdir, f"turnon_{a.set}.txt")
    k4run({"TURNON_MODE": "Fill", "TURNON_SET": a.set, "TURNON_INPUT_FILES": ",".join(chunks),
           "TURNON_OUTPUT": fill, "TURNON_PER_CHUNK": str(a.per_chunk)}, fill + ".log")
    k4run({"TURNON_MODE": "Fit", "TURNON_FILL_FILES": fill, "TURNON_OUTPUT": fit,
           "TURNON_LABEL": f"{a.set}, {run}, {len(chunks)} chunk(s) x {a.per_chunk} acquisitions"}, fit + ".log")
    par = {l.split()[0]: [float(x) for x in l.split()[1:]] for l in open(fit) if not l.startswith("#")}
    block = {"threshold_mip": round(par["set_mip"][0], 4), "sigma_mip": round(par["set_mip"][1], 4),
             "efficiency": round(par["set_mip"][2], 4), "threshold_adc": round(par["set_adc"][0], 2),
             "source_run": run,
             "slab_overrides": {int(k[4:]): {"threshold_adc": round(v[0], 2), "sigma_adc": round(v[1], 2),
                                             "efficiency": round(v[2], 4), "turnon_source_run": run}
                                for k, v in sorted(par.items(), key=lambda kv: kv[0]) if k.startswith("slab")}}
    out = os.path.join(a.outdir, f"turnon_{a.set}.yml")
    with open(out, "w") as fh:
        fh.write(f"# TriggerTurnOnCalibrator, {a.set}: block for thresholds.{a.set} of common/mappings/digi_calibration.yml\n")
        yaml.safe_dump({a.set: block}, fh, sort_keys=False)
    print(f"{fit}\n{out}")


if __name__ == "__main__":
    main()
